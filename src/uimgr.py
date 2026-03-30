# coding=UTF-8
"""
Copyright (c) 2026 KKeygen

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
"""

import hashlib
import json
import os
import sys
import threading

from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, QUrl
from PyQt6.QtWebEngineCore import (
    QWebEngineUrlScheme,
    QWebEngineUrlSchemeHandler,
    QWebEngineUrlRequestJob,
    QWebEnginePage,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QMainWindow

from logutil import setup_logger
from secure_write import write_file_restricted

logger = setup_logger()

# The custom URL scheme for the local UI.
SCHEME_NAME = b"idvlogin"
# Host used for CDN-proxied resources (idvlogin://cdn/...)
_CDN_PROXY_HOST = "cdn"
# Host used for opening external URLs in system browser (idvlogin://open/...)
_OPEN_PROXY_HOST = "open"

# In-memory cache for CDN resources: url -> (content_type, body_bytes)
_cdn_cache: dict[str, tuple[str, bytes]] = {}

# Disk cache directory (initialised lazily via _get_cdn_cache_dir)
_cdn_cache_dir: str | None = None


def _get_cdn_cache_dir() -> str:
    """Return (and create if needed) the on-disk CDN cache directory."""
    global _cdn_cache_dir
    if _cdn_cache_dir is None:
        from envmgr import genv
        base = genv.get("FP_WORKDIR") or os.getcwd()
        _cdn_cache_dir = os.path.join(base, "cdn_cache")
    os.makedirs(_cdn_cache_dir, exist_ok=True)
    return _cdn_cache_dir


def _url_cache_key(url: str) -> str:
    """Derive a filesystem-safe cache key from the URL basename.

    Keyed by filename so that the same resource served by different CDNs
    shares one cache entry.  This avoids repeated timeouts when a primary
    CDN is unreachable: once any mirror delivers the file, all subsequent
    requests (even to the dead CDN) hit the cache instantly.
    """
    from urllib.parse import urlparse

    basename = os.path.basename(urlparse(url).path)
    if not basename:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()
    return hashlib.sha256(basename.encode("utf-8")).hexdigest()


def _load_cdn_from_disk(url: str) -> tuple[str, bytes] | None:
    """Try to load a CDN resource from the on-disk cache."""
    cache_dir = _get_cdn_cache_dir()
    key = _url_cache_key(url)
    meta_path = os.path.join(cache_dir, key + ".meta")
    data_path = os.path.join(cache_dir, key + ".data")
    try:
        if os.path.exists(meta_path) and os.path.exists(data_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            with open(data_path, "rb") as f:
                body = f.read()
            return meta.get("content_type", "application/octet-stream"), body
    except Exception:
        pass
    return None


def _save_cdn_to_disk(url: str, content_type: str, body: bytes):
    """Persist a CDN resource to the on-disk cache using secure_write."""
    cache_dir = _get_cdn_cache_dir()
    key = _url_cache_key(url)
    meta_path = os.path.join(cache_dir, key + ".meta")
    data_path = os.path.join(cache_dir, key + ".data")
    try:
        meta = json.dumps({"url": url, "content_type": content_type}).encode("utf-8")
        write_file_restricted(meta_path, meta)
        write_file_restricted(data_path, body)
    except Exception as exc:
        logger.debug(f"CDN 磁盘缓存写入失败: {url}: {exc}")


def _fetch_cdn_resource(url: str) -> tuple[str, bytes, bool]:
    """Fetch a CDN resource via Python (bypasses system proxy).

    Returns ``(content_type, body, success)``; results are cached in memory
    and persisted to disk.  Failed fetches are **not** cached so that a
    subsequent attempt (e.g. after fallback) can retry.
    ``trust_env=False`` is set globally via ``requests.Session`` monkey-patch.
    """
    # 1) 内存缓存
    cached = _cdn_cache.get(url)
    if cached is not None:
        return (*cached, True)
    # 2) 磁盘缓存
    disk = _load_cdn_from_disk(url)
    if disk is not None:
        _cdn_cache[url] = disk
        return (*disk, True)
    # 3) 网络获取
    try:
        import requests as _req
        resp = _req.get(url, timeout=5)
        resp.raise_for_status()
        ct = resp.headers.get("Content-Type", "application/octet-stream")
        body = resp.content
    except Exception as exc:
        logger.warning(f"CDN 资源获取失败: {url}: {exc}")
        return "text/plain", b"", False
    _cdn_cache[url] = (ct, body)
    if body:
        _save_cdn_to_disk(url, ct, body)
    return ct, body, True


def register_url_scheme():
    """Register the ``idvlogin://`` scheme with QtWebEngine.

    **Must** be called *before* ``QApplication`` is created.
    """
    scheme = QWebEngineUrlScheme(SCHEME_NAME)
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.HostAndPort)
    scheme.setDefaultPort(443)  # 设置默认端口以消除警告
    scheme.setFlags(
        QWebEngineUrlScheme.Flag.SecureScheme
        | QWebEngineUrlScheme.Flag.LocalScheme
        | QWebEngineUrlScheme.Flag.LocalAccessAllowed
        | QWebEngineUrlScheme.Flag.CorsEnabled
        | QWebEngineUrlScheme.Flag.FetchApiAllowed
        | QWebEngineUrlScheme.Flag.ContentSecurityPolicyIgnored
    )
    QWebEngineUrlScheme.registerScheme(scheme)
    hms_scheme = QWebEngineUrlScheme(b"hms")
    hms_scheme.setDefaultPort(443)  # 设置默认端口以消除警告
    QWebEngineUrlScheme.registerScheme(hms_scheme)


class IDVLoginSchemeHandler(QWebEngineUrlSchemeHandler):
    """Handles ``idvlogin://`` requests inside QtWebEngine.

    Routes are dispatched to :class:`local_handler.LocalRequestHandler`
    so the same logic is shared between the mitmproxy addon and the
    Qt-based UI.
    """

    def __init__(self, *, game_helper, ui_logger, parent=None):
        super().__init__(parent)
        self.game_helper = game_helper
        self.ui_logger = ui_logger

    def requestStarted(self, job: QWebEngineUrlRequestJob):
        url: QUrl = job.requestUrl()
        host = url.host()

        # CDN proxy: idvlogin://cdn/https/host/path → fetch via Python
        if host == _CDN_PROXY_HOST:
            self._handle_cdn_proxy(job, url)
            return

        path = url.path() or "/"
        method = job.requestMethod().data().decode("utf-8", errors="replace")

        # Parse query parameters
        from PyQt6.QtCore import QUrlQuery
        qurl_query = QUrlQuery(url)
        args = {item[0]: item[1] for item in qurl_query.queryItems()}

        # Read body for POST
        json_body = None
        if method.upper() == "POST":
            device = job.requestBody()
            if device and device.isOpen():
                raw = bytes(device.readAll())
                try:
                    json_body = json.loads(raw) if raw else {}
                except Exception:
                    json_body = {}

        # Special case: serve the main page
        if path in ("/", "/open", "/index"):
            path = "/_idv-login/index"
        elif not path.startswith("/_idv-login/"):
            path = "/_idv-login" + path

        # Dispatch to shared handler
        from local_handler import LocalRequestHandler

        handler = LocalRequestHandler(
            game_helper=self.game_helper,
            logger=self.ui_logger,
        )

        try:
            _status, headers, body = handler.handle_simple(
                path, method.upper(), args, json_body
            )
        except Exception as e:
            self.ui_logger.exception(f"处理本地请求失败: {path}")
            body = json.dumps({"error": str(e)}).encode("utf-8")
            headers = {"Content-Type": "application/json"}

        content_type = headers.get("Content-Type", "application/octet-stream")

        buf = QBuffer(parent=job)
        buf.setData(QByteArray(body))
        buf.open(QIODevice.OpenModeFlag.ReadOnly)
        job.reply(content_type.encode("utf-8"), buf)

    def _handle_cdn_proxy(self, job: QWebEngineUrlRequestJob, url: QUrl):
        """Serve an external resource fetched via Python (bypasses proxy)."""
        raw_path = url.path()
        if raw_path.startswith("/"):
            raw_path = raw_path[1:]
        query = url.query()
        original_url = raw_path.replace("/", "://", 1)
        if query:
            original_url += "?" + query

        logger.debug(f"[CDN代理] 获取: {original_url}")
        ct, body, ok = _fetch_cdn_resource(original_url)
        if not ok:
            logger.warning(f"[CDN代理] 失败，返回错误: {original_url}")
            job.fail(QWebEngineUrlRequestJob.Error.RequestFailed)
            return
        logger.debug(f"[CDN代理] 完成: {original_url} ({len(body)} bytes, {ct})")
        buf = QBuffer(parent=job)
        buf.setData(QByteArray(body))
        buf.open(QIODevice.OpenModeFlag.ReadOnly)
        job.reply(ct.encode("utf-8"), buf)


from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


def _extract_original_url(url: QUrl) -> str:
    """Extract the original ``https://host/path`` from ``idvlogin://open/https/host/path``."""
    raw_path = url.path()
    if raw_path.startswith("/"):
        raw_path = raw_path[1:]
    original_url = raw_path.replace("/", "://", 1)
    query = url.query()
    if query:
        original_url += "?" + query
    return original_url


class _LoggingWebPage(QWebEnginePage):
    """QWebEnginePage subclass that forwards JS console messages to Python logger
    and intercepts ``idvlogin://open/…`` navigations to open them in the system browser."""

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        logger.debug(f"[JS:{level}] {message} (line {lineNumber}, {sourceID})")

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if url.scheme() == "idvlogin" and url.host() == _OPEN_PROXY_HOST:
            original = _extract_original_url(url)
            import webbrowser
            webbrowser.open(original)
            logger.debug(f"[外部链接] 系统浏览器打开: {original}")
            return False
        return True


class _UISignalRouter(QObject):
    """Routes cross-thread signals to main-thread slots.

    The slot ``_on_open_game`` is a *real* QObject slot, so
    ``AutoConnection`` correctly resolves to ``QueuedConnection``
    when emitted from a background thread, guaranteeing execution
    on the main (GUI) thread.
    """
    open_game_sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._callback = None
        self.open_game_sig.connect(self._on_open_game)

    def set_callback(self, callback):
        self._callback = callback

    @pyqtSlot(str)
    def _on_open_game(self, game_id: str):
        if self._callback:
            self._callback(game_id)


class _MainThreadDispatcher(QObject):
    """Synchronously dispatches a callable to the Qt main thread.

    Usage from a background thread::

        result = dispatcher.run_sync(some_function, arg1, arg2)

    The calling thread blocks until the main thread finishes execution.
    If already on the main thread, the callable is invoked directly.
    """
    _dispatch_sig = pyqtSignal(object, object, object)  # (fn, args, result_bag)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dispatch_sig.connect(self._execute)

    @pyqtSlot(object, object, object)
    def _execute(self, fn, args, bag):
        try:
            bag["value"] = fn(*args)
        except Exception as e:
            bag["error"] = e
        finally:
            bag["event"].set()

    def run_sync(self, fn, *args):
        """Run *fn* on the main thread; block until done."""
        if threading.current_thread() is threading.main_thread():
            return fn(*args)
        bag = {"event": threading.Event(), "value": None, "error": None}
        self._dispatch_sig.emit(fn, args, bag)
        bag["event"].wait()
        if bag["error"] is not None:
            raise bag["error"]
        return bag["value"]


class UIManager:
    """Manages the PyQt6/QtWebEngine window for the account management UI.

    The window is opened when the ``idvlogin://`` URI scheme is
    triggered (e.g. from a QR code redirect) or when the user
    wants to manage accounts.
    """

    def __init__(self, *, game_helper, ui_logger):
        self.game_helper = game_helper
        self.ui_logger = ui_logger
        self._window: QMainWindow | None = None
        self._view: QWebEngineView | None = None
        self._scheme_handler: IDVLoginSchemeHandler | None = None

        self._router = _UISignalRouter()
        self._router.set_callback(self._do_open_for_game)
        self._dispatcher = _MainThreadDispatcher()

    def open_for_game(self, game_id: str = ""):
        """Show the UI window for the given *game_id*. (Thread-safe)"""
        self._router.open_game_sig.emit(game_id)

    def _ensure_window(self):
        if self._window is not None:
            return

        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            raise RuntimeError("QApplication 未创建")

        self._window = QMainWindow()
        self._window.setWindowTitle("渠道服账号管理")
        self._window.resize(900, 700)

        self._view = QWebEngineView(self._window)
        self._window.setCentralWidget(self._view)

        # 使用自定义 Page 子类将 JS 控制台消息写入 Python 日志
        custom_page = _LoggingWebPage(self._view)
        self._view.setPage(custom_page)

        # Install the custom scheme handler for page loads.
        profile = custom_page.profile()
        self._scheme_handler = IDVLoginSchemeHandler(
            game_helper=self.game_helper,
            ui_logger=self.ui_logger,
            parent=self._view,
        )
        profile.installUrlSchemeHandler(SCHEME_NAME, self._scheme_handler)

    def _do_open_for_game(self, game_id: str = ""):
        """Show the UI window for the given *game_id*."""
        self._ensure_window()
        url = QUrl(f"idvlogin://app/_idv-login/index?game_id={game_id}")
        self._view.load(url)
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()
        self._force_foreground()

    def _force_foreground(self):
        """Use Win32 API to reliably bring the window to the foreground."""
        if sys.platform != "win32" or self._window is None:
            return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            hwnd = int(self._window.winId())
            fg_hwnd = user32.GetForegroundWindow()
            fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
            cur_tid = kernel32.GetCurrentThreadId()

            if fg_tid != cur_tid:
                user32.AttachThreadInput(fg_tid, cur_tid, True)
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            if fg_tid != cur_tid:
                user32.AttachThreadInput(fg_tid, cur_tid, False)
        except Exception:
            pass

    def close(self):
        if self._window:
            self._window.close()

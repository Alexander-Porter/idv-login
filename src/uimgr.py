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

import json
import os
import sys
import threading
from urllib.parse import parse_qs, urlparse

from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, QUrl
from PyQt6.QtWebEngineCore import (
    QWebEngineUrlScheme,
    QWebEngineUrlSchemeHandler,
    QWebEngineUrlRequestJob,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QMainWindow

from envmgr import genv
from logutil import setup_logger

logger = setup_logger()

# The custom URL scheme for the local UI.
SCHEME_NAME = b"idvlogin"


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
            status, headers, body = handler.handle_simple(
                path, method.upper(), args, json_body
            )
        except Exception as e:
            self.ui_logger.exception(f"处理本地请求失败: {path}")
            body = json.dumps({"error": str(e)}).encode("utf-8")
            status = 500
            headers = {"Content-Type": "application/json"}

        content_type = headers.get("Content-Type", "application/octet-stream")
        buf = QBuffer(parent=job)
        buf.setData(QByteArray(body))
        buf.open(QIODevice.OpenModeFlag.ReadOnly)
        job.reply(content_type.encode("utf-8"), buf)


from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


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


# Routes that create Qt widgets (browsers, file dialogs) and therefore
# MUST execute on the GUI / main thread.
_QT_ROUTES = frozenset({
    "/_idv-login/import",
    "/_idv-login/set-game-auto-start",
    "/_idv-login/launcher-install",
})


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
        self._local_port: int | None = None

        self._router = _UISignalRouter()
        self._router.set_callback(self._do_open_for_game)
        self._dispatcher = _MainThreadDispatcher()

    # ------------------------------------------------------------------
    # Local HTTP server — handles API requests from the UI page.
    #
    # The page itself is loaded via the idvlogin:// scheme handler.
    # A QWebEngineScript hooks window.fetch() to redirect /_idv-login/*
    # API calls to this HTTP server, bypassing Chromium's custom-scheme
    # fetch restrictions while keeping the page URL clean.
    # ------------------------------------------------------------------

    def _start_local_server(self):
        """Start a lightweight HTTP server on a random port (localhost only)."""
        if self._local_port is not None:
            return

        from http.server import HTTPServer, BaseHTTPRequestHandler
        from socketserver import ThreadingMixIn
        from urllib.parse import urlparse as _urlparse, parse_qs as _parse_qs

        game_helper = self.game_helper
        ui_logger = self.ui_logger
        dispatcher = self._dispatcher

        class _ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
            daemon_threads = True

        class _Handler(BaseHTTPRequestHandler):
            def _dispatch(self, method: str):
                parsed = _urlparse(self.path)
                path = parsed.path
                qs = _parse_qs(parsed.query, keep_blank_values=True)
                args = {k: v[0] if len(v) == 1 else v for k, v in qs.items()}

                if path in ("/", "/open", "/index"):
                    path = "/_idv-login/index"
                elif not path.startswith("/_idv-login/"):
                    path = "/_idv-login" + path

                json_body = None
                if method == "POST":
                    length = int(self.headers.get("Content-Length", 0))
                    raw = self.rfile.read(length) if length else b""
                    try:
                        json_body = json.loads(raw) if raw else {}
                    except Exception:
                        json_body = {}

                from local_handler import LocalRequestHandler
                handler = LocalRequestHandler(
                    game_helper=game_helper, logger=ui_logger,
                )

                def _call():
                    return handler.handle_simple(path, method, args, json_body)

                try:
                    if path in _QT_ROUTES:
                        # These routes create Qt widgets → must run on main thread
                        status, headers, body = dispatcher.run_sync(_call)
                    else:
                        status, headers, body = _call()
                except Exception:
                    body = b'{"error":"internal"}'
                    status, headers = 500, {"Content-Type": "application/json"}

                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                # CORS headers (page origin is idvlogin://, API is http://)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()
                self.wfile.write(body)

            def do_OPTIONS(self):
                """Handle CORS preflight."""
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

            do_GET = lambda s: s._dispatch("GET")
            do_POST = lambda s: s._dispatch("POST")

            def log_message(self, fmt, *args):
                pass  # suppress request logging

        server = _ThreadedHTTPServer(("127.0.0.1", 0), _Handler)
        self._local_port = server.server_address[1]
        logger.info(f"UI 本地服务启动: http://127.0.0.1:{self._local_port}")

        t = threading.Thread(
            target=server.serve_forever, daemon=True, name="ui-http-server",
        )
        t.start()

    def _make_fetch_hook_js(self) -> str:
        """Return JS source that hooks window.fetch for API calls."""
        return (
            "(function(){"
            "var _orig=window.fetch;"
            "window.fetch=function(input,init){"
            "var url=(typeof input==='string')?input:input.url;"
            "if(url.startsWith('/_idv-login/')){"
            f"url='http://127.0.0.1:{self._local_port}'+url;"
            "}"
            "return _orig.call(this,url,init);"
            "};"
            "})();"
        )

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

        # Install the custom scheme handler for page loads.
        profile = self._view.page().profile()
        self._scheme_handler = IDVLoginSchemeHandler(
            game_helper=self.game_helper,
            ui_logger=self.ui_logger,
            parent=self._view,
        )
        profile.installUrlSchemeHandler(SCHEME_NAME, self._scheme_handler)

        # Inject fetch hook BEFORE any page JS runs.
        from PyQt6.QtWebEngineCore import QWebEngineScript
        script = QWebEngineScript()
        script.setName("idv-fetch-hook")
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setSourceCode(self._make_fetch_hook_js())
        self._view.page().scripts().insert(script)

    def _do_open_for_game(self, game_id: str = ""):
        """Show the UI window for the given *game_id*."""
        self._start_local_server()
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

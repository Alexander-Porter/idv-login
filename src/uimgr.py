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
from __future__ import annotations

import asyncio
import json
import os
import sys
from urllib.parse import parse_qs, urlencode, urlsplit

from PyQt6.QtGui import QIcon

import app_state
from browser_runtime import BrowserSession
from logutil import setup_logger

logger = setup_logger()
UI_ORIGIN = "https://idv-login.invalid"


def configure_windows_app_identity():
    """Give the launcher a stable Windows taskbar identity."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "KKeygen.idv-login.GUI"
        )
    except Exception as exc:
        logger.debug(f"设置 Windows 应用标识失败: {exc}")


def _launcher_icon_path() -> str:
    candidates = []
    install_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.extend([
        os.path.join(install_root, "icon.ico"),
        os.path.join(install_root, "assets", "icon.ico"),
        os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "icon.ico"),
    ])
    bundle_root = getattr(sys, "_MEIPASS", "")
    if bundle_root:
        candidates.extend([
            os.path.join(bundle_root, "icon.ico"),
            os.path.join(bundle_root, "assets", "icon.ico"),
        ])
    return next((path for path in candidates if os.path.isfile(path)), "")


def configure_application_icon(app):
    """Set the process-wide icon used by launcher windows and the taskbar."""
    icon_path = _launcher_icon_path()
    if not icon_path:
        logger.warning("未找到启动器图标，任务栏可能继续使用 Qt 默认图标")
        return
    icon = QIcon(icon_path)
    if icon.isNull():
        logger.warning(f"启动器图标无法读取: {icon_path}")
        return
    app.setWindowIcon(icon)


def _minimize_console_window():
    """Minimize the owning Python console after the GUI is visible."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
    except Exception as exc:
        logger.debug(f"最小化控制台窗口失败: {exc}")


class UIManager:
    """Account UI in a separate browser, without an application HTTP API or embedded view.

    The reserved .invalid origin exists only in this session's request router.
    Provider login sessions never receive this router or native capabilities.
    Native dialogs, download tasks, IPC and the proxy stay in the Python host.
    """
    shell_kind = "external-browser"
    window_drag_supported = False
    window_toggle_maximize_supported = False

    def __init__(self, *, game_helper, ui_logger):
        self.game_helper = game_helper
        self.ui_logger = ui_logger
        self._session = None
        self._ready = False
        self._pending_url = ""
        self._pending_launch = ("", "")
        self._reopen_requested = False
        self._startup_error = None
        self._setup_dialog = None

    def open_for_game(self, game_id: str = "", initial_view: str = ""):
        app_state.run_on_main_thread(lambda: self._open(game_id, initial_view))

    def start_system_move(self):
        return False  # The external browser owns its native title bar.

    def toggle_maximized(self):
        return False

    def _open(self, game_id, initial_view):
        self._pending_launch = (game_id, initial_view)
        query = {}
        if game_id:
            query["game_id"] = game_id
        if initial_view:
            query["view"] = initial_view
        self._pending_url = UI_ORIGIN + "/_idv-login/index"
        if query:
            self._pending_url += "?" + urlencode(query)
        if self._session is not None:
            if self._session.is_closing:
                self._reopen_requested = True
                return
            if self._ready:
                self._session.navigate("main", self._pending_url)
                self._session.focus()
            return
        if self._setup_dialog is not None:
            self._setup_dialog.raise_()
            self._setup_dialog.activateWindow()
            return
        from envmgr import genv
        profile = os.path.join(genv.get("FP_WORKDIR") or os.getcwd(),
                               "webui_profile", "external-browser")
        session = BrowserSession(
            dispatch=app_state.run_on_main_thread,
            on_event=lambda event, *args: self._event(session, event, *args),
            profile_path=profile, route_handler=self._route, size=(1200, 820),
        )
        self._session = session
        self._startup_error = None
        self._launch_url = self._pending_url
        session.start(self._pending_url)

    def _event(self, session, event, *args):
        if session is not self._session:
            return
        if event == "ready":
            self._ready = True
            # An IPC activation may have arrived while the browser was starting.
            if self._pending_url != self._launch_url:
                session.navigate("main", self._pending_url)
            session.focus()
            _minimize_console_window()
        elif event == "warning":
            app_state.toast(args[0], 7000)
        elif event == "startup_failed":
            self._startup_error = args[0]
            self.ui_logger.error(args[0])
        elif event == "error":
            self.ui_logger.error(args[0])
            app_state.toast(args[0], 8000)
        elif event == "finished":
            self._session = None
            self._ready = False
            if self._startup_error:
                from browser_setup import BrowserSetupDialog
                def done(retry):
                    dialog, self._setup_dialog = self._setup_dialog, None
                    dialog.deleteLater()
                    self._reopen_requested = False
                    if retry:
                        self._open(*self._pending_launch)
                self._setup_dialog = BrowserSetupDialog(
                    self._startup_error, on_retry=lambda: done(True), on_cancel=lambda: done(False))
                self._setup_dialog.open()
            elif self._reopen_requested:
                self._reopen_requested = False
                self._open(*self._pending_launch)
        # Do not forward arbitrary page console messages: they may contain
        # account/verification data. Backend operation logs remain unchanged.

    async def _route(self, route):
        request = route.request
        target = urlsplit(request.url)
        try:
            frame = request.frame
            source = urlsplit(request.source_url)
        except Exception:
            await route.abort("blockedbyclient")
            return
        origin_matches = (target.scheme == "https" and
                          target.netloc == "idv-login.invalid")
        if not origin_matches:
            if request.is_navigation_request():
                if frame.parent is not None:
                    # Existing UI embeds an HTTPS mini-game. Keep it in its
                    # unprivileged subframe, never turn it into an OS launch or
                    # give it access to the main-page-only native API.
                    if target.scheme == "https":
                        await route.continue_()
                    else:
                        await route.abort("blockedbyclient")
                    return
                # A support/news link must not replace the privileged UI or
                # gain native access by opening a related popup.
                if target.scheme in ("https", "http"):
                    import webbrowser
                    await asyncio.to_thread(webbrowser.open, request.url)
                await route.abort("blockedbyclient")
                if frame is frame.page.main_frame and frame.page not in (
                        route.session.pages.get("main"),):
                    await frame.page.close()
            else:
                await route.continue_()
            return
        main = self._session.pages.get("main") if self._session else None
        source_is_ui = (source.scheme == "https" and
                        source.netloc == "idv-login.invalid")
        is_index = (target.path == "/_idv-login/index" and
                    request.method == "GET" and request.is_navigation_request())
        # Only the single top-level application page may use the native API.
        # Initial about:blank may navigate to index, never call an API.
        allowed = (frame.page is main and frame is main.main_frame and
                   (source_is_ui or (is_index and frame.url == "about:blank")))
        headers = request.headers
        if headers.get("origin", UI_ORIGIN) != UI_ORIGIN:
            allowed = False
        if not allowed or not target.path.startswith("/_idv-login/"):
            await route.fulfill(status=403, content_type="text/plain", body="Forbidden")
            return
        if request.method not in ("GET", "POST"):
            await route.fulfill(status=405, body="Method not allowed")
            return
        try:
            body = request.post_data or ""
            if len(body.encode("utf-8")) > 2 * 1024 * 1024:
                await route.fulfill(status=413, body="Request too large")
                return
            json_body = json.loads(body) if body else None
            query = parse_qs(target.query, keep_blank_values=True)
            args = {key: values[0] if len(values) == 1 else values
                    for key, values in query.items()}
            from local_handler import LocalRequestHandler
            handler = LocalRequestHandler(game_helper=self.game_helper,
                                          logger=self.ui_logger)
            status, response_headers, response_body = await asyncio.to_thread(
                handler.handle_simple, target.path, request.method, args, json_body)
            response_headers = dict(response_headers)
            response_headers.update({
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Cross-Origin-Resource-Policy": "same-origin",
                "Content-Security-Policy": "frame-ancestors 'none'; object-src 'none'; base-uri 'self'",
            })
            await route.fulfill(status=status, headers=response_headers, body=response_body)
        except (ValueError, TypeError):
            await route.fulfill(status=400, content_type="application/json",
                                body='{"error":"Invalid request"}')
        except Exception:
            # Never copy Browser protocol exceptions, request bodies or query strings
            # into the log: this transport also carries account imports.
            self.ui_logger.error("独立浏览器本地请求处理失败")
            try:
                await route.fulfill(status=500, content_type="application/json",
                                    body='{"error":"Local request failed"}')
            except Exception:
                pass

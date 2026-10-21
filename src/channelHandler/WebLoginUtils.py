"""Native login controls plus an isolated, external browser window.

The small Qt widget contains only controls, never a WebView. The provider page
runs in a separate installed browser; its profile and control session belong to this login.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit
from PyQt6.QtCore import QUrl, QTimer
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QPushButton, QWidget, QHBoxLayout, QLabel
import app_state
from browser_runtime import BrowserSession
from envmgr import genv
from logutil import setup_logger

_CURRENT_COOKIE_TOKEN = object()


class ExternalPage:
    """The small page contract actually used by the channel adapters."""
    def __init__(self, owner, page_id="main"):
        self.owner = owner
        self.page_id = page_id
        self._url = "about:blank"
        self.cookie_token = None

    def url(self):
        return QUrl(self._url)

    def runJavaScript(self, script, callback=None):
        if self.owner.session is not None:
            self.owner.session.evaluate(self.page_id, script, callback)

    def toPlainText(self, callback):
        if self.owner.cookie_export is not None:
            if self.cookie_token is None or self.owner.session is None:
                callback(None)
                return
            self.owner.session.evaluate(
                self.page_id, "document.body ? document.body.innerText : ''", callback,
                cookie_token=self.cookie_token)
        else:
            self.runJavaScript("document.body ? document.body.innerText : ''", callback)

    def close(self):
        if self.owner.session is not None:
            self.owner.session.close_page(self.page_id)


class WebBrowser(QWidget):
    callback_schemes = ()
    cookie_export = None

    def __init__(self, name="WebLoginDefault", keepCookie=True, frameless=False):
        super().__init__()
        self.app = QApplication.instance()
        self.logger = setup_logger()
        self.cookies = {}
        self.cookie_records = []
        self._cookie_snapshots = {}
        self._event_cookie_token = None
        self._cookie_commit_token = None
        self._cookie_commit_accepted = False
        self._session_finished = False
        self.result = ""
        self.session = None
        self.page = ExternalPage(self)
        self._pages = {"main": self.page}
        self._keep_cookies = bool(keepCookie)
        self._user_agent = ""
        self._scripts = []
        self._url = "about:blank"
        self._browser_size = (1000, 750)
        self._cleanup_called = False
        self._finished = False
        self._browser_running = False
        self._startup_error = None
        self._setup_dialog = None
        # Snapshot the account UUID now. Never consult this mutable global from
        # the browser thread, and never reuse a user's ordinary browser profile.
        identity = str(genv.get("GLOB_LOGIN_UUID", "") or name)
        import re
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", identity):
            import hashlib
            identity = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        profile_base = genv.get("GLOB_LOGIN_PROFILE_PATH") or os.path.join(
            genv.get("FP_WORKDIR") or os.getcwd(), "profile")
        self._persistent_storage_path = os.path.join(profile_base, identity, "external-browser")

        self.setWindowTitle("独立浏览器登录")
        self.layout = QVBoxLayout(self)
        self._status_label = QLabel("登录页将在独立浏览器窗口中打开。关闭该窗口或点击取消即可终止本次登录。")
        self._status_label.setWordWrap(True)
        self.layout.addWidget(self._status_label)
        self.toolBarLayout = QHBoxLayout()
        self.layout.addLayout(self.toolBarLayout)
        focus = QPushButton("显示登录页面")
        focus.clicked.connect(self.focus_browser)
        self.toolBarLayout.addWidget(focus)
        self.clear_cookie_button = QPushButton("强制退登")
        self.clear_cookie_button.clicked.connect(self.clear_cookies)
        self.toolBarLayout.addWidget(self.clear_cookie_button)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.cleanup)
        self.toolBarLayout.addWidget(cancel)
        super().resize(500, 130)

    def resize(self, width, height):
        # Existing adapters set provider-specific browser dimensions, not the
        # dimensions of the separate native controls window.
        self._browser_size = (int(width), int(height))

    def focus_browser(self):
        if self.session is not None:
            self.session.focus()

    def show_toast(self, text, duration_ms=3000):
        self._status_label.setText(str(text))
        app_state.toast(str(text), duration_ms)

    def set_user_agent(self, user_agent):
        if self.session is not None:
            raise RuntimeError("浏览器启动后不可更换登录 User-Agent")
        self._user_agent = str(user_agent or "")

    def add_init_script(self, source, name=""):
        if self.session is not None:
            raise RuntimeError("初始化脚本必须在打开登录页面前设置")
        if source:
            self._scripts.append(str(source))

    def set_url(self, url):
        self._url = str(url)
        if self.session is not None:
            self.session.navigate("main", self._url)

    def open_popup(self, url):
        if self.session is None:
            raise RuntimeError("登录浏览器尚未启动")
        page_id = self.session.new_page(str(url))
        page = ExternalPage(self, page_id)
        self._pages[page_id] = page
        return page

    def _on_browser_event(self, event, *args):
        if event == "warning":
            app_state.toast(args[0], 7000)
        elif event == "cookies_snapshot":
            if self._cleanup_called:
                return
            token, records = args
            self._cookie_snapshots[token] = tuple(dict(cookie) for cookie in records)
            while len(self._cookie_snapshots) > 256:
                self._cookie_snapshots.pop(next(iter(self._cookie_snapshots)))
            self._replace_cookie_records(records)
            return
        elif event == "cookie_boundary":
            if self._cleanup_called:
                return
            page_id, token = args
            page = self._pages.setdefault(page_id, ExternalPage(self, page_id))
            page.cookie_token = token
            self._event_cookie_token = token
            self._replace_cookie_records(self._cookie_snapshots.get(token, ()))
            return
        elif event == "cookies_committed":
            token, records = args
            if self._finished or token != self._cookie_commit_token:
                return
            self._cookie_commit_accepted = True
            self._replace_cookie_records(records)
            self._cookie_snapshots = {token: tuple(dict(cookie) for cookie in records)}
            if self._session_finished:
                self._complete()
            return
        elif event == "cookies_reset":
            if not self._cleanup_called:
                self._cookie_snapshots.clear()
                self._event_cookie_token = None
                for page in self._pages.values():
                    page.cookie_token = None
                self._replace_cookie_records(())
            return
        elif event == "cookies":
            # Opted-in channels only consume transaction-bearing snapshots.
            # A late generic event must never replace committed credentials.
            if self.cookie_export is None and not self._cleanup_called:
                self._replace_cookie_records(args[0])
            return
        if event == "cookie_error":
            if self._cookie_commit_accepted:
                return
            self.result = ""
            self._cookie_commit_token = None
            self._cookie_snapshots.clear()
            self._replace_cookie_records(())
            self._status_label.setText(args[0])
            app_state.toast(args[0], 7000)
            self.cleanup()
            if self._session_finished:
                self._complete()
            return
        if event == "finished":
            self._session_finished = True
            if self._startup_error and not self._cleanup_called:
                from browser_setup import BrowserSetupDialog
                def retry():
                    self._setup_dialog.deleteLater()
                    self._setup_dialog = None
                    self._start_browser()
                self._setup_dialog = BrowserSetupDialog(
                    self._startup_error, on_retry=retry, on_cancel=self._complete, parent=self)
                self._setup_dialog.open()
            else:
                self._complete()
            return
        if self._cleanup_called:
            return
        if event == "startup_failed":
            self._startup_error = args[0]
            self._status_label.setText(args[0])
        elif event == "error":
            self._status_label.setText(args[0])
            self.logger.error(args[0])
            app_state.toast(args[0], 6000)
        elif event == "page":
            self._pages.setdefault(args[0], ExternalPage(self, args[0]))
        elif event == "url":
            page_id, url = args
            page = self._pages.setdefault(page_id, ExternalPage(self, page_id))
            page._url = url
            # Supplier-created popups belong to this login too. Validate their
            # URL in the channel; never replay it into the main page.
            self.handle_url_change(QUrl(url))
        elif event == "loaded":
            page = self._pages.setdefault(args[0], ExternalPage(self, args[0]))
            self.on_page_load_finished(page, args[1])
        elif event == "console":
            page_id, level, message, line, source = args
            page = self._pages.setdefault(page_id, ExternalPage(self, page_id))
            self.on_console_message(level, message, line, source, page)
        elif event == "page_closed":
            self.on_popup_closed(self._pages.get(args[0]))

    def on_popup_closed(self, page):
        pass

    def on_console_message(self, level, message, lineNumber, sourceID, page=None):
        pass

    def on_page_load_finished(self, page, success):
        if page is self.page:
            self.on_load_finished(success)

    def on_load_finished(self, success):
        if not success:
            self.logger.debug("[WebBrowser] 页面导航中断或加载失败")

    def handle_url_change(self, url):
        # Callback URLs may contain credentials; do not log their query/fragment.
        parsed = urlsplit(url.toString())
        self.logger.debug(f"[WebBrowser] 页面变化: {parsed.scheme}://{parsed.hostname or ''}{parsed.path}")
        if self.verify(url.toString()) and self.parseReslt(url.toString()):
            self.cleanup()

    def verify(self, url):
        return True

    def parseReslt(self, url):
        self.result = url
        return True

    def cookies_replaced(self):
        pass

    def _replace_cookie_records(self, records):
        self.cookie_records = [dict(cookie) for cookie in records]
        self.cookies.clear()
        self.cookies_replaced()
        for cookie in self.cookie_records:
            self.cookie_added(cookie)

    def cookie_added(self, cookie):
        self.cookies[cookie["name"]] = cookie["value"]

    def export_cookie(self):
        return dict(self.cookies)

    def clear_cookies(self):
        if self.session is not None:
            self.session.clear_cookies()

    def run(self):
        self.show()
        self._browser_running = True
        self._start_browser()
        if self.app and self.app.property("_main_loop_running"):
            return None
        self.app.exec()
        return self.result

    def _start_browser(self):
        self._startup_error = None
        self._session_finished = False
        self.session = BrowserSession(
            dispatch=app_state.run_on_main_thread, on_event=self._on_browser_event,
            profile_path=self._persistent_storage_path,
            persistent=self._keep_cookies, user_agent=self._user_agent,
            scripts=self._scripts, size=self._browser_size,
            callback_schemes=self.callback_schemes, cookie_export=self.cookie_export,
        )
        self.session.start(self._url)

    def closeEvent(self, event):
        if not self._finished:
            self.cleanup()
            event.ignore()
        else:
            event.accept()

    def cleanup(self, cookie_token=_CURRENT_COOKIE_TOKEN):
        if self._cleanup_called:
            return
        if self.cookie_export is not None and self.result:
            token = self._event_cookie_token if cookie_token is _CURRENT_COOKIE_TOKEN else cookie_token
            if token is None or token not in self._cookie_snapshots:
                self.result = ""
                self._replace_cookie_records(())
                app_state.toast("未取得完成页面对应的安全 Cookie 快照，已取消本次登录。", 7000)
            else:
                self._cookie_commit_token = token
                # Freeze the exact event snapshot now; completion still waits
                # for runtime's ACK that no earlier export failure revoked it.
                self._replace_cookie_records(self._cookie_snapshots[token])
        self._cleanup_called = True
        self._browser_running = False
        self.setEnabled(False)
        if self.session is not None:
            self.session.finish(self._cookie_commit_token)
            if self._session_finished and self._cookie_commit_token is None:
                self._complete()
        else:
            self._complete()

    def _complete(self):
        if self._finished:
            return
        if self._cookie_commit_token is not None and not self._cookie_commit_accepted:
            return
        if self.cookie_export is not None and not self._cookie_commit_accepted:
            self.result = ""
            self._replace_cookie_records(())
        self._finished = True
        self._cleanup_called = True
        self._browser_running = False
        callback = getattr(self, "_async_completion_callback", None)
        self._async_completion_callback = None
        if callback is not None:
            try:
                callback(self)
            except Exception:
                self.logger.exception("[WebBrowser] 异步登录回调执行失败")
        self.close()
        self.deleteLater()
        if self.app and not self.app.property("_main_loop_running"):
            QTimer.singleShot(0, self.app.quit)

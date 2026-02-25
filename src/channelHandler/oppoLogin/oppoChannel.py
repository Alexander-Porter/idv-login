import json
from typing import Any, Dict, Optional

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtWebEngineWidgets import QWebEngineView

from channelHandler.WebLoginUtils import WebBrowser
from channelHandler.oppoLogin.consts import (
    DEFAULT_CONSTS,
    OPPO_UC_CLIENT_DOMAIN,
    OPPO_WEBVIEW_UA,
    OppoNativeConsts,
)
from channelHandler.oppoLogin.jsbridge import OPPO_CONSOLE_PREFIX, build_mock_native_js
from logutil import setup_logger


class OppoBrowser(WebBrowser):
    def __init__(self, consts: OppoNativeConsts = DEFAULT_CONSTS):
        super().__init__("oppo", True)
        self.logger = setup_logger()
        self._captured: Optional[Dict[str, Any]] = None
        self._observed_popup_view: Optional[QWebEngineView] = None
        self._observed_popup_page = None
        self.consts = consts

        # UA 必须在加载前设置
        self.set_user_agent(OPPO_WEBVIEW_UA)

        # 文档创建前注入 JSBridge mock
        self.add_init_script(build_mock_native_js(self.consts), name="oppo_mock_native")

    def verify(self, url: str) -> bool:
        # Oppo 登录不靠 URL 跳转判定成功，靠 JSBridge 回调。
        return False

    def _open_observed_webview(self, url: str):
        if not url:
            return

        try:
            if self._observed_popup_view is not None:
                self._observed_popup_view.close()
                self._observed_popup_view.deleteLater()
        except Exception:
            pass

        popup = QWebEngineView(self)
        popup.setWindowTitle("Oppo Verify")
        popup.resize(800, 900)

        popup_page = self.create_page(self.profile, popup)
        popup.setPage(popup_page)

        self._observed_popup_view = popup
        self._observed_popup_page = popup_page

        popup.load(QUrl(url))
        popup.show()

    def _trigger_main_page_refresh(self):
        try:
            self.page.runJavaScript("if(window.onRefresh){onRefresh()}")
            self.logger.info("已在主页面触发 onRefresh")
        except Exception as e:
            self.logger.debug(f"触发主页面 onRefresh 失败: {e}")

    def _close_observed_popup(self):
        try:
            if self._observed_popup_view is not None:
                self._observed_popup_view.close()
                self._observed_popup_view.deleteLater()
        except Exception:
            pass
        self._observed_popup_view = None
        self._observed_popup_page = None

    def cleanup(self):
        self._close_observed_popup()
        super().cleanup()

    def _is_verify_finish_payload(self, param: Any) -> bool:
        if not isinstance(param, dict):
            return False
        data = param.get("data")
        if not isinstance(data, dict):
            return False
        operate = data.get("operate")
        if not isinstance(operate, dict):
            return False
        if operate.get("operateType") != "loginVerify":
            return False
        if operate.get("operateSuccess") is not True:
            return False
        return data.get("needResult") is True

    def on_console_message(self, level, message: str, lineNumber: int, sourceID: str, page=None):
        if not isinstance(message, str):
            return
        if not message.startswith(OPPO_CONSOLE_PREFIX):
            return

        payload = message[len(OPPO_CONSOLE_PREFIX) :].strip()
        try:
            data = json.loads(payload)
        except Exception:
            self.logger.debug(f"Oppo console payload 解析失败: {payload}")
            return

        method = (data or {}).get("method")
        param = json.loads((data or {}).get("param"))
        #self.logger.debug(f"Oppo console method {method} 不关心，payload: {payload}")
        # 只关心网页登录完成回调（或 setToken 透传 loginResp）
        if method not in ("vip.onFinish", "accountExternalSdk.setToken","vip.makeToast","vip.openAndObserveWebview"):
            self.logger.debug(f"Oppo console method {method} 不关心，payload: {payload}")
            return
        elif method == "vip.makeToast":
            content = ""
            if isinstance(param, dict):
                content = str(param.get("content", "") or "")
            self.logger.warning(f"网页提示： {content}")
            # 在浏览器所在 widget 上显示一个提示（持续 5 秒）
            if content:
                try:
                    self.show_toast(content, duration_ms=5000)
                except Exception:
                    pass
            return
        elif method == "vip.openAndObserveWebview":
            content = ""
            if isinstance(param, dict):
                content = str(param.get("content", "") or "")
            self._open_observed_webview(content)
            return
        elif method == "vip.onFinish" and page is self._observed_popup_page:
            if self._is_verify_finish_payload(param):
                self.logger.info("子页面登录校验完成，关闭子页面并刷新主页面")
                self._close_observed_popup()
                self._trigger_main_page_refresh()
            return

        login_resp = None
        if isinstance(param, dict):
            login_resp = param.get("loginResp") or param

        if not isinstance(login_resp, dict):
            return

        self._captured = login_resp
        self.result = login_resp
        self.logger.info("已捕获 Oppo 网页登录 loginResp，准备退出浏览器")

        # 避免在 console 回调栈内直接 teardown
        QTimer.singleShot(0, self.cleanup)


class OppoLogin:
    def __init__(self, start_url: str = OPPO_UC_CLIENT_DOMAIN):
        self.logger = setup_logger()
        self.start_url = start_url

    def webLogin(self, consts: OppoNativeConsts = DEFAULT_CONSTS) -> Optional[Dict[str, Any]]:
        browser = OppoBrowser(consts=consts)
        browser.set_url(self.start_url)
        resp = browser.run()
        if isinstance(resp, dict) and resp:
            return resp
        return None

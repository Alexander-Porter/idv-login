import os

from channelHandler.WebLoginUtils import WebBrowser
from logutil import setup_logger


class QQBrowser(WebBrowser):
    def __init__(self, qq_appid):
        super().__init__("myapp_qq", False)
        self.qq_appid = qq_appid

    def verify(self, url: str) -> bool:
        from urllib.parse import urlparse, parse_qs
        parsed_url = urlparse(url)
        if parsed_url.netloc == "imgcache.qq.com" and parsed_url.path == "/open/connect/widget/mobile/login/proxy.htm":
            query_dict = parse_qs(parsed_url.fragment)
            return "access_token" in query_dict.keys()
        return False

    def parseReslt(self, url):
        from urllib.parse import urlparse, parse_qs
        parsed_url = urlparse(url)
        query_dict = parse_qs(parsed_url.fragment)
        self.result = {
            "access_token": query_dict.get("access_token", [None])[0],
            "openid": query_dict.get("openid", [None])[0],
        }
        return True


class QQLogin:
    def __init__(self, qq_appid, game_id=""):
        os.chdir(os.path.join(os.environ["PROGRAMDATA"], "idv-login"))
        self.logger = setup_logger()
        self.qq_appid = qq_appid
        self.game_id = game_id
        self._active_browser: QQBrowser = None

    def webLogin(self, on_complete=None):
        login_url = f"https://openmobile.qq.com/oauth2.0/m_authorize?client_id={self.qq_appid}&scope=all&redirect_uri=auth://tauth.qq.com/&style=qr&response_type=token"
        browser = QQBrowser(self.qq_appid)
        browser.set_url(login_url)
        result = browser.run()

        if result is None:
            # 异步模式：浏览器已显示，等待用户登录完成
            self._active_browser = browser
            if on_complete is not None:
                def _on_async_done(b):
                    self._active_browser = None
                    try:
                        if not b.result or not isinstance(b.result, dict):
                            on_complete(None)
                            return
                        on_complete(b.result)
                    except Exception:
                        self.logger.exception("QQ异步登录处理失败")
                        on_complete(None)
                browser._async_completion_callback = _on_async_done
            return None

        return result

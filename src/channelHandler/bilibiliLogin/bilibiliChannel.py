"""Bilibili Game SDK 网页登录（QWebEngine + XHR 拦截）。

打开 sdk.biligame.com/login/ 登录页，通过注入 JS：
  - 模拟 agreement/config 响应（跳过合规弹窗）
  - 记录所有 XHR 请求/响应（调试用）
  - 捕获 otp/login 成功响应，提取 access_key
"""

import hashlib
import json
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import requests
from PyQt6.QtCore import QTimer

from channelHandler.WebLoginUtils import WebBrowser
from logutil import setup_logger
from ssl_utils import should_verify_ssl


# ── Console 前缀 ──────────────────────────────────────────────
BILI_NET_PREFIX = "__BILI_NET__::"
BILI_LOGIN_PREFIX = "__BILI_LOGIN__::"

# ── 登录页 URL 模板 ──────────────────────────────────────────
_LOGIN_URL_TEMPLATE = (
    "https://sdk.biligame.com/login/"
    "?cef=true&gameId={game_id}&appKey={app_key}"
    "&sdk_ver={sdk_ver}&is_gov_ver=1"
)

# ── 默认参数（第五人格 B站服） ────────────────────────────────
DEFAULT_GAME_ID = "183"
DEFAULT_APP_KEY = "h9Ejat5tFh81cq8"
DEFAULT_SDK_VER = "5.1.0"


def _build_login_url(
    game_id: str = DEFAULT_GAME_ID,
    app_key: str = DEFAULT_APP_KEY,
    sdk_ver: str = DEFAULT_SDK_VER,
) -> str:
    return _LOGIN_URL_TEMPLATE.format(
        game_id=game_id, app_key=app_key, sdk_ver=sdk_ver
    )


# ── Bilibili Sign 算法 ───────────────────────────────────────

def compute_sign(params: dict, app_key: str = DEFAULT_APP_KEY) -> str:
    """Bilibili Game SDK 签名：按 key 排序 → 拼接 value → 追加 appKey → MD5。"""
    sorted_items = sorted(params.items())
    plaintext = "".join(
        str(v) for k, v in sorted_items if k != "sign" and v is not None
    )
    plaintext += app_key
    return hashlib.md5(plaintext.encode("utf-8")).hexdigest()


# ── auto.login API ────────────────────────────────────────────

def call_auto_login(
    access_key: str,
    game_id: str = DEFAULT_GAME_ID,
    app_key: str = DEFAULT_APP_KEY,
) -> Dict[str, Any]:
    """调用 auto.login API 验证 access_key 并获取用户信息。

    返回原始 API 响应 dict。code=0 表示成功。

    注意：只发送 3 个核心参数 + sign。不要加 sdk_ver/timestamp（会导致 sign error）。
    """
    params = {
        "access_key": access_key,
        "game_id": str(game_id),
        "is_gov_ver": 1,
    }
    params["sign"] = compute_sign(params, app_key)
    url = "https://wpg-api.biligame.com/api/pcg/auto.login?" + urlencode(params)
    resp = requests.post(url, timeout=15, verify=should_verify_ssl())
    return resp.json()


def _build_intercept_js() -> str:
    """构建注入到登录页的 XHR 拦截脚本。

    功能：
    1. /api/agreement/config → 本地模拟响应，不发真实请求
    2. 其他所有 XHR → 正常发送，load 后记录 {url, method, status, requestBody, responseBody}
    3. /api/pcg/otp/login 且 code===0 → 发射登录成功消息
    """
    return r"""(function() {
  var BILI_NET  = "__BILI_NET__::";
  var BILI_LOGIN = "__BILI_LOGIN__::";

  var AGREEMENT_MOCK = JSON.stringify({
    request_id: "mock",
    timestamp: Date.now(),
    code: 0,
    message: "\u54CD\u5E94\u6210\u529F",
    data: { cooperation_mode: 0, agreement_switch: "OFF", privacy_tips_switch: "ON" },
    success: true
  });

  var _origOpen = XMLHttpRequest.prototype.open;
  var _origSend = XMLHttpRequest.prototype.send;
  var _origSetHeader = XMLHttpRequest.prototype.setRequestHeader;

  XMLHttpRequest.prototype.open = function(method, url) {
    this.__bili_url    = (typeof url === "string") ? url : String(url);
    this.__bili_method = method;
    this.__bili_mock   = this.__bili_url.indexOf("/api/agreement/config") !== -1;

    if (!this.__bili_mock) {
      return _origOpen.apply(this, arguments);
    }
    // mocked: 不调用真正的 open，后续 send 也不真正发出
  };

  XMLHttpRequest.prototype.setRequestHeader = function() {
    if (this.__bili_mock) return;
    return _origSetHeader.apply(this, arguments);
  };

  XMLHttpRequest.prototype.send = function(body) {
    var self = this;

    if (this.__bili_mock) {
      // ── 模拟 agreement/config ──
      setTimeout(function() {
        try {
          Object.defineProperty(self, "readyState",   { value: 4,   configurable: true });
          Object.defineProperty(self, "status",        { value: 200, configurable: true });
          Object.defineProperty(self, "statusText",    { value: "OK", configurable: true });
          Object.defineProperty(self, "responseText",  { value: AGREEMENT_MOCK, configurable: true });
          Object.defineProperty(self, "response",      { value: AGREEMENT_MOCK, configurable: true });
          self.getAllResponseHeaders = function() { return "content-type: application/json\r\n"; };
          self.getResponseHeader    = function(h) {
            return h.toLowerCase() === "content-type" ? "application/json" : null;
          };

          if (typeof self.onreadystatechange === "function") self.onreadystatechange();
          self.dispatchEvent(new Event("load"));
          self.dispatchEvent(new Event("loadend"));

          console.log(BILI_NET + JSON.stringify({
            url: self.__bili_url, method: self.__bili_method,
            status: 200, requestBody: null,
            responseBody: AGREEMENT_MOCK, mocked: true
          }));
        } catch (e) { console.error("[bili-mock] agreement mock error:", e); }
      }, 10);
      return;
    }

    // ── 真实请求：附加 load 监听 ──
    this.addEventListener("load", function() {
      try {
        var entry = {
          url:          self.__bili_url,
          method:       self.__bili_method,
          status:       self.status,
          requestBody:  body,
          responseBody: self.responseText
        };
        console.log(BILI_NET + JSON.stringify(entry));

        // 登录成功检测
        var u = self.__bili_url || "";
        if (u.indexOf("/api/pcg/otp/login") !== -1) {
          var resp = JSON.parse(self.responseText);
          if (resp && resp.code === 0) {
            console.log(BILI_LOGIN + self.responseText);
          }
        }
      } catch (e) {}
    });

    return _origSend.apply(this, arguments);
  };
})();
"""


class BilibiliBrowser(WebBrowser):
    """QWebEngine 浏览器：加载 B站 登录页并捕获登录结果。"""

    def __init__(
        self,
        game_id: str = DEFAULT_GAME_ID,
        app_key: str = DEFAULT_APP_KEY,
        sdk_ver: str = DEFAULT_SDK_VER,
    ):
        super().__init__("bilibili", True)
        self.logger = setup_logger()
        self._captured: Optional[Dict[str, Any]] = None
        self._login_url = _build_login_url(game_id, app_key, sdk_ver)

        # 注入 XHR 拦截脚本（在文档创建前）
        self.add_init_script(_build_intercept_js(), name="bili_xhr_intercept")

    def verify(self, url: str) -> bool:
        # 登录靠 JS console 回调，不靠 URL 跳转
        return False

    def on_console_message(
        self,
        level,
        message: str,
        lineNumber: int,
        sourceID: str,
        page=None,
    ):
        if not isinstance(message, str):
            return

        # 网络日志（调试用）
        if message.startswith(BILI_NET_PREFIX):
            payload = message[len(BILI_NET_PREFIX):]
            self.logger.debug(f"[bili-net] {payload[:500]}")
            return

        # 登录成功
        if message.startswith(BILI_LOGIN_PREFIX):
            payload = message[len(BILI_LOGIN_PREFIX):]
            try:
                data = json.loads(payload)
            except Exception:
                self.logger.warning(f"[bili-login] JSON 解析失败: {payload[:200]}")
                return

            self._captured = data
            self.result = data
            self.logger.info("已捕获 Bilibili 登录响应，准备退出浏览器")
            # 延迟 teardown，避免在 console 回调栈内直接销毁
            QTimer.singleShot(0, self.cleanup)

    def cleanup(self):
        super().cleanup()


class BilibiliLogin:
    """封装 BilibiliBrowser 的登录流程。"""

    def __init__(
        self,
        game_id: str = DEFAULT_GAME_ID,
        app_key: str = DEFAULT_APP_KEY,
        sdk_ver: str = DEFAULT_SDK_VER,
    ):
        self.logger = setup_logger()
        self.game_id = game_id
        self.app_key = app_key
        self.sdk_ver = sdk_ver
        self._active_browser: Optional[BilibiliBrowser] = None

    def web_login(self, on_complete=None) -> Optional[Dict[str, Any]]:
        """启动浏览器登录。

        同步模式：阻塞至登录完成，返回登录响应 dict。
        异步模式（on_complete 非 None）：立即返回 None，登录完成后回调。
        """
        browser = BilibiliBrowser(
            game_id=self.game_id,
            app_key=self.app_key,
            sdk_ver=self.sdk_ver,
        )
        browser.set_url(browser._login_url)
        resp = browser.run()

        if resp is None:
            # 异步模式：主事件循环已运行，保持强引用防止 GC
            self._active_browser = browser
            if on_complete is not None:
                def _on_async_done(b):
                    self._active_browser = None
                    try:
                        result = b.result
                        if isinstance(result, dict) and result:
                            on_complete(result)
                        else:
                            on_complete(None)
                    except Exception:
                        self.logger.exception("Bilibili 异步登录回调失败")
                        on_complete(None)

                browser._async_completion_callback = _on_async_done
            return None

        # 同步模式
        return resp if isinstance(resp, dict) else None

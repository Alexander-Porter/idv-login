# coding=UTF-8
"""Bilibili (哔哩哔哩) 网页登录渠道。

登录流程：QWebEngine 打开 sdk.biligame.com/login/ → 用户 OTP 登录 → 拦截响应 → SAUTH 换 token。
"""
from __future__ import annotations

import time
import json
from typing import Any, Dict, Optional

import channelmgr
from envmgr import genv
import app_state
from logutil import setup_logger

from channelHandler.channelUtils import buildSAUTH, postSignedData, getShortGameId
from channelHandler.bilibiliLogin.bilibiliChannel import BilibiliLogin, call_auto_login


class bilibiliChannel(channelmgr.channel):
    def __init__(
        self,
        login_info: dict,
        user_info: dict = {},
        ext_info: dict = {},
        device_info: dict = {},
        create_time: int = int(time.time()),
        last_login_time: int = 0,
        name: str = "",
        game_id: str = "",
        loginResp: Optional[Dict[str, Any]] = None,
        uuid: str = "",
    ) -> None:
        super().__init__(
            login_info,
            user_info,
            ext_info,
            device_info,
            create_time,
            last_login_time,
            name,
            uuid=uuid,
        )
        self.logger = setup_logger()
        self.crossGames = False
        self.game_id = game_id
        self.loginResp: Optional[Dict[str, Any]] = loginResp
        self.biliLogin = BilibiliLogin()

    # ── 序列化 / 反序列化 ────────────────────────────────────

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            login_info=data.get("login_info", {}),
            user_info=data.get("user_info", {}),
            ext_info=data.get("ext_info", {}),
            device_info=data.get("device_info", {}),
            create_time=data.get("create_time", int(time.time())),
            last_login_time=data.get("last_login_time", 0),
            name=data.get("name", ""),
            game_id=data.get("game_id", ""),
            loginResp=data.get("loginResp"),
            uuid=data.get("uuid", ""),
        )

    def before_save(self):
        if self.loginResp is not None:
            json.dumps(self.loginResp)

    # ── 登录状态 ──────────────────────────────────────────────

    def _get_login_data(self) -> Optional[Dict[str, Any]]:
        """从 loginResp 中提取 data 字段（兼容 data 在根级或嵌套）。"""
        if not isinstance(self.loginResp, dict):
            return None
        data = self.loginResp.get("data")
        if isinstance(data, dict):
            return data
        # 某些响应格式中 uid/access_key 直接在根级
        if "uid" in self.loginResp and "access_key" in self.loginResp:
            return self.loginResp
        return None

    def is_token_valid(self) -> bool:
        data = self._get_login_data()
        if not data:
            return False
        access_key = str(data.get("access_key") or "").strip()
        if not access_key:
            return False
        # 检查过期时间（留 5 分钟安全余量）
        expires = data.get("expires")
        if expires is not None:
            try:
                exp_ts = int(expires)
                if exp_ts < int(time.time()) + 300:
                    return False
            except (ValueError, TypeError):
                pass
        return True

    def validate_token_online(self) -> bool:
        """通过 auto.login API 验证并刷新 token。

        auto.login 响应为根级格式（无 data 包裹，无 access_key/expires），
        成功表示当前 access_key 仍有效。
        更新用户信息（uid/uname/face），并延长 expires 30 天。
        """
        data = self._get_login_data()
        if not data:
            return False
        access_key = str(data.get("access_key") or "").strip()
        if not access_key:
            return False
        try:
            resp = call_auto_login(access_key)
            if not isinstance(resp, dict) or resp.get("code") != 0:
                self.logger.warning(f"Bilibili auto.login 刷新失败: {resp}")
                return False

            self.logger.info("Bilibili auto.login 刷新成功")
            # auto.login 返回根级字段（uid/uname/face等），不含 access_key/expires
            for key in ("uid", "uname", "face"):
                if key in resp and resp[key] is not None:
                    data[key] = resp[key]
            # access_key 验证通过，延长过期时间 30 天
            data["expires"] = int(time.time()) + 30 * 86400
            return True
        except Exception as e:
            self.logger.error(f"Bilibili auto.login 请求异常: {e}")
            return False

    # ── 登录 ──────────────────────────────────────────────────

    def request_user_login(self, on_complete=None):
        genv.set("GLOB_LOGIN_UUID", self.uuid)

        def _process_resp(resp):
            if not resp:
                self.loginResp = None
                return False
            self.loginResp = resp
            data = self._get_login_data()
            if data:
                uname = str(data.get("uname") or "")
                if uname and not self.name:
                    self.name = uname
            return True

        if on_complete is not None:
            def _on_done(resp):
                try:
                    success = _process_resp(resp)
                except Exception:
                    self.logger.exception("Bilibili 异步登录处理失败")
                    success = False
                on_complete(success)

            self.biliLogin.web_login(on_complete=_on_done)
            return

        resp = self.biliLogin.web_login()
        return _process_resp(resp)

    # ── UniSDK 数据 ──────────────────────────────────────────

    def get_uniSdk_data(self, game_id: str = "", on_complete=None):
        genv.set("GLOB_LOGIN_UUID", self.uuid)
        if not game_id:
            game_id = self.game_id
        if not game_id:
            raise RuntimeError("bilibili 缺少 game_id")

        short_game_id = getShortGameId(game_id)

        if not self.is_token_valid():
            # token 过期或不存在：先尝试 auto.login 刷新
            has_key = bool(
                self._get_login_data()
                and str(self._get_login_data().get("access_key") or "").strip()
            )
            refreshed = has_key and self.validate_token_online()

            if not refreshed:
                # 刷新失败，需要重新浏览器登录
                if on_complete is not None:
                    def _on_login_done(success):
                        if success and self.is_token_valid():
                            try:
                                result = self._build_unisdk_result(short_game_id)
                                on_complete(result)
                            except Exception as e:
                                self.logger.error(f"Bilibili UniSDK error: {e}")
                                on_complete(None)
                        else:
                            on_complete(None)
                    self.request_user_login(on_complete=_on_login_done)
                    return None
                else:
                    self.request_user_login()

        return self._build_unisdk_result(short_game_id)

    def _build_unisdk_result(self, short_game_id: str) -> Optional[Dict[str, Any]]:
        data = self._get_login_data()
        if not data:
            raise RuntimeError("bilibili loginResp 数据缺失")

        uid = str(data.get("uid") or "")
        access_key = str(data.get("access_key") or "")
        if not uid or not access_key:
            raise RuntimeError(f"bilibili 缺少 uid 或 access_key: uid={uid}")

        sauth_data = buildSAUTH(
            login_channel="bilibili_sdk",
            app_channel="bilibili_sdk",
            uid=uid,
            session=access_key,
            game_id=short_game_id,
            sdk_version="6.8.0",
        )
        return postSignedData(sauth_data, short_game_id)

# coding=UTF-8
"""
 Copyright (c) 2025 KKeygen & fwilliamhe

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
import time
import base64
import channelmgr

from cloudRes import CloudRes
from envmgr import genv
import app_state
from logutil import setup_logger
from channelHandler.channelUtils import getShortGameId
from channelHandler.huaLogin.huaChannel import HuaweiLogin


class huaweiLoginResponse:
    def __init__(self, rawJson: dict) -> None:
        self.playerLevel = rawJson.get("playerLevel")
        self.unionId = rawJson.get("unionId")
        self.openIdSign = rawJson.get("openIdSign")
        self.openId = rawJson.get("openId")
        self.gameAuthSign = rawJson.get("gameAuthSign")
        self.playerId = rawJson.get("playerId")
        self.ts = str(rawJson.get("ts"))
    
    def __str__(self) -> str:
        return f"playerLevel:{self.playerLevel},unionId:{self.unionId},openIdSign:{self.openIdSign},openId:{self.openId},gameAuthSign:{self.gameAuthSign},playerId:{self.playerId},ts:{self.ts}"


class huaweiChannel(channelmgr.channel):

    def __init__(
        self,
        login_info: dict,
        user_info: dict = {},
        ext_info: dict = {},
        device_info: dict = {},
        create_time: int = int(time.time()),
        last_login_time: int = 0,
        name: str = "",
        refreshToken: str = "",
        game_id: str = "",
    ) -> None:
        super().__init__(
            login_info,
            user_info,
            ext_info,
            device_info,
            create_time,
            last_login_time,
            name,
        )
        self.refreshToken = refreshToken
        self.logger = setup_logger()
        self.crossGames = False
        # To DO: Use Actions to auto update game_id-app_id mapping by uploading an APK.
        # this is a temporary solution for IDV
        self.game_id = game_id
        real_game_id = getShortGameId(game_id)
        # find cloudConfig
        cloudRes = CloudRes()
        res = cloudRes.get_channelData(self.channel_name, real_game_id)
        if res == None:
            self.logger.error(f"Failed to get channel config for {self.name}")
            raise Exception(f"游戏{real_game_id}-渠道{self.channel_name}暂不支持，请参照教程联系开发者发起添加请求。")
        self.huaweiLogin = HuaweiLogin(res.get(self.channel_name), self.refreshToken, real_game_id)
        self.realGameId = real_game_id
        self.uniBody = None
        self.uniData = None
        self.session: huaweiLoginResponse = None

    def request_user_login(self, on_complete=None):
        genv.set("GLOB_LOGIN_UUID", self.uuid)

        if on_complete is not None:
            def _on_done(_success):
                self.refreshToken = self.huaweiLogin.refreshToken
                on_complete(self.refreshToken is not None)
            self.huaweiLogin.newOAuthLogin(on_complete=_on_done)
            return

        self.huaweiLogin.newOAuthLogin()
        self.refreshToken = self.huaweiLogin.refreshToken
        return self.refreshToken != None

    def _get_session(self, on_complete=None):
        """获取session数据，支持异步模式。
        
        当 accessToken 过期需要重新OAuth登录时，会异步弹出浏览器窗口。
        """
        def _do_get_session():
            """实际获取 session 的逻辑"""
            try:
                data = self.huaweiLogin.initAccountData()
                if data is None:
                    self.logger.error("Failed to get session data: initAccountData returned None")
                    self.refreshToken = None
                    return None
                res = huaweiLoginResponse(data)
                self.session = res
                return res
            except Exception as e:
                self.logger.error(f"{e}")
                self.logger.error(f"Failed to get session data")
                self.refreshToken = None
                return None

        # 检查是否需要重新 OAuth
        if self.huaweiLogin.is_token_expired():
            if on_complete is not None:
                # 异步模式：先完成 OAuth，再获取 session
                def _on_login_done(success):
                    if success:
                        result = _do_get_session()
                        on_complete(result)
                    else:
                        on_complete(None)
                self.request_user_login(on_complete=_on_login_done)
                return None
            else:
                # 同步模式不支持，因为浏览器必须在主事件循环中运行
                self.logger.error("华为渠道 token 过期，需要异步重新登录")
                return None
        
        # token 有效，直接获取 session
        result = _do_get_session()
        if on_complete is not None:
            on_complete(result)
            return None
        return result

    def is_token_valid(self):
        if self.refreshToken is None:
            self.logger.info(f"Token is invalid for {self.name}")
            return False
        return True

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
            refreshToken=data.get("refreshToken", None),
            game_id=data.get("game_id", ""),
        )

    def _build_extra_unisdk_data(self) -> str:
        fd = app_state.fake_device
        res = {
            "SAUTH_STR": "",
            "SAUTH_JSON": "",
        }
        extra_data = {
            "anonymous": "",
            "get_access_token": "0",
            "extra_data": self._get_extra_data(),
            "timestamp": self.session.ts,
            "realname": json.dumps({"realname_type": 0, "duration": 0}),
        }
        res.update(extra_data)
        json_data = {
            "extra_data": extra_data.get("extra_data"),
            "get_access_token": "0",
            "sdk_udid": fd["udid"],
            "realname": extra_data.get("realname"),
        }
        json_data.update(self.uniBody)

        str_data = json_data.copy()
        str_data.update({"username": self.uniSDKJSON["username"]})
        str_data = "&".join([f"{k}={v}" for k, v in str_data.items()])

        res["SAUTH_STR"] = base64.b64encode(str_data.encode()).decode()
        res["SAUTH_JSON"] = base64.b64encode(json.dumps(json_data).encode()).decode()
        return json.dumps(res)
    
    def _get_extra_data(self):
        self.logger.info(f"{getShortGameId(self.game_id)}")
        if getShortGameId(self.game_id)=='g37':
            self.logger.info(f"游戏{getShortGameId(self.game_id)}-需要HMS AccessToken, 二次登录中")
            ext={}
            ext["playerLevel"]=str(self.session.playerLevel)
            sdk={}
            sdk["transtition_version"]=1
            sdk["openId"]=self.session.openId
            sdk["accessToken"]=self.huaweiLogin.accessToken
            ext["sdk_info"]=sdk
            return json.dumps(ext)

        else:
            return str(self.session.playerLevel)

    def get_uniSdk_data(self, game_id: str = "", on_complete=None):
        """获取 UniSDK 登录数据，支持异步模式。
        
        当 token 过期需要重新 OAuth 时，会异步弹出浏览器窗口。
        
        Args:
            game_id: 游戏ID
            on_complete: 异步回调函数，接收登录数据或 None
        """
        genv.set("GLOB_LOGIN_UUID", self.uuid)
        if game_id == "":
            game_id = self.game_id
        self.logger.info(f"Get unisdk data for {self.name}")
        import channelHandler.channelUtils as channelUtils

        def _build_unisdk_data():
            """构建 UniSDK 数据的实际逻辑"""
            self.uniBody = channelUtils.buildSAUTH(
                self.channel_name,
                self.channel_name,
                self.session.playerId,
                self.session.gameAuthSign,
                getShortGameId(game_id),
                "6.1.0.301",
                {
                    "anonymous": "",
                    "get_access_token": "0",
                    "extra_data": self._get_extra_data(),
                    "timestamp": str(self.session.ts),
                    "realname": json.dumps({"realname_type": 0, "duration": 0}),
                },
            )
            fd = app_state.fake_device
            self.uniData = channelUtils.postSignedData(self.uniBody,getShortGameId(game_id),False)
            self.uniSDKJSON = json.loads(
                base64.b64decode(self.uniData["unisdk_login_json"]).decode()
            )
            res = {
                "user_id": self.session.playerId,
                "token": base64.b64encode(self.session.gameAuthSign.encode()).decode(),
                "login_channel": self.channel_name,
                "udid": fd["udid"],
                "app_channel": self.channel_name,
                "sdk_version": "6.1.0.301",
                "jf_game_id": getShortGameId(game_id),
                "pay_channel": self.channel_name,
                "extra_data": "",
                "extra_unisdk_data": self._build_extra_unisdk_data(),
                "gv": "157",
                "gvn": "1.5.80",
                "cv": "a1.5.0",
            }
            return res

        def _on_session_ready(session):
            """session 准备好后的回调"""
            if session is None:
                if on_complete:
                    on_complete(None)
                return None
            try:
                result = _build_unisdk_data()
                if on_complete:
                    on_complete(result)
                return result
            except Exception as e:
                self.logger.error(f"构建 UniSDK 数据失败: {e}")
                if on_complete:
                    on_complete(None)
                return None

        # 先检查 refreshToken
        if not self.is_token_valid():
            if on_complete is not None:
                # 异步模式：先完成登录
                def _on_login_done(success):
                    if success:
                        self._get_session(on_complete=_on_session_ready)
                    else:
                        on_complete(None)
                self.request_user_login(on_complete=_on_login_done)
                return None
            else:
                # 同步模式无法支持完整的 OAuth 流程
                self.request_user_login()
                if not self.is_token_valid():
                    return None

        # 获取 session（可能需要异步重新 OAuth）
        if on_complete is not None:
            self._get_session(on_complete=_on_session_ready)
            return None
        
        # 同步模式
        if self._get_session() is None:
            return None
        return _build_unisdk_data()

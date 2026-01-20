# coding=UTF-8
"""
 Copyright (c) 2025 Alexander-Porter & fwilliamhe

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
import string
import time
import base64
import channelmgr

from envmgr import genv
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
            Exception(f"游戏{real_game_id}-渠道{self.channel_name}暂不支持，请参照教程联系开发者发起添加请求。")
            return
        self.huaweiLogin = HuaweiLogin(res.get(self.channel_name), self.refreshToken, real_game_id)
        self.realGameId = real_game_id
        self.uniBody = None
        self.uniData = None
        self.session: huaweiLoginResponse = None

    def request_user_login(self):
        genv.set("GLOB_LOGIN_UUID", self.uuid)
        self.huaweiLogin.newOAuthLogin()
        self.refreshToken = self.huaweiLogin.refreshToken
        self.logger.debug(self.refreshToken)
        return self.refreshToken != None

    def _get_session(self):
        try:
            data = self.huaweiLogin.initAccountData()
            res = huaweiLoginResponse(data)
        except Exception as e:
            self.logger.error(f"{e}")
            self.logger.error(f"Failed to get session data {data}")
            self.refreshToken = None
            return None
        self.session = res
        return res

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
        fd = genv.get("FAKE_DEVICE")
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
            self.logger.info(self.session)
            self.logger.info(self.huaweiLogin.accessToken)
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

    def get_uniSdk_data(self, game_id: str = ""):
        genv.set("GLOB_LOGIN_UUID", self.uuid)
        if game_id == "":
            game_id = self.game_id
        self.logger.info(f"Get unisdk data for {self.name}")
        import channelHandler.channelUtils as channelUtils

        if not self.is_token_valid():
            self.request_user_login()
        if self._get_session() == None:
            return None
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
        fd = genv.get("FAKE_DEVICE")
        self.logger.info(json.dumps(self.uniBody))
        self.uniData = channelUtils.postSignedData(self.uniBody,getShortGameId(game_id),False)
        self.logger.info(f"Get unisdk data for {self.uniData}")
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

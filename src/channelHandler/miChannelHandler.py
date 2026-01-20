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
import time
import base64
import channelmgr

from cloudRes import CloudRes
from envmgr import genv
from logutil import setup_logger
from channelHandler.miLogin.miChannel import MiLogin
from channelHandler.channelUtils import getShortGameId


class miChannel(channelmgr.channel):
    def __init__(
        self,
        login_info: dict,
        user_info: dict = {},
        ext_info: dict = {},
        device_info: dict = {},
        create_time: int = int(time.time()),
        last_login_time: int = 0,
        name: str = "",
        oAuthData: dict = {},
        game_id: str = "",
        account_type: int = 4,
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
        self.oAuthData = oAuthData
        self.logger = setup_logger()
        self.crossGames = False
        # Done: Use Actions to auto update game_id-app_id mapping by uploading an APK.
        self.game_id = game_id
        real_game_id = getShortGameId(game_id)
        cloudRes = CloudRes()
        res = cloudRes.get_channelData(self.channel_name, real_game_id)
        if res == None:
            self.logger.error(f"Failed to get channel config for {self.name}")
            Exception(
                f"游戏{real_game_id}-渠道{self.channel_name}暂不支持，请参照教程联系开发者发起添加请求。"
            )
            return
        self.miLogin = MiLogin(
            res.get(self.channel_name).replace("mi_", ""), self.oAuthData, account_type
        )
        self.realGameId = real_game_id
        self.uniBody = None
        self.uniData = None
        self.account_type = account_type

    def request_user_login(self):
        genv.set("GLOB_LOGIN_UUID", self.uuid)
        self.miLogin.webLogin()
        self.oAuthData = self.miLogin.oauthData
        self.account_type = self.miLogin.account_type
        self.logger.info(f"小米登录类型：{self.account_type}")
        self.logger.debug(self.oAuthData)
        return self.oAuthData != None

    def _get_session(self):
        try:
            data = self.miLogin.initAccountData()
        except Exception as e:
            self.logger.error(f"Failed to get session data {e}")
            self.oAuthData = None
            self.request_user_login()
            data = self.miLogin.initAccountData()
            if data is None:
                raise Exception("Failed to get session data after re-login")
        return data["appAccountId"], data["session"]

    def is_token_valid(self):
        if self.oAuthData is None:
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
            oAuthData=data.get("oAuthData", None),
            game_id=data.get("game_id", ""),
            account_type=data.get("account_type", 4),
        )

    def get_sdk_udid(self):
        return self.oAuthData["uuid"]

    def _build_extra_unisdk_data(self) -> str:
        res = {
            "SAUTH_STR": "",
            "SAUTH_JSON": "",
            "extra_data": "",
            "realname": "",
            "get_access_token": "1",
        }
        extra = json.dumps({"adv_channel": "0", "adid": "0"})
        realname = json.dumps({"realname_type": 0, "age": 18})
        json_data = {
            "extra_data": extra,
            "get_access_token": "1",
            "sdk_udid": self.get_sdk_udid(),
            "realname": realname,
        }
        json_data.update(self.uniBody)

        str_data = json_data.copy()
        str_data.update({"username": self.uniSDKJSON["username"]})
        str_data = "&".join([f"{k}={v}" for k, v in str_data.items()])

        res["SAUTH_STR"] = base64.b64encode(str_data.encode()).decode()
        res["SAUTH_JSON"] = base64.b64encode(json.dumps(json_data).encode()).decode()
        res["extra_data"] = extra
        res["realname"] = realname
        return json.dumps(res)

    def get_uniSdk_data(self, game_id: str = ""):
        genv.set("GLOB_LOGIN_UUID", self.uuid)
        if game_id == "":
            game_id = self.game_id
        self.logger.info(f"Get unisdk data for {self.name}")
        import channelHandler.channelUtils as channelUtils

        if not self.is_token_valid():
            self.request_user_login()
        appAccountId, session = self._get_session()
        self.uniBody = channelUtils.buildSAUTH(
            self.channel_name,
            self.channel_name,
            str(appAccountId),
            session,
            getShortGameId(game_id),
            "3.3.0.7",
        )
        fd = genv.get("FAKE_DEVICE")
        self.uniData = channelUtils.postSignedData(
            self.uniBody, getShortGameId(game_id)
        )
        self.logger.info(f"Get unisdk data for {self.uniData}")
        self.uniSDKJSON = json.loads(
            base64.b64decode(self.uniData["unisdk_login_json"]).decode()
        )
        res = {
            "user_id": self.get_sdk_udid(),
            "token": base64.b64encode(session.encode()).decode(),
            "login_channel": self.channel_name,
            "udid": fd["udid"],
            "app_channel": self.channel_name,
            "sdk_version": "3.0.5.002",
            "jf_game_id": getShortGameId(game_id),
            "pay_channel": self.channel_name,
            "extra_data": "",
            "extra_unisdk_data": self._build_extra_unisdk_data(),
            "gv": "157",
            "gvn": "1.5.80",
            "cv": "a1.5.0",
        }
        return res

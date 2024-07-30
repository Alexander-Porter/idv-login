# coding=UTF-8
"""
 Copyright (c) 2024 Alexander-Porter & fwilliamhe

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

from envmgr import genv
from logutil import setup_logger
from channelHandler.channelUtils import getShortGameId
from channelHandler.huaLogin.huaChannel import HuaweiLogin

MI_APP_ID_MAP={"h55":"111"}

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
        refreshToken: str="",
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
        self.logger = setup_logger(__name__)
        self.logger.info(f"Create a new huaChannel with name {self.name} and {refreshToken}")
        self.crossGames = True
        #To DO: Use Actions to auto update game_id-app_id mapping by uploading an APK.
        #this is a temporary solution for IDV
        self.game_id = game_id
        real_game_id = getShortGameId(game_id)
        #if(real_game_id not in MI_APP_ID_MAP):
        #    raise Exception(f"游戏代号 {game_id} 尚未支持。")
        self.huaweiLogin = HuaweiLogin(MI_APP_ID_MAP[real_game_id], self.refreshToken)
        self.realGameId = real_game_id
        self.uniBody = None
        self.uniData = None

    def request_user_login(self):
        self.huaweiLogin.newOAuthLogin()
        self.refreshToken = self.huaweiLogin.refreshToken
        self.logger.debug(self.refreshToken)
        return self.refreshToken!=None

    def _get_session(self):
        try:
            data = self.huaweiLogin.initAccountData()
        except Exception as e:
            self.logger.error(f"Failed to get session data {e}")
            self.refreshToken = None
            return None
        self.last_login_time = int(time.time())
        return data

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
            transferKey=data.get("transferKey", None),
            game_id=data.get("game_id", ""),
        )

    def _build_extra_unisdk_data(self)->str:
        res={
            "SAUTH_STR":"",
            "SAUTH_JSON":"",
            "extra_data":"",
            "realname":"",
            "get_access_token":"1",
        }
        extra=json.dumps({"adv_channel":"0","adid":"0"})
        realname=json.dumps({"realname_type":0,"age":18})
        json_data={"extra_data":extra,"get_access_token":"1","sdk_udid":self.refreshToken["uuid"],"realname":realname}
        json_data.update(self.uniBody)

        str_data=json_data.copy()
        str_data.update({"username":self.uniSDKJSON["username"]})
        str_data="&".join([f"{k}={v}" for k, v in str_data.items()])

        res["SAUTH_STR"]=base64.b64encode(str_data.encode()).decode()
        res["SAUTH_JSON"]=base64.b64encode(json.dumps(json_data).encode()).decode()
        res["extra_data"]=extra
        res["realname"]=realname
        return json.dumps(res)


    def get_uniSdk_data(self):
        self.logger.info(f"Get unisdk data for {self.name}")
        import channelHandler.channelUtils as channelUtils
        
        if not self.is_token_valid():
            self.request_user_login()
        channelData = self._get_session()
        if channelData is None:
            self.logger.error(f"Failed to get session data for {self.name}")
            return False
        self.uniBody = channelUtils.buildSAUTH(
            "huawei",
            "huawei",
            str(channelData["appAccountId"]),
            channelData["session"],
            self.realGameId,
        )
        fd = genv.get("FAKE_DEVICE")
        self.uniData = channelUtils.postSignedData(self.uniBody,self.realGameId)
        self.logger.info(f"Get unisdk data for {self.uniData}")
        self.uniSDKJSON=json.loads(base64.b64decode(self.uniData["unisdk_login_json"]).decode())
        res = {
            "user_id": self.refreshToken["uuid"],
            "token": base64.b64encode(channelData["session"].encode()).decode(),
            "login_channel": "huawei",
            "udid": fd["udid"],
            "app_channel": "huawei",
            "sdk_version": "6.1.0.301",
            "jf_game_id": self.game_id,  # maybe works for all games
            "pay_channel": "huawei",
            "extra_data": "",
            "extra_unisdk_data": self._build_extra_unisdk_data(),
            "gv": "157",
            "gvn": "1.5.80",
            "cv": "a1.5.0",
        }
        return res

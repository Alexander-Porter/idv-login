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
import string
import time
import base64

import requests
import channelmgr

from envmgr import genv
from logutil import setup_logger
from channelHandler.channelUtils import getShortGameId
from channelHandler.wechatLogin.wechatChannel import WechatLogin

class myappVeriftResp:
    def __init__(self, rawJson: dict) -> None:
        try:
            self.atk = rawJson.get("atk")
            self.atk_expire = rawJson.get("atk_expire")
            self.first = rawJson.get("first")
            self.judgeLoginData = rawJson.get("judgeLoginData")
            self.msg = rawJson.get("msg")
            self.openid = rawJson.get("openid")
            self.pf = rawJson.get("pf")
            self.pfKey = rawJson.get("pfKey")
            self.regChannel = rawJson.get("regChannel")
            self.retk = rawJson.get("retk")
            self.rtk = rawJson.get("rtk")
            self.visitorLoginData = rawJson.get("visitorLoginData")
        except Exception as e:
            self.msg = "Failed to parse json"
            print(e)

    def __dict__(self):
        return {
            "atk": self.atk,
            "atk_expire": self.atk_expire,
            "first": self.first,
            "judgeLoginData": self.judgeLoginData,
            "msg": self.msg,
            "openid": self.openid,
            "pf": self.pf,
            "pfKey": self.pfKey,
            "regChannel": self.regChannel,
            "retk": self.retk,
            "rtk": self.rtk,
            "visitorLoginData": self.visitorLoginData,
        }

class wechatChannel(channelmgr.channel):

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
        refreshToken: str = "",

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
        self.logger = setup_logger()
        self.crossGames = False
        cloudRes = genv.get("CLOUD_RES")

        self.game_id = game_id
        real_game_id = getShortGameId(game_id)
        res = cloudRes.get_channelData(self.channel_name, real_game_id)
        if res == None:
            self.logger.error(f"Failed to get channel config for {self.name}")
            return False
        
        self.wx_appid = res.get(self.channel_name).get("wx_appid")
        self.channel= res.get(self.channel_name).get("channel")
        
        self.refreshToken = refreshToken
        self.wechatLogin = WechatLogin(self.wx_appid,self.channel, self.refreshToken)
        self.realGameId = real_game_id
        self.uniBody = None
        self.uniData = None
        self.session: myappVeriftResp = None
        


    def request_user_login(self):
        if self.refreshToken == "":
            genv.set("GLOB_LOGIN_UUID", self.uuid)
            resp=self.vivoLogin.webLogin()
            if resp==None:
                self.session=None
                return False
            self.session=myappVeriftResp(resp)
            return self.session!=None
        else:
            r=requests.get(f"https://api.weixin.qq.com/sns/oauth2/refresh_token?appid={self.wx_appid}&grant_type=refresh_token&refresh_token={self.refreshToken}")
            if not r.status_code==200:
                self.logger.error(f"Refresh token 过期: {r.text}")
                self.refreshToken=""
                return self.request_user_login()
            self.session.retk=r.json().get("refresh_token")
            self.session.atk=r.json().get("access_token")
            self.refreshToken=self.session.retk
            return True

    def is_token_valid(self):
        return self.session!=None

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
            refreshToken=data.get("refreshToken", None),
            session=data.get("session", None),
        )

    def _build_extra_unisdk_data(self) -> str:
        fd = genv.get("FAKE_DEVICE")
        res = {
            "SAUTH_STR": "",
            "SAUTH_JSON": "",
        }
        
        extra_data = {
            "login_type": 8,
            "session_id": "hy_gameid",
            "session_type": "wc_actoken",
            "openid": self.session.openid,
            "openkey": self.session.atk,
            "pf": self.session.pf,
            "pfkey": self.session.pfKey,
            "zoneid": "1",
        }

        res.update(extra_data)
        json_data = {
            "extra_data": extra_data.get("extra_data"),
            "get_access_token": "1",
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

    def get_uniSdk_data(self, game_id: str = ""):
        genv.set("GLOB_LOGIN_UUID", self.uuid)
        if game_id == "":
            game_id = self.game_id
        self.logger.info(f"Get unisdk data for {self.name}")
        import channelHandler.channelUtils as channelUtils

        if not self.is_token_valid():
            self.request_user_login()

        self.uniBody = channelUtils.buildSAUTH(
            self.channel_name,
            self.channel_name,
            self.session.openid,
            self.session.atk,
            getShortGameId(game_id),
            "2.2.3",
            {
                "realname": json.dumps({"realname_type": 0, "age": 22}),
            },
        )
        fd = genv.get("FAKE_DEVICE")
        self.logger.info(json.dumps(self.uniBody))
        self.uniData = channelUtils.postSignedData(self.uniBody,getShortGameId(game_id),True)

        self.logger.info(f"Get unisdk data for {self.uniData}")
        self.uniSDKJSON = json.loads(
            base64.b64decode(self.uniData["unisdk_login_json"]).decode()
        )
        res = {
            "user_id": self.session.openid,
            "token": self.session.atk,
            "login_channel": self.channel_name,
            "udid": fd["udid"],
            "app_channel": self.channel_name,
            "sdk_version": "2.2.3",
            "jf_game_id": getShortGameId(game_id),
            "pay_channel": self.channel_name,
            "extra_data": "",
            "extra_unisdk_data": self._build_extra_unisdk_data(),
            "gv": "157",
            "gvn": "1.5.80",
            "cv": "a1.5.0",
        }
        return res

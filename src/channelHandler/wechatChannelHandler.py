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

import requests
import channelmgr

from cloudRes import CloudRes
from envmgr import genv
import app_state
from logutil import setup_logger
from ssl_utils import should_verify_ssl
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

    def __json__(self):
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
        session: myappVeriftResp = None,
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
            uuid,
        )
        self.logger = setup_logger()
        self.crossGames = False
        cloudRes = CloudRes()

        self.game_id = game_id
        real_game_id = getShortGameId(game_id)
        res = cloudRes.get_channelData(self.channel_name, real_game_id)
        if res == None:
            self.logger.error(f"Failed to get channel config for {self.name}")
            return False

        self.wx_appid = res.get(self.channel_name).get("wx_appid")
        self.channel = res.get(self.channel_name).get("channel")

        self.wechatLogin = WechatLogin(self.wx_appid, self.channel, game_id=game_id)
        self.realGameId = real_game_id
        self.uniBody = None
        self.uniData = None
        self.session: myappVeriftResp = myappVeriftResp(session) if session != None else None

    def request_user_login(self, on_complete=None):
        """请求用户登录，支持异步模式。
        
        Args:
            on_complete: 异步回调函数，接收登录结果 (True/False)
        """
        def _do_login():
            if self.session == None:
                genv.set("GLOB_LOGIN_UUID", self.uuid)
                resp = self.wechatLogin.webLogin()
                if resp == None:
                    self.session = None
                    return False
                self.session = myappVeriftResp(resp)
                #get user info
                #https://api.weixin.qq.com/sns/userinfo?access_token=ACCESS_TOKEN&openid=OPENID
                try:
                    r = requests.get(
                        f"https://api.weixin.qq.com/sns/userinfo?access_token={self.session.atk}&openid={self.session.openid}",
                        verify=should_verify_ssl()
                    )
                    r.encoding="utf-8"
                    self.name=r.json().get("nickname")
                except:
                    pass
            else:
                self.logger.info(f"刷新 ac-token，当前时间: {int(time.time())}，过期时间: {self.last_login_time+self.session.atk_expire}")
                r = requests.get(
                    f"https://api.weixin.qq.com/sns/oauth2/refresh_token?appid={self.wx_appid}&grant_type=refresh_token&refresh_token={self.session.rtk}",
                    verify=should_verify_ssl()
                )
                if not r.status_code == 200:
                    self.logger.error(f"Refresh token 过期，疑似被顶号，重新唤起扫码登录。status={r.status_code}")
                    self.session = None
                    return _do_login()  # 递归调用内部函数
                self.session.rtk = r.json().get("refresh_token")
                self.session.atk = r.json().get("access_token")
                self.logger.info("微信 ac-token 刷新成功")
            if self.session!=None:
                self.last_login_time=int(time.time())
                return True
            return False

        if on_complete is not None:
            # 异步模式：在线程中执行登录
            import threading
            def _async_login():
                result = _do_login()
                on_complete(result)
            thread = threading.Thread(target=_async_login)
            thread.start()
            return None
        else:
            # 同步模式
            return _do_login()

    def is_token_valid(self):
        #	/sns/auth
        if self.session != None and self.last_login_time+self.session.atk_expire > int(time.time()):
            r = requests.get(
                    f"https://api.weixin.qq.com/sns/auth?access_token={self.session.atk}&openid={self.session.openid}",
                    verify=should_verify_ssl()
                )
            result = r.json()
            return result.get("errcode")==0
        else:
            return False

    def before_save(self):
        self.session_json = self.session.__json__()
        return super().before_save()

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
            session=data.get("session_json", None),
            uuid=data.get("uuid", ""),
        )

    def _get_extra_data(self):
        self.logger.info(f"{getShortGameId(self.game_id)}")
        return json.dumps(
                {
                    "login_type": 8,
                    "session_id": "hy_gameid",
                    "session_type": "wc_actoken",
                    "openid": self.session.openid,
                    "openkey": self.session.atk,
                    "pf": self.session.pf,
                    "pfkey": self.session.pfKey,
                    "zoneid": "1",
                })


    def _build_extra_unisdk_data(self) -> str:
        fd = app_state.fake_device
        res = {
            "SAUTH_STR": "",
            "SAUTH_JSON": "",
        }

        extra_data = {
            "extra_data": self._get_extra_data(),
            "realname": json.dumps({"realname_type": 0, "age": 22}),
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

    def get_uniSdk_data(self, game_id: str = "", on_complete=None):
        """获取 UniSDK 登录数据，支持异步模式。
        
        当 token 过期需要重新登录时，可异步执行登录流程。
        
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
                self.session.openid,
                self.session.atk,
                getShortGameId(game_id),
                "2.2.2",
                {
                    "get_access_token": "1",
                    "extra_data": self._get_extra_data(),
                },
            )
            fd = app_state.fake_device
            self.logger.info(json.dumps(self.uniBody))
            self.uniData = channelUtils.postSignedData(
                self.uniBody, getShortGameId(game_id), True
            )

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
                "sdk_version": "2.2.2",
                "jf_game_id": getShortGameId(game_id),
                "pay_channel": self.channel_name,
                "extra_data": "",
                "extra_unisdk_data": self._build_extra_unisdk_data(),
                "gv": "157",
                "gvn": "1.5.80",
                "cv": "a1.5.0",
            }
            return res

        def _on_login_ready():
            """登录完成后构建数据"""
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

        # 检查 token 是否有效
        if not self.is_token_valid():
            if on_complete is not None:
                # 异步模式：先完成登录
                def _on_login_done(success):
                    if success:
                        _on_login_ready()
                    else:
                        on_complete(None)
                self.request_user_login(on_complete=_on_login_done)
                return None
            else:
                # 同步模式
                self.request_user_login()
                if not self.is_token_valid():
                    return None

        # 同步模式或 token 有效时直接构建数据
        if on_complete is not None:
            return _on_login_ready()
        return _build_unisdk_data()

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
import time
from channelmgr import channel
from envmgr import genv
from logutil import setup_logger

class miChannel(channel):
    def __init__(self,
                 login_info: dict,
                 user_info: dict= {},
                 ext_info: dict= {},
                 device_info: dict= {},
                 create_time:int =int(time.time()),
                 last_login_time:int=0,
                 name:str="",
                 ) -> None:
        super().__init__(login_info, user_info, ext_info, device_info, create_time, last_login_time, name)
        self.logger = setup_logger(__name__)
        self.logger.info(f"Create a new miChannel with name {self.name}")

    def _request_user_login(self):
        #唤起网页登录。然后自行处理后续的登录流程
        self.logger.info(f"Requesting user login")
        pass


    def _refresh_session(self):
        #刷新session
        self.logger.info(f"Refreshing session")
        pass
    def is_session_valid(self):
        #检查session是否有效，可以通过`https://mgbsdk.matrix.netease.com/h55/sdk/uni_sauth `
        self.logger.info(f"Checking session valid")
        pass
        return True

    def get_uniSdk_data(self):
        #获取UniSdk数据，用于扫码
        self.logger.info(f"Getting UniSdk data")
        return super().get_uniSdk_data()
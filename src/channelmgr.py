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

import os
import json
import time

import requests

from envmgr import genv
from logutil import setup_logger


class channel:
    def __init__(
        self,
        login_info: dict,
        user_info: dict = {},
        ext_info: dict = {},
        device_info: dict = {},
        create_time: int = int(time.time()),
        last_login_time: int = 0,
        name: str = "",
    ) -> None:
        self.login_info = login_info
        self.user_info = user_info
        self.ext_info = ext_info
        self.device_info = device_info
        self.exchange_data = {
            "device": device_info,
            "ext_info": ext_info,
            "user": user_info,
        }

        self.create_time = create_time
        self.last_login_time = last_login_time
        self.uuid = f"{login_info['login_channel']}-{login_info['code']}"
        self.channel_name = login_info["login_channel"]
        if name is "":
            self.name = self.uuid
        else:
            self.name = name

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
        )

    def login(self):
        self.last_login_time = int(time.time())
        return self.exchange_data

    def get_non_sensitive_data(self):
        return {
            "create_time": self.create_time,
            "last_login_time": self.last_login_time,
            "uuid": self.uuid,
            "name": self.name,
        }


class ChannelManager:
    def __init__(self):
        self.logger = setup_logger(__name__)
        self.channels = []
        if os.path.exists(genv.get("FP_CHANNEL_RECORD")):
            with open(genv.get("FP_CHANNEL_RECORD"), "r") as file:
                try:
                    data = json.load(file)
                    self.logger.info("解析渠道服登录信息成功！")
                    for item in data:
                        self.channels.append(channel.from_dict(item))
                except:
                    with open(genv.get("FP_CHANNEL_RECORD"), "w") as f:
                        json.dump([], f)
        else:
            with open(genv.get("FP_CHANNEL_RECORD"), "w") as f:
                json.dump([], f)
            self.channels = []

    def save_records(self):
        with open(genv.get("FP_CHANNEL_RECORD"), "w") as file:
            data = [channel.__dict__ for channel in self.channels]
            json.dump(data, file)
        self.logger.info("渠道服登录信息已更新")

    def list_channels(self):
        return sorted(
            [channel.get_non_sensitive_data() for channel in self.channels],
            key=lambda x: x["last_login_time"],
            reverse=True,
        )

    def import_from_scan(self, login_info: dict, exchange_info: dict):
        tmp_channel: channel = channel(
            login_info,
            exchange_info["user"],
            exchange_info["ext_info"] if "ext_info" in exchange_info.keys() else {},
            exchange_info["device"] if "device" in exchange_info.keys() else {},
        )
        self.channels.append(tmp_channel)
        self.save_records()

    def login(self, uuid: str):
        for channel in self.channels:
            if channel.uuid == uuid:
                data = channel.login()
                self.save_records()
                return data
        return False

    def rename(self, uuid: str, new_name: str):
        for channel in self.channels:
            if channel.uuid == uuid:
                channel.name = new_name
                self.save_records()
                return True
        return False

    def delete(self, uuid: str):
        for i, channel in enumerate(self.channels):
            if channel.uuid == uuid:
                del self.channels[i]
                self.save_records()
                return True
        return False

    def build_query_res(self, uuid: str):
        for channel in self.channels:
            if channel.uuid == uuid:
                data = channel.login_info
                return data
        return None

    def simulate_confirm(self, channel:channel, scanner_uuid: str, game_id: str):
        data = {
            "uuid": scanner_uuid,
            "user_id": channel.user_info["id"],
            "token": channel.user_info["token"],
            "login_channel": channel.ext_info["src_app_channel2"],
            "udid": channel.ext_info["src_udid"],
            "app_channel": channel.ext_info["src_app_channel"],
            "sdk_version": channel.ext_info["src_jf_game_id"],
            "jf_game_id": channel.ext_info["src_jf_game_id"],
            "pay_channel": channel.ext_info["src_pay_channel"],
            "extra_data": "",
            "extra_unisdk_data":channel.ext_info["extra_unisdk_data"],
            "game_id": game_id,
            "gv": "157",
            "gvn": "1.5.80",
            "cv": "a1.5.0",
        }
        body="&".join([f"{k}={v}" for k, v in data.items()])
        self.logger.info(f"模拟确认请求: {body}")
        r=requests.post("https://service.mkey.163.com/mpay/api/qrcode/confirm_login", data=body, headers={"Content-Type": "application/x-www-form-urlencoded"},verify=False)
        self.logger.info(f"模拟确认请求返回: {r.json()}")
        if r.status_code == 200:
            return r.json()
        else:
            genv.set("CHANNEL_ACCOUNT_SELECTED", "")
            return False


    def simulate_scan(self, uuid: str, scanner_uuid: str, game_id: str):
        for channel in self.channels:
            if channel.uuid == uuid:
                data = {
                    "uuid": scanner_uuid,
                    "login_channel": channel.channel_name,
                    "app_channel": channel.channel_name,
                    "pay_channel": channel.channel_name,
                    "game_id": game_id,
                    "gv": "157",
                    "gvn": "1.5.80",
                    "cv": "a1.5.0",
                }
                try:
                    r = requests.get(
                        "https://service.mkey.163.com/mpay/api/qrcode/scan", params=data,verify=False
                    )
                    self.logger.info(f"模拟扫码请求: {r.json()}")
                    if r.status_code == 200:
                        return self.simulate_confirm(channel, scanner_uuid, game_id)
                    else:
                        genv.set("CHANNEL_ACCOUNT_SELECTED", "")
                        return False
                except:
                    self.logger.error(f"模拟扫码请求失败", stack_info=True, exc_info=True)
                    genv.set("CHANNEL_ACCOUNT_SELECTED", "")
                    return False
        return None

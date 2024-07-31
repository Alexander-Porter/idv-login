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
import random
import time

import requests

from envmgr import genv
from const import manual_login_channels
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
        self.crossGames = True
        if name == "":
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

    def get_uniSdk_data(self):
        return {
            "user_id": self.user_info["id"],
            "token": self.user_info["token"],
            "login_channel": self.ext_info["src_app_channel2"],
            "udid": self.ext_info["src_udid"],
            "app_channel": self.ext_info["src_app_channel"],
            "sdk_version": self.ext_info["src_jf_game_id"],
            "jf_game_id": self.ext_info["src_jf_game_id"],
            "pay_channel": self.ext_info["src_pay_channel"],
            "extra_data": "",
            "extra_unisdk_data": self.ext_info["extra_unisdk_data"],
            "gv": "157",
            "gvn": "1.5.80",
            "cv": "a1.5.0",
        }

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
        from channelHandler.miChannelHandler import miChannel
        from channelHandler.huaChannelHandler import huaweiChannel

        if os.path.exists(genv.get("FP_CHANNEL_RECORD")):
            with open(genv.get("FP_CHANNEL_RECORD"), "r") as file:
                try:
                    data = json.load(file)
                    for item in data:
                        if "login_info" in item.keys():
                            channel_name = item["login_info"]["login_channel"]
                            if channel_name == "xiaomi_app":

                                tmpChannel: miChannel = miChannel.from_dict(item)
                                # if tmpChannel.is_token_valid():
                                self.channels.append(tmpChannel)
                                # else:
                                #    self.logger.error(f"渠道服登录信息失效: {tmpChannel.name}")
                            elif channel_name == "huawei":
                                tmpChannel: huaweiChannel = huaweiChannel.from_dict(item)
                                # if tmpChannel.is_token_valid():
                                self.channels.append(tmpChannel)
                                # else:
                                #    self.logger.error(f"渠道服登录信息失效: {tmpChannel.name}")
                            else:
                                self.channels.append(channel.from_dict(item))
                except:
                    self.logger.error(f"读取渠道服登录信息失败。已经清空渠道服信息。",exc_info=True,stack_info=True)
                    with open(genv.get("FP_CHANNEL_RECORD"), "w") as f:
                        json.dump([], f)
        else:
            with open(genv.get("FP_CHANNEL_RECORD"), "w") as f:
                json.dump([], f)
            self.channels = []

    def save_records(self):
        with open(genv.get("FP_CHANNEL_RECORD"), "w") as file:
            oldData = [channel.__dict__.copy() for channel in self.channels]
            data = oldData.copy()
            for channel_data in data:
                to_be_deleted = []
                for key in channel_data.keys():
                    mini_data = {"data": channel_data[key]}
                    try:
                        json.dumps(mini_data)

                    except:
                        to_be_deleted.append(key)
                for key in to_be_deleted:
                    del channel_data[key]
            json.dump(data, file)
        self.logger.info("渠道服登录信息已更新")

    def list_channels(self,game_id: str):
        return sorted(
            [channel.get_non_sensitive_data()  for channel in self.channels if game_id == "" or channel.crossGames or (channel.game_id == game_id)],
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
        if login_info["login_channel"] in [i["channel"] for i in manual_login_channels]:
            self.logger.error(f"不支持扫码的渠道服: {login_info['login_channel']}")
            return False
        self.channels.append(tmp_channel)
        self.save_records()

    def manual_import(self, channle_name: str, game_id: str):
        tmpData = {
            "code": str(random.randint(100000, 999999)),
            "src_client_type": 1,
            "login_channel": channle_name,
            "src_client_country_code": "CN",
        }
        if channle_name == "xiaomi_app":
            from channelHandler.miChannelHandler import miChannel

            tmp_channel: miChannel = miChannel(tmpData,game_id=game_id)
        if channle_name == "huawei":
            from channelHandler.huaChannelHandler import huaweiChannel

            tmp_channel: huaweiChannel = huaweiChannel(tmpData,game_id=game_id)
        try:
            tmp_channel.request_user_login()
            if tmp_channel.is_token_valid():
                self.channels.append(tmp_channel)
                self.save_records()
                return True
            else:
                self.logger.error(f"手动导入失败: {tmp_channel.name}")
                return False
        except:
            self.logger.error(f"手动导入失败", stack_info=True, exc_info=True)
            return False

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

    def query_channel(self, uuid: str):
        for channel in self.channels:
            if channel.uuid == uuid:
                return channel
        return None

    def simulate_confirm(self, channel: channel, scanner_uuid: str, game_id: str):
        channel_data = channel.get_uniSdk_data()
        if not channel_data:
            genv.set("CHANNEL_ACCOUNT_SELECTED", "")
            return False
        channel_data["uuid"] = scanner_uuid
        channel_data["game_id"] = game_id
        body = "&".join([f"{k}={v}" for k, v in channel_data.items()])
        r = requests.post(
            "https://service.mkey.163.com/mpay/api/qrcode/confirm_login",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            verify=False,
        )
        self.logger.info(f"模拟确认请求返回: {r.json()}")
        if r.status_code == 200:
            channel.last_login_time = int(time.time())
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
                    if scanner_uuid=="Kinich":
                        return channel.get_uniSdk_data()
                    r = requests.get(
                        "https://service.mkey.163.com/mpay/api/qrcode/scan",
                        params=data,
                        verify=False,
                    )
                    self.logger.info(f"模拟扫码请求: {r.json()}")
                    if r.status_code == 200:
                        return self.simulate_confirm(channel, scanner_uuid, game_id)
                    else:
                        genv.set("CHANNEL_ACCOUNT_SELECTED", "")
                        return False
                except:
                    self.logger.error(
                        f"模拟扫码请求失败", stack_info=True, exc_info=True
                    )
                    genv.set("CHANNEL_ACCOUNT_SELECTED", "")
                    return False
        return None

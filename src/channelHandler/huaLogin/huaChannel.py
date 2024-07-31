import binascii
import json
import os
import random
import string
import time

import requests
import sys
from faker import Faker
import random
import webbrowser
import pyperclip as cb
from envmgr import genv
#from logutil import setup_logger
from faker import Faker
#from channelHandler.huaLogin.consts import DEVICE,QRCODE_BODY
from channelHandler.huaLogin.consts import DEVICE,hms_client_id,hms_redirect_uri,hms_scope,COMMON_PARAMS
from channelHandler.huaLogin.utils import get_authorization_code,exchange_code_for_token,get_access_token

DEVICE_RECORD = 'huawei_device.json'
import win32pipe
import win32file
import pywintypes

PIPE_NAME = r'\\.\pipe\idv-login'



class HuaweiLogin:

    def __init__(self, channelConfig, refreshToken=None):

        os.chdir(os.path.join(os.environ["PROGRAMDATA"], "idv-login"))
        #self.logger = setup_logger(__name__)
        self.channelConfig = channelConfig
        self.refreshToken = refreshToken
        self.accessToken=None
        self.lastLoginTime = 0
        self.expiredTime = 0
        if os.path.exists(DEVICE_RECORD):
            with open(DEVICE_RECORD, "r") as f:
                self.device = json.load(f)
        else:
            self.device = self.makeFakeDevice()
            with open(DEVICE_RECORD, "w") as f:
                json.dump(self.device, f)

    def makeFakeDevice(self):
        fake = Faker()
        device = DEVICE.copy()
        manufacturers = ["Samsung", "Huawei", "Xiaomi", "OPPO"]
        #deviceId is a 64 char string 
        import random

        device["deviceId"] = ''.join(random.choice('abcdef' + string.digits) for _ in range(64))
        device["brand"] = random.choice(manufacturers)
        device['romVersion']=fake.lexify(
        text="V???IR release-keys", letters="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    )
        device["androidVersion"]=random.choice(["12","13","11"])
        device["manufacturer"]=device["brand"]
        device["phoneType"] = fake.lexify(text="SM-????", letters="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
        return device
    
    def newOAuthLogin(self):
        client_id = str(self.channelConfig["app_id"])
        redirect_uri = hms_redirect_uri
        scope = hms_scope
        auth_url, code_verifier = get_authorization_code(client_id, redirect_uri, scope)
        webbrowser.open(auth_url)
        pipe=genv.get("PIPE")
        win32pipe.ConnectNamedPipe(pipe, None)
        print("Client connected.")

        try:
            result, message = win32file.ReadFile(pipe, 65534)
            if message:
                code = message.decode()
                print(f"Received: {code}")
        except pywintypes.error as e:
            print(f"Failed to read/write from/to named pipe: {e}")

        print("Disconnecting pipe...")
        win32pipe.DisconnectNamedPipe(pipe)

        #解析url-schema获取code
        try:
            code = code.split("code=")[1]
        except Exception as e:
            print("获取code失败")
            return False
        #进行urldecode
        import urllib.parse
        code=urllib.parse.unquote(code)
        code=code.replace(" ","+")


        token_response = exchange_code_for_token(client_id, code, code_verifier, redirect_uri)
        self.refreshToken = token_response.get("refresh_token")
        self.lastLoginTime=int(time.time())
        self.expiredTime=self.lastLoginTime+token_response.get("expires_in")
        self.accessToken=token_response.get("access_token")

    def refreshToken(self):
        if self.refreshToken == None:
            return False
        
    def initAccountData(self) -> object:
        if self.refreshToken == None:
            return None
        #access_token=get_access_token(self.channelConfig["app_id"],self.channelConfig["client_secret"],self.refreshToken)
        #we dont know client secret lol.
        #get now time
        now=int(time.time())
        if now>=self.expiredTime:
            self.newOAuthLogin()
        if self.accessToken==None:
            return None
        #build urlencoded k-v body
        url = "https://jgw-drcn.jos.dbankcloud.cn/gameservice/api/gbClientApi"

        headers = {
            "User-Agent": f"com.huawei.hms.game/6.14.0.300 (Linux; Android 12; {self.device.get('phoneType')}) RestClient/7.0.6.300",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        body = COMMON_PARAMS.copy()
        body.update(self.device)
        body["method"] = "client.hms.gs.getGameAuthSign"
        body["extraBody"] = f'json={{"appId":"{str(self.channelConfig["app_id"])}"}}'
        body["accessToken"]=self.accessToken

        response = requests.post(url, headers=headers, data=body,verify=False)
        print(response.text)
        return response.json()

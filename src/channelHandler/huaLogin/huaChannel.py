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

#from channelHandler.huaLogin.consts import DEVICE,QRCODE_BODY
from channelHandler.huaLogin.consts import DEVICE,hms_client_id,hms_redirect_uri,hms_scope
from channelHandler.huaLogin.utils import get_authorization_code,exchange_code_for_token

DEVICE_RECORD = 'huawei_device.json'
import win32pipe
import win32file
import pywintypes

PIPE_NAME = r'\\.\pipe\idv-login'



class HuaweiLogin:

    def __init__(self, appId, oauthData=None):

        os.chdir(os.path.join(os.environ["PROGRAMDATA"], "idv-login"))
        #self.logger = setup_logger(__name__)
        self.appId = appId
        self.refreshToken = ""
        if os.path.exists(DEVICE_RECORD):
            with open(DEVICE_RECORD, "r") as f:
                self.device = json.load(f)
        else:
            self.device = self.makeFakeDevice()
            with open(DEVICE_RECORD, "w") as f:
                json.dump(self.device, f)

    def makeFakeDevice(self):
        device = DEVICE.copy()
        manufacturers = ["Samsung", "Huawei", "Xiaomi", "OPPO"]
        device["deviceBrand"] = random.choice(manufacturers)
        return device
    
    def newOAuthLogin(self):
        client_id =hms_client_id
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




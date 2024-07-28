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

#from logutil import setup_logger

#from channelHandler.huaLogin.consts import DEVICE,QRCODE_BODY
from channelHandler.huaLogin.consts import DEVICE,QRCODE_BODY,IV_LENGTH,KEY_LENGTH
from channelHandler.huaLogin.utils import encrypt,decrypt,getPublicKey,buildHwidCommonParams

DEVICE_RECORD = 'huawei_device.json'

class HuaweiLogin:

    def __init__(self, appId, oauthData=None):

        os.chdir(os.path.join(os.environ["PROGRAMDATA"], "idv-login"))
        #self.logger = setup_logger(__name__)
        self.appId = appId
        self.oauthData = oauthData
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
    


    def newQrCodeLogin(self):

        
        url = "https://id.cloud.huawei.com/DimensionalCode/getqrInfo"
        headers = {
            "Authorization": "1722168834179",
            "Connection": "Keep-Alive",
            "Host": "id.cloud.huawei.com",
            "User-Agent": "com.huawei.hms.commonkit/6.14.0.300 (Linux; Android 12; SM-S9080) RestClient/7.0.3.300",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept-Encoding": "gzip"
        }
        params=buildHwidCommonParams()
        data=QRCODE_BODY.copy()
        
        response = requests.post(url, headers=headers, params=params, data=data,verify=False)
        respCookies = response.cookies
        print(response.text)
        self.qrCodeListener(response.json().get("qrToken"),respCookies,callback=self.callback)
    def callback(self,result):
        print("Login successful:", result)
    def qrCodeListener(self,token,cookies,callback):
        url = "https://id1.cloud.huawei.com/DimensionalCode/async"
        headers = {
            "Authorization": str(int(time.time())),
            "Connection": "Keep-Alive",
            "Host": "id1.cloud.huawei.com",
            "User-Agent": "com.huawei.hms.commonkit/6.14.0.300 (Linux; Android 12; SM-S9080) RestClient/7.0.3.300",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept-Encoding": "gzip"
        }

        data = {
            "qrToken": token
        }
        dictCookies = requests.utils.dict_from_cookiejar(cookies)
        while True:
            response = requests.post(url, headers=headers, data=data,cookies=dictCookies,verify=False)
            print(response.text)
            if response.status_code == 200:
                result = response.json()
                if result.get("resultCode") == "0":
                    callback(result)
                    break
                elif result.get("resultCode") == "103000200":
                    print("Please login.")
                else:
                    print("Login failed.")
                    print(result)
            time.sleep(5)

    def generateTransferKeyPair(self):
        self.transferKey=binascii.hexlify(os.urandom(int(KEY_LENGTH/2))).decode('ascii')
        self.transferKeyId=f"D-{binascii.hexlify(os.urandom(16)).decode('ascii')}"

    def initTransferKey(self):
        self.generateTransferKeyPair()
        self.iv=os.urandom(int(IV_LENGTH/2))
        self.key=getPublicKey()
        #use public key (hex-encoded) to encrypt transfer key
        import rsa
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives import hashes
        pubBytes=binascii.unhexlify(self.key)
        pubkey =serialization.load_der_public_key(pubBytes, backend=default_backend())
        encrypted = pubkey.encrypt(
        binascii.unhexlify(self.transferKey),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
        self.encryptedTransferKey = binascii.hexlify(encrypted).decode('ascii').upper()
    
    def sendTransferKey(self):
        url = "https://hwid-drcn.platform.hicloud.com/IdmClientApi/v2/setTransferKey"
        params = buildHwidCommonParams()
        headers = {
            "Connection": "Keep-Alive",
            "Host": "hwid-drcn.platform.hicloud.com",
            "User-Agent": "com.huawei.hms.commonkit/6.14.0.300 (Linux; Android 12; SM-S9080) RestClient/7.0.3.300",
            "Content-Type": "application/json; charset=UTF-8",
            "Accept-Encoding": "gzip"
        }
        data = {
            "version": DEVICE["Version"],
            "transferKey": self.encryptedTransferKey,
            "languageCode": "zh-CN",
            "clientType": "1",
            "transferKeyID": self.transferKeyId,
            "sceneID": 1
        }
        response = requests.post(url, params=params, headers=headers, json=data)
        return response




import binascii
import json
import os
import random
import string
import time
import gevent
import requests
import sys
from faker import Faker
import random
import webbrowser
import pyperclip as cb
from envmgr import genv
from logutil import setup_logger
from faker import Faker
#from channelHandler.huaLogin.consts import DEVICE,QRCODE_BODY
from channelHandler.huaLogin.consts import DEVICE,hms_client_id,hms_redirect_uri,hms_scope,COMMON_PARAMS
from channelHandler.huaLogin.utils import get_authorization_code,exchange_code_for_token,get_access_token
from channelHandler.channelUtils import G_clipListener
from channelHandler.WebLoginUtils import WebBrowser
from PyQt5.QtWebEngineCore import QWebEngineUrlRequestInterceptor,QWebEngineUrlRequestJob,QWebEngineUrlSchemeHandler
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtWidgets import QCheckBox,QComboBox,QInputDialog,QPushButton,QMessageBox
from AutoFillUtils import RecordMgr

DEVICE_RECORD = 'huawei_device.json'


class HuaweiBrowser(WebBrowser):
    def __init__(self):
        super().__init__("huawei", True)
        self.logger = setup_logger()
        

    async def handle_request(self, response):
        url = response.url
        if "oauth2/ajax/authorizeConfirm" in url:
            body=(await response.body()).decode("utf-8")
            data=json.loads(body)
            if data.get("isSuccess")=="true":
                res=data.get("code")
                new_res = "https://id1.cloud.huawei.com/CAS/portal/login.html"
                data.update({"code":new_res})
                self.logger.debug(f"Intercepted request: {url}")
                self.logger.debug(f"Intercepted response: {body}")
                if self.verify(res):
                    if self.parse_result(res):
                        await self.page.goto(new_res)
                        return

        if "id1.cloud.huawei.com/CAS/portal/login.html" in url:
            await self.page.wait_for_load_state("networkidle")
            self.logger.info("Handling login page")
            
    async def initialize(self):
        await super().initialize()
        self.page.on("response", self.handle_request)

     
    async def handle_url_change(self):
        self.logger.info("Handling URL change")
        await self.page.wait_for_load_state("networkidle")
        await self.page.evaluate("""
            console.log("Handling URL change");
            for (let ip of document.querySelectorAll('input')) {
                ip.setAttribute('autocomplete', 'on');
                console.log(ip);
            }
        """)
        

    def verify(self, url):
        return url.startswith("hms://")

    def parse_result(self, url):
        self.result = url
        return True


class HuaweiLogin:

    def __init__(self, channelConfig, refreshToken=None):

        os.chdir(os.path.join(os.environ["PROGRAMDATA"], "idv-login"))
        #self.logger = setup_logger()
        self.channelConfig = channelConfig
        self.refreshToken = refreshToken
        self.accessToken=None
        self.code_verifier=None
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
    
    def verify(self,code):
        return code.startswith("hms://")
    
    async def newOAuthLogin(self):
        client_id = str(self.channelConfig["app_id"])
        redirect_uri = hms_redirect_uri
        scope = hms_scope
        auth_url, self.code_verifier = get_authorization_code(client_id, redirect_uri, scope)
        huaWebLogin = HuaweiBrowser()
        await huaWebLogin.initialize()
        await huaWebLogin.set_url(auth_url)
        res = await huaWebLogin.run()
        await self.standardCallback(res)

    async def standardCallback(self, url, cookies={}):
        client_id = str(self.channelConfig["app_id"])
        redirect_uri = hms_redirect_uri
        scope = hms_scope
        code=""
        try:
            code = url.split("code=")[1]
        except Exception as e:
            print("获取code失败,Code为空")
            return False
        #进行urldecode
        import urllib.parse
        code=urllib.parse.unquote(code)
        code=code.replace(" ","+")
        token_response = exchange_code_for_token(client_id, code, self.code_verifier, redirect_uri)
        self.refreshToken = token_response.get("refresh_token")
        self.lastLoginTime=int(time.time())
        self.expiredTime=self.lastLoginTime+token_response.get("expires_in")
        self.accessToken=token_response.get("access_token")


    async def initAccountData(self) -> object:
        if self.refreshToken == None:
            return None
        #access_token=get_access_token(self.channelConfig["app_id"],self.channelConfig["client_secret"],self.refreshToken)
        #we dont know client secret lol.
        #get now time
        now=int(time.time())
        if now>=self.expiredTime:
            await self.newOAuthLogin()
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
        return response.json()

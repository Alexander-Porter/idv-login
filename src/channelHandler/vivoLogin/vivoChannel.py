import json
import os
import random
import string
import time
import channelHandler.miLogin.utils as utils
import requests
import sys
from faker import Faker
import random
import webbrowser
import pyperclip as cb

from channelHandler.miLogin.consts import DEVICE, DEVICE_RECORD, AES_KEY
from channelHandler.channelUtils import G_clipListener
from logutil import setup_logger
from ssl_utils import should_verify_ssl
from channelHandler.WebLoginUtils import WebBrowser
from PyQt5.QtWebEngineCore import (
    QWebEngineUrlRequestInterceptor,
    QWebEngineUrlRequestJob,
    QWebEngineUrlSchemeHandler,
)


class VivoBrowser(WebBrowser):
    def __init__(self, gamePackage):
        super().__init__("nearme_vivo", True)
        self.logger = setup_logger()
        self.gamePackage = gamePackage

    def verify(self, url: str) -> bool:
        return "openid" in self.parse_url_query(url).keys()

    def parseReslt(self, url):
        # get cookies
        u = f"https://joint.vivo.com.cn/h5/union/get?gamePackage={self.gamePackage}"
        self.logger.info(u)
        try:
            r = requests.get(u, cookies=self.cookies, verify=should_verify_ssl())
            self.result = r.json()
            return True
        except Exception as e:
            self.logger.error(e)
            self.result = {"code": -1, "msg": e}
            return False

    def parse_url_query(self, url):
        from urllib.parse import urlparse, parse_qs

        parsed_url = urlparse(url)
        query_dict = parse_qs(parsed_url.query)
        return query_dict


class VivoLogin:
    def __init__(self, gamePackage=""):
        os.chdir(os.path.join(os.environ["PROGRAMDATA"], "idv-login"))
        self.logger = setup_logger()
        self.gamePackage = gamePackage
        self.cookies = {}

    def webLogin(self):
        login_url = f"https://passport.vivo.com.cn/#/login?client_id=67&redirect_uri=https%3A%2F%2Fjoint.vivo.com.cn%2Fgame-subaccount-login%3Ffrom%3Dlogin"
        miBrowser = VivoBrowser(self.gamePackage)
        miBrowser.set_url(login_url)
        resp = miBrowser.run()
        try:
            if resp.get("code") == 0:
                self.cookies = miBrowser.cookies.copy()
                return resp.get("data")
            else:
                self.logger.error(resp.get("msg"))
                return None
        except:
            self.logger.error(f"登录失败，原始响应{resp}")
            return None

    def loginSubAccount(self, subOpenId):
        data = {
            "noLoading": True,
            "subOpenId": subOpenId,
            "gamePackage": self.gamePackage,
        }
        header={
            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36 Edg/105.0.1343.27"
        }
        r = requests.post("https://joint.vivo.com.cn/h5/union/use",data=data,cookies=self.cookies,headers=header,verify=should_verify_ssl())
        try:
            resp=r.json()
            if resp.get("code") == 0:
                return resp.get("data")
            else:
                self.logger.error(resp.get("msg"))
                return None
        except:
            self.logger.exception(f"登录失败")
            return None

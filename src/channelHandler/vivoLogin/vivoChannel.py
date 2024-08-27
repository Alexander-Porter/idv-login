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
from channelHandler.WebLoginUtils import WebBrowser
from PyQt5.QtWebEngineCore import QWebEngineUrlRequestInterceptor,QWebEngineUrlRequestJob,QWebEngineUrlSchemeHandler



class VivoBrowser(WebBrowser):
    def __init__(self):
        super().__init__("nearme_vivo",True)
        self.logger = setup_logger(__name__)

    def verify(self, url: str) -> bool:
        return "openid" in self.parse_url_query(url).keys()

    def parseReslt(self, url):
        #get cookies
        u="https://joint.vivo.com.cn/h5/union/get?gamePackage="
        try:
            r=requests.get(u,cookies=self.cookies)
            self.result=r.json()
            return True
        except Exception as e:
            self.logger.error(e)
            self.result={
                "code":-1,
                "msg":e
            }
            return False

    def parse_url_query(self,url):
        from urllib.parse import urlparse, parse_qs
        parsed_url = urlparse(url)
        query_dict = parse_qs(parsed_url.query)
        return query_dict
    

class VivoLogin:
    def __init__(self):
        os.chdir(os.path.join(os.environ["PROGRAMDATA"], "idv-login"))
        self.logger = setup_logger(__name__)

    def webLogin(self):
        login_url = f"https://passport.vivo.com.cn/#/login?client_id=67&redirect_uri=https%3A%2F%2Fjoint.vivo.com.cn%2Fgame-subaccount-login%3Ffrom%3Dlogin"
        miBrowser=VivoBrowser()
        miBrowser.set_url(login_url)
        resp=(miBrowser.run())
        if resp.get("code")==0:
            return resp.get("data")
        else:
            self.logger.error(resp.get("msg"))
            return None

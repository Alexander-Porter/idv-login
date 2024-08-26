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
from channelHandler.WebLoginUtils import WebBroswer
from PyQt5.QtWebEngineCore import QWebEngineUrlRequestInterceptor,QWebEngineUrlRequestJob,QWebEngineUrlSchemeHandler



class VivoBroswer(WebBroswer):
    def __init__(self,name=""):
        super().__init__(f"nearme_vivo{name}",True)
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
    def __init__(self, name=""):
        os.chdir(os.path.join(os.environ["PROGRAMDATA"], "idv-login"))
        self.logger = setup_logger(__name__)
        self.name = name

    def webLogin(self):
        login_url = f"https://passport.vivo.com.cn/#/login?client_id=67&redirect_uri=https%3A%2F%2Fjoint.vivo.com.cn%2Fgame-subaccount-login%3Ffrom%3Dlogin"
        miBroswer=VivoBroswer(self.name)
        miBroswer.set_url(login_url)
        resp=(miBroswer.run())
        if resp.get("code")==0:
            return resp.get("data")
        else:
            self.logger.error(resp.get("msg"))
            return None

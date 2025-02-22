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
    class HuaweiRequestInterceptor(QWebEngineUrlSchemeHandler):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.parent = parent

        def requestStarted(self, info: QWebEngineUrlRequestJob):
            url = info.requestUrl().toString()
            print(f"Intercepted request: {url}")
            if url.startswith("hms://"):
                self.parent.invokeSaveAccountPwdPair()
                self.parent.notify(info.requestUrl())  # Notify the parent class

    def __init__(self):
        super().__init__("huawei",True)
        self.logger=setup_logger()
        self.intercept_request = self.HuaweiRequestInterceptor(self)
        self.profile.removeAllUrlSchemeHandlers()
        self.profile.installUrlSchemeHandler(b"hms", self.intercept_request)
        self.autoFillMgr=RecordMgr()
        self.records=self.autoFillMgr.list_records()
        #check genv for default account
        defaultAccount=genv.get(f"defaultAutoFill{genv.get('GLOB_LOGIN_UUID','')}",None)
        if defaultAccount:
            #make sure default account is in records and then put it in index 0
            if defaultAccount in self.records:
                self.records.remove(defaultAccount)
                self.records.insert(0,defaultAccount)
        self.autoFillCheckBox=QCheckBox("记住账号密码")
        self.toolBarLayout.addWidget(self.autoFillCheckBox)
        self.autoFillCheckBox.setChecked(genv.get("autoFill",False))
        self.autoFillCheckBox.stateChanged.connect(self.saveAutoFillOption)
        
        self.bypassCheckBox=QCheckBox("跳过二次验证")
        self.toolBarLayout.addWidget(self.bypassCheckBox)
        self.bypassCheckBox.setChecked(genv.get("bypass_double_check",False))
        self.bypassCheckBox.stateChanged.connect(self.saveByPassOption)

        #增加一个下拉菜单QComboBox
        self.accountComboBox=QComboBox()
        self.toolBarLayout.addWidget(self.accountComboBox)
        self.accountComboBox.addItems(self.records)
        self.accountComboBox.currentIndexChanged.connect(self.onAccountChanged)
        self.accountComboBox.textActivated.connect(self.onAccountChanged)

        #增加一个按钮，文本为“填充”
        self.fillButton=QPushButton("填充")
        self.toolBarLayout.addWidget(self.fillButton)
        self.fillButton.clicked.connect(self.onAccountChanged)

        self.deleteButton=QPushButton("删除")
        self.toolBarLayout.addWidget(self.deleteButton)
        self.deleteButton.clicked.connect(self.deleteAccount)

    def deleteAccount(self):
        account=self.accountComboBox.currentText()
        self.autoFillMgr.remove_record(account)
        self.accountComboBox.removeItem(self.accountComboBox.currentIndex())
        if len(self.records)>0:
            self.accountComboBox.setCurrentIndex(0)
        self.logger.info(f"删除账号{account}")

    def saveByPassOption(self):
        checked=self.bypassCheckBox.isChecked()
        if checked:
            #show warning, QMessagebox
            reply=QMessageBox.warning(self,"警告","跳过二次验证会使账号密码明文存储在本机内，存在安全风险。\n开启后，请不要将工作目录下的文件随意分享给他人。是否继续？",QMessageBox.Yes|QMessageBox.No)
            if reply==QMessageBox.No:
                self.bypassCheckBox.setChecked(False)
                return
        genv.set("bypass_double_check",checked,True)

    def onAccountChanged(self):
        #get account
        account=self.accountComboBox.currentText()
        #check if has * mask
        if "*" in account:
            #ask for full account
            if self.bypassCheckBox.isChecked():
                text,ok=QInputDialog.getText(self,"关闭二次验证","密码已被加密，请输入完整的账号来解密，本次解密后该账号不再需要二次验证。",text=account)
            else:
                text,ok=QInputDialog.getText(self,"二次验证","密码已被加密，请输入完整的账号来解密",text=account)
            if ok:
                #find password
                password=self.autoFillMgr.find_password(text)
                if password:
                    self.insertAcctPwd(text,password)
                    if self.bypassCheckBox.isChecked():
                        self.autoFillMgr.untruncate_username(text)
                else:
                    self.logger.info("未找到密码，账号输入错误或者未保存")
        else:
            #find password
            password=self.autoFillMgr.find_password(account)
            if password:
                self.insertAcctPwd(account,password)
            else:
                self.logger.info("未找到密码，账号输入错误或者未保存")

    def insertAcctPwd(self,account,password):
        js_code = f"""
            function inputVal(t,val){{
                let evt = document.createEvent('HTMLEvents');
                evt.initEvent('input', true, true);
                t.value=val;
                t.dispatchEvent(evt)
            }};
            (function() {{
                let inputs = document.querySelectorAll('input');
                let accountInput = Array.prototype.find.call(inputs, input => input.getAttribute('ht') === 'input_pwdlogin_account');
                let pwdInput = Array.prototype.find.call(inputs, input => input.getAttribute('ht') === 'input_pwdlogin_pwd');
                if (accountInput && pwdInput) {{
                    //activate
                    accountInput.focus();
                    inputVal(accountInput,"{account}");
                    pwdInput.focus();
                    inputVal(pwdInput,"{password}");
                    return true;
                }}
                return false;
            }})();
        """
        self.page.runJavaScript(js_code)
    def saveAutoFillOption(self):
        checked=self.autoFillCheckBox.isChecked()
        genv.set("autoFill",checked,True)

    def verify(self, url):
        return url.startswith("hms://")

    def parseReslt(self, url):
        self.result = url
        return True

    @pyqtSlot(bool)
    def on_load_finished(self, ok):
        if ok:
            if len(self.autoFillMgr.list_records())==1:
                pass



    def invokeSaveAccountPwdPair(self):
        if self.autoFillCheckBox.isChecked():
            js_code = r"""
                (function() {
                let inputs = document.querySelectorAll('input');
                let accountInput = Array.prototype.find.call(inputs, input => input.getAttribute('ht') === 'input_pwdlogin_account');
                let pwdInput = Array.prototype.find.call(inputs, input => input.getAttribute('ht') === 'input_pwdlogin_pwd');
                if (accountInput && pwdInput && accountInput.value && pwdInput.value) {
                    //build json
                    let json = {
                        account: accountInput.value,
                        pwd: pwdInput.value
                    };
                    return JSON.stringify(json);
                }
                return JSON.stringify({});
                })();
            """
            self.page.runJavaScript(js_code, self.js_callback)
        else:
            self.logger.info("未开启记住账密")

    def js_callback(self, result):
        if result:
            data=json.loads(result)
            #check key
            if "account" in data and "pwd" in data:
                if self.autoFillCheckBox.isChecked():
                    self.logger.info("读取账号密码成功")
                    if self.bypassCheckBox.isChecked():
                        record=self.autoFillMgr.add_untruncate_record(data["account"],data["pwd"])
                    else:
                        record=self.autoFillMgr.add_record(data["account"],data["pwd"])
                    genv.set(f"defaultAutoFill{genv.get('GLOB_LOGIN_UUID','')}",record.truncated_username,True)

    def notify(self, url):
        if self.verify(url.toString()):
            if self.parseReslt(url.toString()):
                self.cleanup()
                self.profile.removeAllUrlSchemeHandlers()

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
    
    def newOAuthLogin(self):
        client_id = str(self.channelConfig["app_id"])
        redirect_uri = hms_redirect_uri
        scope = hms_scope
        auth_url, self.code_verifier = get_authorization_code(client_id, redirect_uri, scope)
        huaWebLogin=HuaweiBrowser()
        huaWebLogin.set_url(auth_url)
        res=(huaWebLogin.run())
        self.standardCallback(res)

    def standardCallback(self, url, cookies={}):
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
        return response.json()

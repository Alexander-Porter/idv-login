import base64
import os
import time
import requests
import gevent

from logutil import setup_logger

#1106682786 is offerid
def sig_helper(magicValue="5C2F##3[6$^(68#%#D3E96;]35q#FB46",ts="1"):
    #用时间戳作为盐值，对magicValue进行md5
    from hashlib import md5
    return md5((ts+magicValue).encode())
    


class WechatLogin:
    def __init__(self,wx_appid,channel,refreshToken=""):
        os.chdir(os.path.join(os.environ["PROGRAMDATA"], "idv-login"))
        self.logger = setup_logger()
        self.wx_appid=wx_appid
        self.channel=channel
        self.refreshToken = refreshToken

    def webLogin(self):
        ts=str(int(time.time()*1000))
        qrcodeData = {
            "noncestr":"!!freeSoftwareDoNOTSell-idv-login!!"+ts,
            "scope":"snsapi_userinfo,snsapi_friend,snsapi_message",
            "wx_appid":self.wx_appid,
            "loginplatform":"2",
            "sig":sig_helper(ts=ts).hexdigest(),
            "appid":self.wx_appid,
            "timestamp":ts
        }
        
        r=requests.get(f"https://ysdk.qq.com/auth/wx_scan_code_login",params=qrcodeData)
        if not r.status_code==200 or not r.json()['ret']==0:
            self.logger.error(f"微信扫码请求创建失败: {r.text}")
            return None
        #删除响应json里的msg字段
        rjson=r.json()
        rjson.pop("msg")
        rjson.pop("ret")
        #https://open.weixin.qq.com/connect/sdk/qrconnect
        r=requests.get(f"https://open.weixin.qq.com/connect/sdk/qrconnect",params=rjson,
                       headers={"accept-encoding":"gzip",})
        #use utf-8
        r.encoding="utf-8"

        #get qrcode img
        qrcode=r.json().get("qrcode").get("qrcodebase64")
        uuid=r.json().get("uuid")

        with open("qrcode.png","wb") as f:
            f.write(base64.b64decode(qrcode))
        gevent.sleep(0.5)
        #不要阻塞
        import webbrowser
        webbrowser.open("qrcode.png")


        while True:
            r=requests.get(f"https://long.open.weixin.qq.com/connect/l/qrconnect?f=json&uuid={uuid}")
            print(r.text)
            if r.json().get("wx_code") != "":
                self.logger.info(f"扫码成功{r.json().get('wx_code')}")
                break
            gevent.sleep(1)

        verifyData={
            "channel":"00000000",
            "code":r.json().get("wx_code"),
            "offerid":self.channel,
            "platform":"desktop_m_wechat",
            "client_hope_switch":"1",
            "wx_appid":self.wx_appid,
            "version":"2.2.2",
            "sig":sig_helper(ts=ts).hexdigest(),
            "anti_hope_switch":"1",
            "appid":self.wx_appid,
            "timestamp":ts
        }
        r=requests.get("https://ysdk.qq.com/auth/wx_verify_code",params=verifyData)
        self.logger.debug(f"扫码校验结果: {r.text}")
        if not r.status_code==200 or not r.json()['ret']==0:
            self.logger.error(f"扫码校验失败: {r.text}")
            return None
        return r.json()



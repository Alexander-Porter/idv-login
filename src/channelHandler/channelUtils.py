import json
import random
import string
import hmac
import hashlib
import requests
from envmgr import genv

class CustomEncoder(json.JSONEncoder):
    def encode(self, obj):
        json_str = super().encode(obj)
        return json_str.replace('/', '\\/')

LOG_KEY="SvShWXDcmogbZJoU3YWe3Su3Ci-mCRcw"

def _get_my_ip():
        #get my IP
    try:
        return requests.get("https://api.ipify.org").text
    except Exception as e:
        return "127.0.0.1"

def get_sign_src(str1, str2, str3):
    str4 = ""
    replaced = str2.replace("://", "")
    if replaced.find("/") != -1:
        str4 = replaced[replaced.find("/"):]
    return str1.upper() + str4 + str3

def calcSign(url,method,data):
    src=get_sign_src(method,url,data)
    #sha256
    key=LOG_KEY
    return hmac.new(key.encode(), src.encode(), hashlib.sha256).hexdigest()

def buildSAUTH(login_channel, app_channel,uid,session,game_id,sdk_version,custom_data={}):
    fakeData = genv.get("FAKE_DEVICE")
    ip=_get_my_ip()
    data = {
        "gameid": game_id,#maybe works for all games
        "login_channel": login_channel,
        "app_channel": app_channel,
        "platform": "ad",
        "sdkuid": uid,
        "udid": fakeData["udid"],
        "sessionid": session,
        "sdk_version": sdk_version,
        "is_unisdk_guest": 0,
        "ip": ip,
        "aim_info": '{"tz":"+0800","tzid":"Asia\/Shanghai","aim":"'+ip+'","country":"CN"}',
        "source_app_channel": app_channel,
        "source_platform": "ad",
        "client_login_sn": "".join(random.choices((string.hexdigits), k=16)),
        "step": "".join(random.choices(string.digits, k=10)),
        "step2": "".join(random.choices(string.digits, k=9)),
        "hostid": 0,
        "sdklog": json.dumps(fakeData),
    }
    data.update(custom_data)
    return data


def postSignedData(data,game_id,need_custom_encode=False):
    url=f"https://mgbsdk.matrix.netease.com/{game_id}/sdk/uni_sauth"
    method="POST"
    if need_custom_encode:
        data=json.dumps(data,cls=CustomEncoder)
    else:
        data=json.dumps(data)
    headers={"X-Client-Sign":calcSign(url,method,data),
             "Content-Type":"application/json",
             "User-Agent":"Dalvik/2.1.0 (Linux; U; Android 12; M2102K1AC Build/V417IR)",}
    r=requests.post(url,data=data,headers=headers,verify=False)
    return r.json()

def getShortGameId(game_id):
    return game_id.split("-")[-1]

#jsodn=r'''{"gameid":"h55","login_channel":"huawei","app_channel":"huawei","platform":"ad","sdkuid":"2850086000509138399","udid":"237157c94854463c","sessionid":"VYGPlWGwh7bra1iarfCv2RwDJ4SBaULPXOgq1jlObmVQyvXkulwv5CbdLNbOg5UW8anB\/SP\/ZMKA55kcKYyZnNuWW+3axFECRo\/ExKBLcS44xsIa4pbwRxjV97eJn2T5CQDoU3r2aNEdmTfAxKbH8QUdKy4IL6P1oGUrrCQXPe2WA+I4NS6FGOPn4KBZf1Gko2l\/N6FklYqjyJq7w9lAkBDj9EwAaAH5IfTMymyzh9euwvcINRwfEtTUi76eq\/2+AnMW8NKZfTAliDt+yoE2nFGKdB9p1cGEdBXAPgskhWPeJyXYznCYRa\/X8SBiwtiuWspnIqTIQpsHEdrRvx2dLw==","sdk_version":"6.1.0.301","is_unisdk_guest":0,"ip":"117.182.131.79","aim_info":"{\"tz\":\"+0800\",\"tzid\":\"Asia\\\/Shanghai\",\"aim\":\"117.182.131.79\",\"country\":\"CN\"}","source_app_channel":"huawei","source_platform":"ad","extra_data":"1","get_access_token":"1","anonymous":"","timestamp":"1722358017656","realname":"{\"realname_type\":0,\"duration\":0}","client_login_sn":"ebb2b4f469be39777498b3eb5bc44242","step":"-707443943","step2":"1354881653","hostid":0,"sdklog":"{\"device_model\":\"BLA-AL00\",\"os_name\":\"android\",\"os_ver\":\"12\",\"udid\":\"237157c94854463c\",\"app_ver\":\"175\",\"imei\":\"\",\"country_code\":\"CN\",\"is_emulator\":1,\"is_root\":1,\"oaid\":\"\"}"}'''
#print(calcSign("https://mgbsdk.matrix.netease.com/h55/sdk/uni_sauth","POST",(jsodn)))
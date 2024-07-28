import json
import os
import random
import string
import time
from Crypto.Cipher import AES
import binascii
from channelHandler.huaLogin.consts import DEVICE,QRCODE_BODY,IV_LENGTH,KEY_LENGTH
GCM_TYPE = "4"
IV_LENGTH = 24
SPLIT_CHAR = ":"

def encrypt(plain_text, key,iv):
    if not plain_text or not key:
        return plain_text
    #genenrate a random iv
    
    iv_str=binascii.hexlify(iv).decode('ascii')
    cipher = AES.new(key.encode('utf-8'), AES.MODE_GCM, nonce=iv)
    cipher.update(b"")
    ciphertext, tag = cipher.encrypt_and_digest(plain_text.encode('utf-8'))

    encrypted_text = binascii.hexlify(ciphertext).decode('utf-8')
    
    
    return f"{GCM_TYPE}:{iv_str}:{encrypted_text}"

def decrypt(encrypted_text, key):
    if not encrypted_text or not key:
        return encrypted_text
    
    parts = encrypted_text.split(SPLIT_CHAR)
    if len(parts) != 3:
        return encrypted_text
    
    iv = binascii.unhexlify(parts[1])
    ciphertext = binascii.unhexlify(parts[2])
    
    cipher = AES.new(key.encode('utf-8'), AES.MODE_GCM, nonce=iv)
    cipher.update(b"")
    plain_text = cipher.decrypt(ciphertext)
    
    return plain_text.decode('utf-8')

import requests
import xml.etree.ElementTree as ET

def getPublicKey():
    url = "https://hwid.platform.hicloud.com/AccountServer/IUserInfoMng/getResource"
    params = DEVICE.copy()
    params["ctrID"]=(str(int(time.time()))+"".join(random.choices(string.ascii_letters + string.digits, k=32)))[0:32]
    headers = {
        "Connection": "Keep-Alive",
        "Host": "hwid.platform.hicloud.com",
        "User-Agent": "com.huawei.hms.commonkit/6.14.0.300 (Linux; Android 12; SM-S9080) RestClient/7.0.3.300",
        "Content-Type": "text/html; charset=UTF-8",
        "Accept-Encoding": "gzip"
    }
    data = f"""<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<GetResourceReq>
    <version>{DEVICE["Version"]}</version>
    <resourceID>upLogin503</resourceID>
    <languageCode>zh-CN</languageCode>
    <reqClientType>0</reqClientType>
</GetResourceReq>"""

    response = requests.post(url, params=params, headers=headers, data=data)
    response.raise_for_status()

    root = ET.fromstring(response.text)
    public_key = root.find(".//ResourceContent").text
    public_key_json = json.loads(public_key)
    
    return public_key_json["public-key"]

def buildHwidCommonParams():
    params=DEVICE.copy()
    params["ctrID"]=(str(int(time.time()))+"".join(random.choices(string.ascii_letters + string.digits, k=32)))[0:32]
    return params

# 调用示例
#print(getPublicKey())
#decrypt("4:02bb4d97bc70d54db476b73a:40c8d7bb517a044400a1c0196f7fbc81d7f382cf63d8d398de72a2ca597ede13de3ea8d647712be9d2320b26dbd00a972d8c1504e00638fd070d75f7a1c4ad32d1e6f081e0","084DE0E62163084402274B38A9422AD8B1D49310FB1278B40E5BA556C9A5BD5C8C3C4E09FB1810A24ED579E2A27EB192D6C3BE402C56B7EE6822F1E031A097F09B9FCCE3B98C391B41813C759BA5E04F68B1124D71397C405045ED1832C37ACA18D32997C31E23FAB74E0CC200853DB97FBA733502F599BAA6E1DED3DF885FFE4A79DA4A454C3467A066AEE2CE6D5C61A4AAE29E4FF0ED4ED383D9C745A41BB63B8AB740388650040F5A74653CB92CA54ADD8CF435517873CC46FA90C7A44EB339213ED99250B9F982B3A5FE6616C8791A112A4B61FB5CF5041C038E8C121C9C8C676A66893EC31633BF224C2AF1C22DFDAE55D123988895DEBA48ED2168DAF97288F243A44CCAA97C89BBCF9DE459A70543DF6B485A1827D159FD1224402E9B0E4EFE178D64AB46CDF369BD8C9EEFA7BB5624717621F1E6D7C706CB5B59CE4271F42A1E35BE61AAE4F640A7A4CE33621D5E6CAC40DF2989809E61D13E6BF497E7E76C59EEF6C82094F8F98AF7321810088A46B94D649BD757BB9B77B6B61DCE")
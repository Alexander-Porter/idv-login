import json
import os
import random
import string
import time
from Crypto.Cipher import AES
import binascii
import requests
import base64
import hashlib
import uuid

def generate_code_challenge(code_verifier):
    sha256 = hashlib.sha256()
    sha256.update(code_verifier.encode('ascii'))
    code_challenge = base64.urlsafe_b64encode(sha256.digest()).decode('ascii').rstrip('=')
    return code_challenge

def get_authorization_code(client_id, redirect_uri, scope):
    # 生成随机字符串code_verifier
    code_verifier = str(uuid.uuid4())
    code_challenge = generate_code_challenge(code_verifier)
    code_challenge_method = "S256"

    # 拼接授权码请求URL
    auth_url = (
        f"https://oauth-login.cloud.huawei.com/oauth2/v3/authorize?"
        f"access_type=offline&"
        f"response_type=code&"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        f"scope={scope}&"
        f"code_challenge={code_challenge}&"
        f"code_challenge_method={code_challenge_method}"
    )

    # 返回授权码请求URL和code_verifier
    return auth_url, code_verifier

def exchange_code_for_token(client_id, code, code_verifier, redirect_uri):
    # 拼接请求参数
    token_url = "https://oauth-login.cloud.huawei.com/oauth2/v3/token"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri
    }

    # 发送POST请求获取Token
    response = requests.post(token_url, headers=headers, data=data,verify=False)
    return response.json()

def get_access_token(client_id, client_secret, refresh_token):
    # Construct the token URL
    token_url = "https://oauth-login.cloud.huawei.com/oauth2/v3/token"
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    data = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        #"client_secret": client_secret,
        "refresh_token": refresh_token
    }
    
    response = requests.post(token_url, headers=headers, data=data,verify=False)
    
    return response.json()

#print(getPublicKey())
#decrypt("4:02bb4d97bc70d54db476b73a:40c8d7bb517a044400a1c0196f7fbc81d7f382cf63d8d398de72a2ca597ede13de3ea8d647712be9d2320b26dbd00a972d8c1504e00638fd070d75f7a1c4ad32d1e6f081e0","084DE0E62163084402274B38A9422AD8B1D49310FB1278B40E5BA556C9A5BD5C8C3C4E09FB1810A24ED579E2A27EB192D6C3BE402C56B7EE6822F1E031A097F09B9FCCE3B98C391B41813C759BA5E04F68B1124D71397C405045ED1832C37ACA18D32997C31E23FAB74E0CC200853DB97FBA733502F599BAA6E1DED3DF885FFE4A79DA4A454C3467A066AEE2CE6D5C61A4AAE29E4FF0ED4ED383D9C745A41BB63B8AB740388650040F5A74653CB92CA54ADD8CF435517873CC46FA90C7A44EB339213ED99250B9F982B3A5FE6616C8791A112A4B61FB5CF5041C038E8C121C9C8C676A66893EC31633BF224C2AF1C22DFDAE55D123988895DEBA48ED2168DAF97288F243A44CCAA97C89BBCF9DE459A70543DF6B485A1827D159FD1224402E9B0E4EFE178D64AB46CDF369BD8C9EEFA7BB5624717621F1E6D7C706CB5B59CE4271F42A1E35BE61AAE4F640A7A4CE33621D5E6CAC40DF2989809E61D13E6BF497E7E76C59EEF6C82094F8F98AF7321810088A46B94D649BD757BB9B77B6B61DCE")
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
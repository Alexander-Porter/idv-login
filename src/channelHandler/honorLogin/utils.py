import base64
import hashlib
import uuid as _uuid

import requests
from ssl_utils import should_verify_ssl

from channelHandler.honorLogin.consts import HONOR_OAUTH_BASE, HONOR_REDIRECT_URI


def generate_code_challenge(code_verifier: str) -> str:
    sha256 = hashlib.sha256()
    sha256.update(code_verifier.encode("ascii"))
    return base64.urlsafe_b64encode(sha256.digest()).decode("ascii").rstrip("=")


def get_authorization_code(client_id: str, redirect_uri: str = HONOR_REDIRECT_URI, scope: str = ""):
    """构建荣耀 OAuth 授权 URL，返回 (auth_url, code_verifier)。"""
    code_verifier = str(_uuid.uuid4())
    code_challenge = generate_code_challenge(code_verifier)
    nonce = str(_uuid.uuid4())
    state = str(_uuid.uuid4())

    auth_url = (
        f"{HONOR_OAUTH_BASE}/oauth2/v3/authorize?"
        f"access_type=offline&"
        f"response_type=code&"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        f"scope={scope}&"
        f"code_challenge={code_challenge}&"
        f"code_challenge_method=S256&"
        f"nonce={nonce}&"
        f"display=touch&"
        f"state={state}"
    )
    return auth_url, code_verifier


def exchange_code_for_token(client_id: str, code: str, code_verifier: str,
                            redirect_uri: str = HONOR_REDIRECT_URI) -> dict:
    """用 authorization code 换取 access_token / refresh_token。"""
    token_url = f"{HONOR_OAUTH_BASE}/oauth2/v3/token"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "need_code": "true",
        "not_need_at": "false",
        "need_open_uid": "true",
    }
    resp = requests.post(token_url, data=data,
                         headers={"Content-Type": "application/x-www-form-urlencoded"},
                         verify=should_verify_ssl())
    return resp.json()


def refresh_access_token(client_id: str, refresh_token: str) -> dict:
    """用 refresh_token 刷新 access_token。"""
    token_url = f"{HONOR_OAUTH_BASE}/oauth2/v3/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
    }
    resp = requests.post(token_url, data=data,
                         headers={"Content-Type": "application/x-www-form-urlencoded"},
                         verify=should_verify_ssl())
    return resp.json()

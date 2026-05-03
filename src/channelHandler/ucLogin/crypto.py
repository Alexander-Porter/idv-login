# coding=UTF-8
"""UC SDK AES+RSA 混合加密/解密。

UC SDK 的所有网络请求都使用 AES+RSA 混合加密：
- 请求：生成随机 AES key+IV → RSA 加密 key 和 IV → AES-CBC 加密 body
- 响应：用同一组 AES key+IV 解密

初始化流程：
1. 首次使用 APK 内置 RSA key (version 1) 调用 getSecurityKey
2. 服务端返回新的 RSA key (如 version 5)
3. 后续所有请求使用新 key + 新 version
"""

import base64
import json
import os

from cryptography.hazmat.primitives import serialization, padding as sym_padding
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from channelHandler.ucLogin.consts import UC_RSA_PUBKEY_B64, UC_RSA_PUBKEY_VERSION


def _load_rsa_pubkey_from_b64(b64: str):
    """从 base64 DER 字符串加载 RSA 公钥。"""
    der = base64.b64decode(b64)
    return serialization.load_der_public_key(der)


# 当前使用的 RSA 公钥（运行时可被 getSecurityKey 更新）
_rsa_pubkey = None
_rsa_pubkey_version = UC_RSA_PUBKEY_VERSION
_rsa_pubkey_b64 = UC_RSA_PUBKEY_B64


def _get_rsa_pubkey():
    global _rsa_pubkey
    if _rsa_pubkey is None:
        _rsa_pubkey = _load_rsa_pubkey_from_b64(_rsa_pubkey_b64)
    return _rsa_pubkey


def get_rsa_version() -> int:
    """获取当前 RSA 公钥版本号。"""
    return _rsa_pubkey_version


def update_rsa_key(security_key: str) -> bool:
    """用 getSecurityKey 返回的密钥更新 RSA 公钥。

    Args:
        security_key: 格式 "version|base64_der_pubkey"，例如
            "5|MFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBAMFx..."

    Returns:
        True 更新成功。
    """
    global _rsa_pubkey, _rsa_pubkey_version, _rsa_pubkey_b64

    parts = security_key.split("|", 1)
    if len(parts) != 2:
        return False

    try:
        ver = int(parts[0])
        b64 = parts[1]
        pubkey = _load_rsa_pubkey_from_b64(b64)
        _rsa_pubkey = pubkey
        _rsa_pubkey_version = ver
        _rsa_pubkey_b64 = b64
        return True
    except Exception:
        return False


def _rsa_encrypt(data: bytes) -> bytes:
    """RSA PKCS1v15 加密（UC SDK 使用标准 PKCS1 填充）。"""
    pubkey = _get_rsa_pubkey()
    return pubkey.encrypt(data, asym_padding.PKCS1v15())


def _aes_encrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
    """AES-CBC + PKCS5 填充加密。"""
    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(data) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    enc = cipher.encryptor()
    return enc.update(padded) + enc.finalize()


def _aes_decrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
    """AES-CBC + PKCS5 去填充解密。"""
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    dec = cipher.decryptor()
    padded = dec.update(data) + dec.finalize()
    unpadder = sym_padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def encrypt_request(body: dict) -> tuple[dict, bytes, bytes]:
    """加密 UC SDK 请求。

    Args:
        body: 明文请求体 JSON。

    Returns:
        (encrypted_payload, aes_key, aes_iv) — 密文负载及密钥对（解密响应时需要）。
    """
    plaintext = json.dumps(body, separators=(",", ":")).encode("utf-8")

    # 生成随机 AES-128 密钥和 IV
    aes_key = os.urandom(16)
    aes_iv = os.urandom(16)

    # RSA 加密 AES 密钥和 IV
    encrypted_key = base64.b64encode(_rsa_encrypt(aes_key)).decode("ascii")
    encrypted_iv = base64.b64encode(_rsa_encrypt(aes_iv)).decode("ascii")

    # AES 加密请求体
    encrypted_data = base64.b64encode(_aes_encrypt(plaintext, aes_key, aes_iv)).decode("ascii")

    payload = {
        "k": encrypted_key,
        "i": encrypted_iv,
        "d": encrypted_data,
        "v": _rsa_pubkey_version,
    }
    return payload, aes_key, aes_iv


def decrypt_response(resp_json: dict, aes_key: bytes, aes_iv: bytes) -> dict:
    """解密 UC SDK 响应。

    Args:
        resp_json: 服务器返回的 JSON（含 "c" 和 "d" 字段）。
        aes_key: 请求时使用的 AES 密钥。
        aes_iv: 请求时使用的 AES IV。

    Returns:
        解密后的响应 JSON。
    """
    code = resp_json.get("c", -1)
    encrypted_data = resp_json.get("d", "")

    if not encrypted_data:
        return {"code": code}

    decrypted = _aes_decrypt(
        base64.b64decode(encrypted_data), aes_key, aes_iv
    )
    result = json.loads(decrypted.decode("utf-8"))
    result["code"] = code
    return result

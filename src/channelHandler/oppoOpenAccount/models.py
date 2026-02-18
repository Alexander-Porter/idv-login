#仅供技术交流，请下载后24小时内删除，禁止商用！如有侵权请联系仓库维护者删除！谢谢！
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from channelHandler.oppoOpenAccount.sign import sign_request


ACCOUNT_BIZK = "3cd48b0c781835478b0a1783a9eff0c9"  # 与 mockNative.js / authro.txt 一致


@dataclass
class BaseBizkRequest:
    bizk: str = ACCOUNT_BIZK
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))
    sign: str = ""

    def compute_sign(self):
        self.sign = sign_request(self)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "bizk": self.bizk,
            "timestamp": self.timestamp,
            "sign": self.sign,
        }
        return d


@dataclass
class AuthorizeRequest(BaseBizkRequest):
    envInfo: str = ""
    accountIdToken: str = ""
    bizAppKey: str = "cd73441423364d90a6ac6fe2bc727542"

    def finalize(self):
        self.compute_sign()

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "envInfo": self.envInfo,
            "accountIdToken": self.accountIdToken,
            "bizAppKey": self.bizAppKey,
        })
        return d


@dataclass
class LogoutRequest(BaseBizkRequest):
    userToken: str = ""
    secondaryToken: str = ""

    def finalize(self):
        self.compute_sign()

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "userToken": self.userToken,
            "secondaryToken": self.secondaryToken,
        })
        return d


@dataclass
class RefreshRequest(BaseBizkRequest):
    refreshToken: str = ""
    ssoid: str = ""
    primaryToken: str = ""
    packageSignMap: Optional[Dict[str, str]] = None
    refreshTicket: str = ""
    envInfo: str = ""
    accessToken: str = ""

    def finalize(self):
        self.compute_sign()

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "refreshToken": self.refreshToken,
            "ssoid": self.ssoid,
            "primaryToken": self.primaryToken,
            "packageSignMap": self.packageSignMap,
            "refreshTicket": self.refreshTicket,
            "envInfo": self.envInfo,
            "accessToken": self.accessToken,
        })
        return d

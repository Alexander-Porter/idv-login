from __future__ import annotations

import time
import uuid
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests

from channelHandler.oppoGameSdk.gamesdk_latest_role_pb2 import LatestGameAccountsDto
from channelHandler.oppoGameSdk.gamesdk_login_pb2 import GameAccountsDto
from channelHandler.oppoGameSdk.sign2 import (
    build_headers,
    build_ocs_encoded,
    build_user_agent_encoded,
)
from logutil import setup_logger
from ssl_utils import should_verify_ssl


BASE_URL = "https://isdk.heytapmobi.com"


_UUID_HEX_RE = re.compile(r"[0-9a-f]+")


def _normalize_uuid32(value: str) -> str:
    """尽量把输入规整成 32 位 hex（模拟 DeviceUtils.getUuid）。"""

    raw = (value or "").strip().lower()
    if not raw:
        return ""

    # 保留 hex 字符，兼容带 '-' 或其他分隔符的 uuid
    hex_only = "".join(_UUID_HEX_RE.findall(raw))
    if len(hex_only) < 32:
        return ""
    return hex_only[:32]


def _generate_vaid(device_uuid: str = "") -> str:
    """按 SimpleDateFormat("yyMMddHH") + DeviceUtils.getUuid() 的特征生成 vaid。

    例：26021717 + 48fea7e66b3945fca2debd1f54d2db9b => 40 字符。
    """

    prefix = time.strftime("%y%m%d%H", time.localtime())
    u32 = _normalize_uuid32(device_uuid)
    if not u32:
        u32 = uuid.uuid4().hex
    return prefix + u32


@dataclass
class GameSdkLoginResult:
    code: str = ""
    msg: str = ""
    ticket: str = ""
    trace_id: str = ""
    user_dto: Dict[str, Any] = None  # type: ignore[assignment]


@dataclass
class ResultDto:
    code: str = ""
    msg: str = ""


@dataclass
class Sign2Profile:
    brand: str = "Xiaomi"
    model: str = "M2102K1AC"
    api: int = 32
    os_ver: str = "12"
    rom: str = "unknown"

    sdkversion: int = 6070105
    ch: str = "2401"
    pid: str = "1001"
    locale: str = "-;cn"
    country: str = "CN"
    net: str = "wifi"
    sdktype: str = "0"

    appversion: str = "2.0.15"
    appid: str = "OPPO#1001#CN"

    udid: str = ""
    oaid: str = ""
    mkmix_id: str = ""
    vaid: str = ""  # 必填：用于 id/sign

    screen_w: int = 1600
    screen_h: int = 900

    def user_agent(self) -> str:
        return build_user_agent_encoded(
            brand=self.brand,
            model=self.model,
            api=self.api,
            os_ver=self.os_ver,
            sdkversion=self.sdkversion,
            ch=self.ch,
        )

    def ocs(self) -> str:
        return build_ocs_encoded(
            brand=self.brand,
            model=self.model,
            api=self.api,
            os_ver=self.os_ver,
            sdkversion=self.sdkversion,
            rom=self.rom,
        )


class OppoGameSdkClient:
    """只实现两个接口：

    - GET /gamesdk/v2/user/login
    - GET /gamesdk/v2/user/account-latest-role

    返回为 protostuff（二进制），这里用最小解码器只取必要字段。
    """

    def __init__(self, profile: Sign2Profile, base_url: str = BASE_URL):
        self.logger = setup_logger()
        self.profile = profile
        if not (self.profile.vaid or "").strip():
            # 直接使用 yyMMddHH + uuid32 的规则；uuid 优先取 profile.udid（更接近“设备 uuid”语义）
            self.profile.vaid = _generate_vaid(self.profile.udid)
        self.base_url = base_url.rstrip("/")
        self.http = requests.Session()
        self.http.trust_env = False
        self._rsq = int(time.time()) % 100000

    def _next_rsq(self) -> int:
        self._rsq += 1
        return self._rsq

    def _get(self, path: str, params: Dict[str, Any]) -> Tuple[int, Dict[str, str], bytes]:
        url = self.base_url + path
        r = self.http.get(url, params=params, headers=self._build_headers_for(url, params), verify=should_verify_ssl())
        return r.status_code, dict(r.headers), r.content

    def _build_headers_for(self, url: str, params: Dict[str, Any]) -> Dict[str, str]:
        # requests 会对 params 做 urlencoding；这里直接复用 r.url 不方便，所以手动拼出来给 sign。
        # 注意：sign2 需要 path+query 严格一致。
        from urllib.parse import urlencode

        query = urlencode(params or {}, doseq=True)
        full_url = url if not query else f"{url}?{query}"

        t_ms = int(time.time() * 1000)
        return build_headers(
            url=full_url,
            t_ms=t_ms,
            user_agent=self.profile.user_agent(),
            ocs=self.profile.ocs(),
            vaid=self.profile.vaid,
            udid=self.profile.udid,
            oaid=self.profile.oaid,
            mkmix_id=self.profile.mkmix_id,
            net=self.profile.net,
            country=self.profile.country,
            sdkversion=self.profile.sdkversion,
            sdktype=self.profile.sdktype,
            ch=self.profile.ch,
            locale=self.profile.locale,
            rom=self.profile.rom,
            pid=self.profile.pid,
            appversion=self.profile.appversion,
            appid=self.profile.appid,
            client_time_ms=t_ms,
            h=str(self.profile.screen_h),
            w=str(self.profile.screen_w),
            rsq=self._next_rsq(),
            ext_original_url=True,
        )

    def user_login(self, *, pkg_name: str, secondary_token: str, ad_id: str = "") -> GameSdkLoginResult:
        status, headers, body = self._get(
            "/gamesdk/v2/user/login",
            {
                "adId": ad_id,
                "pkgName": pkg_name,
                "token": secondary_token,
            },
        )
        if status != 200:
            raise RuntimeError(f"user/login http={status} raw={body[:200]!r}")

        dto = GameAccountsDto()
        dto.ParseFromString(body)

        user_dto: Dict[str, Any] = {}
        if dto.HasField("user_dto"):
            u = dto.user_dto
            user_dto = {
                "user_id": str(u.user_id or ""),
                "user_name": str(u.user_name or ""),
                "email": str(u.email or ""),
                "mobile": str(u.mobile or ""),
                "create_time": str(u.create_time or ""),
                "user_status": str(u.user_status or ""),
                "real_name_status": str(u.real_name_status or ""),
                "age": int(u.age or 0),
                "twice_real_name_auth": bool(u.twice_real_name_auth),
            }
        return GameSdkLoginResult(
            code=str(dto.code or ""),
            msg=str(dto.msg or ""),
            ticket=str(dto.ticket or ""),
            trace_id=str(dto.trace_id or ""),
            user_dto=user_dto,
        )

    def account_latest_role(self, *, pkg_name: str, secondary_token: str) -> Tuple[ResultDto, List[Dict[str, Any]]]:
        status, headers, body = self._get(
            "/gamesdk/v2/user/account-latest-role",
            {
                "pkgName": pkg_name,
                "token": secondary_token,
            },
        )
        if status != 200:
            raise RuntimeError(f"account-latest-role http={status} raw={body[:200]!r}")

        dto = LatestGameAccountsDto()
        dto.ParseFromString(body)
        result = ResultDto(code=str(dto.code or ""), msg=str(dto.msg or ""))

        out: List[Dict[str, Any]] = []
        for a in dto.accountMsgDtoList:
            out.append(
                {
                    "account_id": str(a.accountId or ""),
                    "user_id": str(a.userId or ""),
                    "role_id": str(a.roleId or ""),
                    "role_name": str(a.roleName or ""),
                    "realm_id": str(a.realmId or ""),
                    "realm_name": str(a.realmName or ""),
                    "login_time": int(a.loginTime or 0),
                    "role_level": int(a.roleLevel or 0),
                    "account_name": str(a.accountName or ""),
                }
            )

        return result, out

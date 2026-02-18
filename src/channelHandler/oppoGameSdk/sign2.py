from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from urllib.parse import quote, urlsplit


RSA_BLOB_STORENEW = (
    "STORENEW"
    "MIICeAIBADANBgkqhkiG9w0BAQEFAASCAmIwggJeAgEAAoGBANYFY/UJGSzhIhpx6YM5KJ9yRHc7YeURxzb9tDvJvMfENHlnP3DtVkOIjERbpsSd76fjtZnMWY60TpGLGyrNkvuV40L15JQhHAo9yURpPQoI0eg3SLFmTEI/MUiPRCwfwYf2deqKKlsmMSysYYHX9JiGzQuWiYZaawxprSuiqDGvAgMBAAECgYEAtQ0QV00gGABISljNMy5aeDBBTSBWG2OjxJhxLRbndZM81OsMFysgC7dq+bUS6ke1YrDWgsoFhRxxTtx/2gDYciGp/c/h0Td5pGw7T9W6zo2xWI5oh1WyTnn0Xj17O9CmOk4fFDpJ6bapL+fyDy7gkEUChJ9+p66WSAlsfUhJ2TECQQD5sFWMGE2IiEuz4fIPaDrNSTHeFQQr/ZpZ7VzB2tcG7GyZRx5YORbZmX1jR7l3H4F98MgqCGs88w6FKnCpxDK3AkEA225CphAcfyiH0ShlZxEXBgIYt3V8nQuc/g2KJtiV6eeFkxmOMHbVTPGkARvt5VoPYEjwPTg43oqTDJVtlWagyQJBAOvEeJLno9aHNExvznyD4/pR4hec6qqLNgMyIYMfHCl6d3UodVvC1HO1/nMPl+4GvuRnxuoBtxj/PTe7AlUbYPMCQQDOkf4sVv58tqslO+I6JNyHy3F5RCELtuMUR6rG5x46FLqqwGQbO8ORq+m5IZHTV/Uhr4h6GXNwDQRh1EpVW0gBAkAp/v3tPI1riz6UuG0I6uf5er26yl5evPyPrjrD299L4Qy/1EIunayC7JYcSGlR01+EDYYgwUkec+QgrRC/NstV"
)


@dataclass(frozen=True)
class Sign2Constants:
    oak: str = "a78b923440df20ce"
    salt: str = "a31cfccd172003e00f5ac59c95387a3b"
    rsa_blob: str = RSA_BLOB_STORENEW


def md5_hex(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def split_path_query(url: str) -> Tuple[str, str]:
    parts = urlsplit(url)
    return parts.path or "", parts.query or ""


def build_id_header_from_vaid(vaid: str) -> str:
    vaid = str(vaid or "").strip()
    return f"///{vaid}" if vaid else "///"


def build_sign(*, url: str, ocs: str, t_ms: int, device_id: str, constants: Sign2Constants = Sign2Constants()) -> str:
    path, query = split_path_query(url)

    prefix = "".join(
        [
            constants.oak,
            constants.salt,
            ocs,
            str(t_ms),
            device_id,
            path,
            query,
        ]
    )

    prefix_with_len = prefix + str(len(prefix))
    final = prefix_with_len + constants.rsa_blob
    return md5_hex(final)


def build_user_agent_encoded(*, brand: str, model: str, api: int, os_ver: str, sdkversion: int, ch: str) -> str:
    raw = f"{brand}/{model}/{api}/{os_ver}/unknown/{sdkversion}/{ch}/{sdkversion}"
    return quote(raw, safe="")


def build_ocs_encoded(*, brand: str, model: str, api: int, os_ver: str, sdkversion: int, rom: str) -> str:
    raw = f"{brand}/{model}/{api}/{os_ver}/unknown/{sdkversion}/{rom}/{sdkversion}"
    return quote(raw, safe="")


def build_headers(
    *,
    url: str,
    t_ms: int,
    user_agent: str,
    ocs: str,
    vaid: str,
    udid: str = "",
    oaid: str = "",
    mkmix_id: str = "",
    net: str = "wifi",
    country: str = "CN",
    sdkversion: int = 6070105,
    sdktype: str = "0",
    ch: str = "2401",
    oak: str = "a78b923440df20ce",
    locale: str = "-;cn",
    rom: str = "unknown",
    pid: str = "1001",
    appversion: str = "2.0.15",
    appid: str = "OPPO#1001#CN",
    client_time_ms: Optional[int] = None,
    h: Optional[str] = None,
    w: Optional[str] = None,
    rsq: Optional[int] = None,
    ext_original_url: bool = True,
) -> Dict[str, str]:
    device_id = build_id_header_from_vaid(vaid)
    sign = build_sign(url=url, ocs=ocs, t_ms=t_ms, device_id=device_id)

    headers: Dict[str, str] = {
        "Accept": "application/x-protostuff; charset=UTF-8",
        "User-Agent": user_agent,
        "t": str(t_ms),
        "id": device_id,
        "udid": udid,
        "oaid": oaid,
        "vaid": vaid,
        "MkMixId": mkmix_id,
        "ocs": ocs,
        "ch": ch,
        "oak": oak,
        "locale": locale,
        "rom": rom,
        "pid": pid,
        "country": country,
        "sdkversion": str(sdkversion),
        "sdkType": sdktype,
        "net": net,
        "sign": sign,
        "appversion": appversion,
        "appid": appid,
        "ouidStatus": "false",
    }

    if client_time_ms is not None:
        headers["clientTime"] = str(client_time_ms)
        headers["ct"] = str(client_time_ms)

    if h is not None:
        headers["h"] = str(h)

    if w is not None:
        headers["w"] = str(w)

    if rsq is not None:
        headers["rsq"] = str(int(rsq))

    if ext_original_url:
        headers["extOriginalUrl"] = url

    return headers

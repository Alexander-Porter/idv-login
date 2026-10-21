"""Narrow, explicit exports from an app-owned browser context to channel HTTP.

This is not a browser cookie jar or a persistence mechanism. Firefox keeps its
native, partition-aware profile. A BiDi context query can still return cookies
for third-party domains and does not label each cookie's partition; only cookies
applicable to declared destinations may leave that context. Ambiguous names fail
closed rather than guessing which partition/domain/path supplied a credential.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import math
import re
import time
from urllib.parse import urlsplit


class CookieExportError(ValueError):
    """An export cannot be represented safely. Messages never include secrets."""


_COOKIE_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


def _url_parts(url: str):
    try:
        parsed = urlsplit(url)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username is not None or parsed.password is not None):
            raise ValueError
        port = parsed.port
        host = parsed.hostname.lower()
        authority = f"[{host}]" if ":" in host else host
        if port is not None and port != (443 if parsed.scheme == "https" else 80):
            authority += f":{port}"
        return parsed.scheme, host, parsed.path or "/", f"{parsed.scheme}://{authority}"
    except (TypeError, ValueError, AttributeError):
        raise CookieExportError("Cookie export requires a valid HTTP(S) destination") from None


def _applies(cookie: dict, url: str, now: float) -> bool:
    scheme, host, path, _origin = _url_parts(url)
    domain = cookie.get("domain")
    cookie_path = cookie.get("path", "/")
    if not isinstance(domain, str) or not isinstance(cookie_path, str):
        raise CookieExportError("Invalid cookie scope metadata")
    domain = domain.lower()
    # Firefox exposes nsICookie.host: the leading dot denotes a domain cookie.
    # Without it, this is host-only, not an implicit subdomain wildcard.
    if domain.startswith("."):
        domain = domain[1:]
        domain_matches = bool(domain) and (host == domain or host.endswith("." + domain))
    else:
        domain_matches = bool(domain) and host == domain
    if not domain_matches:
        return False
    if not cookie_path.startswith("/"):
        raise CookieExportError("Invalid cookie path metadata")
    if not (path == cookie_path or (path.startswith(cookie_path)
            and (cookie_path.endswith("/") or path[len(cookie_path):].startswith("/")))):
        return False
    secure = cookie.get("secure", False)
    if not isinstance(secure, bool):
        raise CookieExportError("Invalid cookie security metadata")
    if secure and scheme != "https":
        return False
    expires = cookie.get("expiry", cookie.get("expires", -1))
    try:
        expires = float(expires)
    except (TypeError, ValueError, OverflowError):
        raise CookieExportError("Invalid cookie expiry metadata") from None
    if not math.isfinite(expires):
        raise CookieExportError("Invalid cookie expiry metadata")
    return expires < 0 or expires > now


def _normalize(cookie: dict) -> dict:
    name = cookie.get("name")
    value = cookie.get("value")
    if not isinstance(name, str) or not _COOKIE_NAME.fullmatch(name):
        raise CookieExportError("Invalid exported cookie name")
    if isinstance(value, dict):
        try:
            if value.get("type") == "string":
                value = value["value"]
            elif value.get("type") == "base64":
                value = base64.b64decode(value["value"], validate=True).decode("utf-8")
            else:
                raise ValueError
        except (KeyError, TypeError, ValueError, UnicodeError):
            raise CookieExportError("Unsupported exported cookie encoding") from None
    # requests ultimately writes an HTTP header; reject delimiter/control data
    # rather than letting an invalid credential become another header/cookie.
    if (not isinstance(value, str)
            or any(ord(char) < 32 or ord(char) == 127 or ord(char) > 255 or char == ";" for char in value)):
        raise CookieExportError("Invalid exported cookie value")
    return {
        "name": name, "value": value,
        "domain": cookie["domain"].lower(), "path": cookie.get("path", "/"),
        "expires": float(cookie.get("expiry", cookie.get("expires", -1))),
        "secure": cookie.get("secure", False), "httpOnly": bool(cookie.get("httpOnly", False)),
        "sameSite": str(cookie.get("sameSite", "unknown")),
    }


def cookies_for_url(records: list[dict], target_url: str) -> dict[str, str]:
    """Project scoped records for ONE request, rejecting same-name ambiguity.

    Callers must also constrain the request destination and disable redirects;
    requests' ordinary dict cookies do not retain any domain/path restrictions.
    """
    _url_parts(target_url)
    if not isinstance(records, list):
        raise CookieExportError("Invalid exported cookie records")
    selected = {}
    now = time.time()
    for raw in records:
        if not isinstance(raw, dict):
            raise CookieExportError("Invalid exported cookie records")
        if not _applies(raw, target_url, now):
            continue
        cookie = _normalize(raw)
        name = cookie["name"]
        if name in selected:
            raise CookieExportError("Ambiguous cookie scope; a fresh browser login is required")
        selected[name] = cookie["value"]
    return selected


@dataclass(frozen=True)
class CookieExport:
    """Allowlisted observation pages and intended HTTP destinations.

    ``targets=None`` selects cookies applicable to the observed completion page
    itself. ``source_origin`` / ``source_path`` in results describe that query's
    context, NOT the hidden partition of each individual cookie. They never
    contain an OAuth query or fragment and must never be used to restore cookies.
    """

    source_origins: tuple[str, ...]
    source_paths: tuple[str, ...]
    targets: tuple[str, ...] | None = None
    names: frozenset[str] | None = None

    def matches(self, url: str) -> bool:
        try:
            _scheme, _host, path, origin = _url_parts(url)
        except CookieExportError:
            return False
        return origin in self.source_origins and path in self.source_paths

    def select(self, rawcookies: list[dict], source_url: str) -> list[dict]:
        if not self.matches(source_url):
            raise CookieExportError("Cookie export source is not allowed")
        if not isinstance(rawcookies, list):
            raise CookieExportError("Invalid browser cookie snapshot")
        _scheme, _host, path, origin = _url_parts(source_url)
        targets = self.targets if self.targets is not None else (origin + path,)
        records = []
        now = time.time()
        for raw in rawcookies:
            if not isinstance(raw, dict):
                raise CookieExportError("Invalid browser cookie snapshot")
            if self.names is not None and raw.get("name") not in self.names:
                continue
            if not any(_applies(raw, target, now) for target in targets):
                continue
            cookie = _normalize(raw)
            cookie.update(source_origin=origin, source_path=path)
            records.append(cookie)
        # A union of disjoint get-only / use-only paths is legitimate. A dict
        # projection is checked independently for every real destination.
        for target in targets:
            cookies_for_url(records, target)
        return records

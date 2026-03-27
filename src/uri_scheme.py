# coding=UTF-8
"""
Copyright (c) 2026 KKeygen

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
"""

import os
import sys

from logutil import setup_logger

logger = setup_logger()


def register_uri_scheme(executable_path: str | None = None) -> bool:
    """Register the ``idvlogin://`` URI scheme so that the OS opens our
    application when a user or WebView navigates to an ``idvlogin://``
    URL (e.g. from a QR-code redirect).

    On Windows this adds entries under
    ``HKEY_CURRENT_USER\\Software\\Classes\\idvlogin``.

    The registration is intentionally under HKCU so that no admin
    rights are needed and the entry is removed when the user's
    profile is cleaned up.

    Returns ``True`` on success.
    """
    if sys.platform != "win32":
        logger.debug("URI Scheme 注册仅支持 Windows 平台")
        return False

    if executable_path is None:
        if getattr(sys, "frozen", False):
            executable_path = sys.executable
        else:
            executable_path = os.path.abspath(sys.argv[0])
            # For .py scripts, prepend the interpreter
            if executable_path.endswith(".py"):
                executable_path = f'{sys.executable}" "{executable_path}'

    try:
        import winreg

        base = r"Software\Classes\idvlogin"

        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, base)
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "URL:IDV Login Protocol")
        winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
        winreg.CloseKey(key)

        cmd_key = winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, base + r"\shell\open\command"
        )
        winreg.SetValueEx(
            cmd_key,
            "",
            0,
            winreg.REG_SZ,
            f'"{executable_path}" --uri "%1"',
        )
        winreg.CloseKey(cmd_key)

        logger.info("已注册 idvlogin:// URI Scheme")
        return True
    except Exception as e:
        logger.warning(f"注册 URI Scheme 失败: {e}")
        return False


def unregister_uri_scheme() -> bool:
    """Remove the ``idvlogin://`` URI scheme registration."""
    if sys.platform != "win32":
        return False

    try:
        import winreg

        base = r"Software\Classes\idvlogin"
        # Delete keys bottom-up
        for sub in (
            base + r"\shell\open\command",
            base + r"\shell\open",
            base + r"\shell",
            base,
        ):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            except FileNotFoundError:
                pass
        logger.info("已注销 idvlogin:// URI Scheme")
        return True
    except Exception as e:
        logger.warning(f"注销 URI Scheme 失败: {e}")
        return False


def parse_uri(uri: str) -> dict:
    """Parse an ``idvlogin://`` URI into a dict of parameters.

    Example::

        parse_uri("idvlogin://open?game_id=h55")
        # => {"action": "open", "game_id": "h55"}
    """
    from urllib.parse import urlparse, parse_qs

    parsed = urlparse(uri)
    params: dict = {}
    params["action"] = parsed.hostname or parsed.netloc or "open"
    qs = parse_qs(parsed.query, keep_blank_values=True)
    for k, v in qs.items():
        params[k] = v[0] if len(v) == 1 else v
    return params

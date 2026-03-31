# coding=UTF-8
"""
Restricted-permission file writes.

All sensitively-stored files (account tokens, config, keys, etc.)
should use the helpers in this module so that they are readable
only by the current user.
"""

import json
import os
import sys


def write_file_restricted(filepath: str, data: bytes):
    """Write *data* (bytes) and restrict permissions to current user."""
    try:
        if sys.platform != "win32":
            fd = os.open(filepath, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(fd, data)
            finally:
                os.close(fd)
        else:
            _win_write_restricted(filepath, data, binary=True)
    except Exception:
        # Fallback: standard write
        with open(filepath, "wb") as f:
            f.write(data)


def write_json_restricted(filepath: str, obj):
    """Serialize *obj* as JSON and write with restricted permissions."""
    text = json.dumps(obj, ensure_ascii=False)
    data = text.encode("utf-8")
    try:
        if sys.platform != "win32":
            fd = os.open(filepath, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(fd, data)
            finally:
                os.close(fd)
        else:
            _win_write_restricted(filepath, data, binary=True)
    except Exception:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)


def write_text_restricted(filepath: str, text: str, encoding: str = "utf-8"):
    """Write text with restricted permissions. Default UTF-8 encoding."""
    data = text.encode(encoding)
    write_file_restricted(filepath, data)


def _win_write_restricted(filepath: str, data: bytes, *, binary: bool = True):
    """Windows: write then restrict ACL to Administrators/SYSTEM only.

    Non-elevated users must use UAC to access the file, even if they
    created it.  Uses well-known SIDs for locale independence.
    """
    mode = "wb" if binary else "w"
    with open(filepath, mode) as f:
        f.write(data)
    import subprocess
    # /reset 清除所有显式 ACE 并恢复为继承权限（移除旧版本残留的用户 ACE）
    subprocess.run(
        ["icacls", filepath, "/reset"],
        capture_output=True, timeout=10,
    )
    # /inheritance:r 移除所有继承的 ACE，然后仅授权 Administrators 和 SYSTEM
    # S-1-5-32-544 = BUILTIN\Administrators  (requires elevation)
    # S-1-5-18     = NT AUTHORITY\SYSTEM
    subprocess.run(
        ["icacls", filepath, "/inheritance:r",
         "/grant:r", "*S-1-5-32-544:(F)",
         "/grant:r", "*S-1-5-18:(F)"],
        capture_output=True, timeout=10,
    )

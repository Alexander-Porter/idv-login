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


def _win_write_restricted(filepath: str, data: bytes, *, binary: bool = True):
    """Windows: write then immediately restrict ACL."""
    mode = "wb" if binary else "w"
    with open(filepath, mode) as f:
        f.write(data)
    import subprocess
    username = os.getlogin()
    subprocess.run(
        ["icacls", filepath, "/inheritance:r",
         "/grant:r", f"{username}:(R,W)"],
        capture_output=True, timeout=10,
    )

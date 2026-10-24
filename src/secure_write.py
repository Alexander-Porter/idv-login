# coding=UTF-8
"""
Restricted-permission file writes.

All sensitively-stored files (account tokens, config, keys, etc.)
should use the helpers in this module. Unix files are private to the current
user; Windows also retains access for Administrators and SYSTEM.

Writes are atomic: data goes to a temporary file first, then
``os.replace()`` swaps it into place.  A per-path thread lock serializes
writers within this process. Failed writes leave the destination unchanged.
"""

import json
import os
import sys
import tempfile
import threading

_write_locks = {}          # type: dict[str, threading.Lock]
_meta_lock = threading.Lock()


def _get_lock(filepath: str) -> threading.Lock:
    key = os.path.normcase(os.path.abspath(filepath))
    with _meta_lock:
        if key not in _write_locks:
            _write_locks[key] = threading.Lock()
        return _write_locks[key]


def _atomic_write(filepath: str, data: bytes, *, restrict_unix: bool = True):
    """Write *data* atomically via temp-file + os.replace().

    On Unix the temp file is created with mode 0o600 when *restrict_unix*
    is True. On Windows, ACLs are restricted before writing any payload.
    """
    dirpath = os.path.dirname(os.path.abspath(filepath)) or "."
    fd = None
    tmp_path = None
    try:
        if sys.platform != "win32" and restrict_unix:
            fd = tempfile.mkstemp(dir=dirpath, prefix=".tmp_", suffix=".json")
            tmp_path = fd[1]
            with os.fdopen(fd[0], 'wb') as tmp:
                fd = None
                tmp.write(data)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.chmod(tmp_path, 0o600)
        else:
            with tempfile.NamedTemporaryFile(
                dir=dirpath, prefix=".tmp_", suffix=".json",
                delete=False, mode="wb",
            ) as tmp:
                tmp_path = tmp.name
                if sys.platform == "win32":
                    _win_restrict_acl(tmp_path)
                tmp.write(data)
                tmp.flush()
                os.fsync(tmp.fileno())

        os.replace(tmp_path, filepath)
        tmp_path = None  # rename succeeded, nothing to clean up
    finally:
        if fd is not None:
            try:
                os.close(fd[0])
            except OSError:
                pass
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def write_file_restricted(filepath: str, data: bytes):
    """Write *data* atomically; raise on lock timeout or write failure."""
    lock = _get_lock(filepath)
    if not lock.acquire(timeout=5):
        raise TimeoutError('文件写入锁获取超时')
    try:
        _atomic_write(filepath, data)
    finally:
        lock.release()


def write_json_restricted(filepath: str, obj, *, atomic_required=False):
    """Write JSON atomically, preserving the destination on failure.

    ``atomic_required`` is retained for compatibility; all writes now require
    atomic replacement, including callers that omit it or pass False.
    """
    text = json.dumps(obj, ensure_ascii=False)
    data = text.encode("utf-8")
    write_file_restricted(filepath, data)


def _win_restrict_acl(filepath: str):
    """Restrict ACL to the current user, Administrators and SYSTEM."""
    import csv
    import re
    import subprocess
    try:
        system_dir = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
        run_options = dict(
            capture_output=True, timeout=10, check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        identity = subprocess.run(
            [os.path.join(system_dir, "whoami.exe"), "/user", "/fo", "csv", "/nh"],
            text=True, encoding="utf-8", errors="replace", **run_options,
        )
        rows = list(csv.reader(identity.stdout.splitlines()))
        if len(rows) != 1 or len(rows[0]) != 2:
            raise ValueError("Invalid user identity")
        sid = rows[0][1]
        if not re.fullmatch(r"S-1-(?:[0-9]+-)*[0-9]+", sid):
            raise ValueError("Invalid user SID")
        subprocess.run(
            [os.path.join(system_dir, "icacls.exe"), filepath, "/reset"],
            **run_options,
        )
        subprocess.run(
            [os.path.join(system_dir, "icacls.exe"), filepath, "/inheritance:r",
             "/grant:r", f"*{sid}:(F)",
             "/grant:r", "*S-1-5-32-544:(F)",
             "/grant:r", "*S-1-5-18:(F)"],
            **run_options,
        )
    except (OSError, subprocess.SubprocessError, ValueError, csv.Error):
        # Avoid including identity information or command output in logs.
        raise OSError('无法设置文件访问权限') from None

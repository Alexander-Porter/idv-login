"""Own-profile leases and cookie-only Firefox native session restoration.

Firefox's BiDi cookie representation omits originAttributes. Never round-trip
that representation into persistent storage: Firefox's native session document
preserves cookie partitions. Only native schema 1 is accepted here; every tab,
closed window, form and history is replaced with a single about:blank document
before Firefox starts. No ordinary browser profile is opened by this module.

The small supported format follows Mozilla SessionFile/SessionCookies (153 ESR
and 158), not a copied implementation. A format mismatch loses session restore,
with an explicit warning, rather than guessing at cookie ownership.
"""
from contextlib import contextmanager
import ctypes
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
import tempfile
import time
import uuid

import lz4.block

_MAGIC = b"mozLz40\0"
_MAX_STATE = 16 * 1024 * 1024
_HOST = "idv-login.invalid"
_READY_PREFIX = "__idv_native_ready_"
_CLEAR_PREFIX = "__idv_native_clear_"
_MARKER = ".idv-cookies-cleared.json"
_CORE = (
    "sessionstore.jsonlz4",
    "sessionstore-backups/recovery.jsonlz4",
    "sessionstore-backups/recovery.baklz4",
    "sessionstore-backups/previous.jsonlz4",
)
_WARNING = "上次的浏览器临时登录状态无法完整恢复，请重新登录。账号记录未被修改。"


class BrowserProfileError(RuntimeError):
    """A dedicated profile could not be prepared safely. Do not launch it."""


def _no_link(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise BrowserProfileError("专用浏览器资料路径不可为链接，请选择本地独立资料目录。")



def validate_profile_path(profile):
    """Normalize without following links; reject links/reparse points at every level.

    Check this BEFORE mkdir or ACL changes. In particular Path.resolve() would
    silently turn an attacker-controlled link into an unrelated existing profile.
    Missing components are permitted for a new dedicated directory.
    """
    path = Path(os.path.abspath(os.fspath(profile)))
    for component in reversed((path, *path.parents)):
        _no_link(component)
    return path


def _read_bounded(path, limit=_MAX_STATE):
    _no_link(path)
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Profile state too large")
    return data


def _sync_directory(path):
    if sys.platform != "win32":
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _atomic_write(path, data):
    # The caller has already restricted the dedicated directory's ACL. A temp
    # file inherits that Windows ACL; on Unix mkstemp gives mode 0600. Never use
    # a fallback that truncates the live file after a failed atomic replacement.
    _no_link(path)
    fd, temporary = tempfile.mkstemp(prefix=".idv-state-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        _sync_directory(path.parent)
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _compressed(path):
    return ".jsonlz4" in path.name or path.name.endswith(".baklz4")


def _read_state(path):
    data = _read_bounded(path)
    if _compressed(path):
        if len(data) < 12 or not data.startswith(_MAGIC):
            raise ValueError("Invalid native session header")
        if struct.unpack("<I", data[8:12])[0] > _MAX_STATE:
            raise ValueError("Native session expands beyond the size limit")
        data = lz4.block.decompress(data[8:])
    state = json.loads(data)
    if not isinstance(state, dict) or state.get("version") != ["sessionrestore", 1]:
        raise ValueError("Unsupported native session schema")
    if not isinstance(state.get("windows"), list) or not isinstance(state.get("cookies", []), list):
        raise ValueError("Invalid native session structure")
    for cookie in state.get("cookies", []):
        if (not isinstance(cookie, dict) or not isinstance(cookie.get("host"), str)
                or not isinstance(cookie.get("value"), str)
                or not isinstance(cookie.get("originAttributes", {}), dict)):
            raise ValueError("Invalid native cookie structure")
        # Validate known scalar types without reconstructing or dropping fields.
        # In particular, preserve *all* originAttributes and partition metadata.
        for key in ("name", "path"):
            if key in cookie and not isinstance(cookie[key], str):
                raise ValueError("Invalid native cookie string")
        for key in ("secure", "httponly", "isPartitioned"):
            if key in cookie and type(cookie[key]) is not bool:
                raise ValueError("Invalid native cookie flag")
        for key in ("expiry", "sameSite", "schemeMap"):
            if key in cookie and type(cookie[key]) is not int:
                raise ValueError("Invalid native cookie integer")
    return state


def _legacy(name):
    return name.replace("jsonlz4", "js").replace("baklz4", "bak")


def _native_cookie(prefix, token):
    return {"host": _HOST, "name": prefix + token, "value": token, "path": "/",
            "secure": True, "httponly": True, "sameSite": 2, "originAttributes": {}}


def _bidi_cookie(cookie):
    # Only internally generated synchronization markers go through this adapter.
    # Site cookies are never converted to the incomplete BiDi representation.
    return {"domain": cookie["host"], "name": cookie["name"],
            "value": {"type": "string", "value": cookie["value"]},
            "path": "/", "secure": True, "httpOnly": True, "sameSite": "strict"}


def _internal(cookie, prefix):
    name = cookie.get("name", "")
    token = name[len(prefix):] if name.startswith(prefix) else ""
    return (cookie.get("host") == _HOST and cookie.get("path", "") == "/"
            and re.fullmatch(r"[0-9a-f]{32}", token) is not None
            and cookie.get("value") == token)


def _windows_lock(path):
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    # Firefox itself uses exclusive CreateFileW sharing, not byte-range locks.
    handle = kernel.CreateFileW(str(path), 0xC0000000, 0, None, 4, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error(), "Dedicated profile is locked")
    return lambda: kernel.CloseHandle(handle)


@contextmanager
def _native_lock(profile):
    name = "parent.lock" if sys.platform == "win32" else ".parentlock"
    path = profile / name
    _no_link(path)
    if sys.platform == "win32":
        release = _windows_lock(path)
    else:
        import fcntl
        fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            # flock and fcntl are independent on Linux; Firefox uses F_SETLK.
            fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if sys.platform != "darwin":
                old = profile / "lock"
                if old.is_symlink() and not re.fullmatch(r"[^:]+:\+[0-9]+", os.readlink(old)):
                    # Do not break legacy/network-host locks or infer ownership
                    # from an unrelated PID. Local modern Firefox uses +PID.
                    raise OSError("Unsupported legacy Firefox profile lock")
        except BaseException:
            os.close(fd)
            raise
        release = lambda: os.close(fd)
    try:
        yield
    finally:
        release()


def native_profile_unlocked(profile):
    """Whether an owned profile's native Firefox lock can be acquired now.

    Call only after the owned launch process has exited and its inherited output
    pipe reached EOF. A successful instantaneous lock probe alone cannot exclude
    a still-starting browser child that has not acquired the profile yet. This
    function neither rewrites state nor releases the application's lifetime
    lease; retain that lease (and do not report finished) while this returns
    False. Path/link violations raise instead of following another profile.
    """
    profile = validate_profile_path(profile)
    if not profile.is_dir():
        raise BrowserProfileError("专用浏览器资料目录不存在，无法确认退出。")
    try:
        with _native_lock(profile):
            return True
    except OSError:
        # Busy, unsupported legacy lock, and inability to inspect are all unsafe
        # to treat as successful shutdown. Never modify/break a native lock.
        return False


class ProfileLease:
    """One owning application session, from preparation through process exit.

    Call prepare() before starting Firefox (after restricting the directory ACL),
    and close() only after the owned Firefox process is gone. Run disk methods on
    one worker/asyncio.to_thread, not concurrently. Native Firefox lock protects
    offline rewriting; a separate app lock stays held across the launch handoff.
    """

    def __init__(self, profile):
        self.profile = validate_profile_path(profile)
        self._release = None
        self.ready_cookie = None
        self.needs_cookie_clear = False
        self._clear_token = None

    def _acquire(self):
        self.profile = validate_profile_path(self.profile)
        if not self.profile.is_dir():
            raise BrowserProfileError("专用浏览器资料目录不存在。")
        path = self.profile / ".idv-browser-owner.lock"
        _no_link(path)
        if sys.platform == "win32":
            self._release = _windows_lock(path)
        else:
            import fcntl
            fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                # flock is deliberately used only for our own lifetime lease.
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BaseException:
                os.close(fd)
                raise
            self._release = lambda: os.close(fd)

    def _paths(self):
        names = list(_CORE)
        prefs = self.profile / "prefs.js"
        if prefs.exists():
            contents = _read_bounded(prefs, 4 * 1024 * 1024).decode("utf-8", "replace")
            ids = re.findall(
                r'user_pref\("browser\.sessionstore\.upgradeBackup\.latestBuildID",\s*"([0-9]+)"\);',
                contents)
            if ids:
                names.append("sessionstore-backups/upgrade.jsonlz4-" + ids[-1])
        # Mozilla first exhausts compressed candidates, then tries the old .js
        # equivalents in the same order. Never choose an upgrade just by mtime.
        load_order = [self.profile / name for name in names + [_legacy(n) for n in names]]
        targets = set(load_order)
        backups = self.profile / "sessionstore-backups"
        _no_link(backups)
        if backups.exists():
            if not backups.is_dir():
                raise BrowserProfileError("浏览器恢复目录无效。")
            targets.update(backups.glob("upgrade.jsonlz4-*"))
            targets.update(backups.glob("upgrade.js-*"))
        # Non-selected upgrades also must not retain replayable login URLs.
        existing = []
        for path in targets:
            _no_link(path)
            if path.exists():
                if not path.is_file():
                    raise BrowserProfileError("浏览器恢复文件无效。")
                existing.append(path)
        return load_order, existing

    def prepare(self):
        """Acquire lease and sanitize native recovery; return a warning or None.

        A corrupt/unknown native document can only become a fresh login or a
        known-schema fallback. A lock/I/O/path failure instead raises and MUST
        abort browser launch, as not all replayable sources may be neutralized.
        """
        if self._release is not None:
            raise BrowserProfileError("浏览器资料已被此会话占用。")
        try:
            self._acquire()
            with _native_lock(self.profile):
                return self._prepare_locked()
        except BaseException as error:
            self.close()
            if isinstance(error, BrowserProfileError):
                raise
            if isinstance(error, (OSError, ValueError, RuntimeError)):
                raise BrowserProfileError("无法安全准备专用浏览器资料。请关闭该资料对应的 Firefox 窗口后重试。") from None
            raise

    def _prepare_locked(self):
        load_order, targets = self._paths()
        selected = None
        warning = None
        for path in load_order:
            if not path.exists():
                continue
            try:
                selected = _read_state(path)
                break
            except (ValueError, UnicodeError, lz4.block.LZ4BlockError):
                warning = _WARNING
        cookies = selected.get("cookies", []) if selected is not None else []
        if targets and selected is None:
            warning = _WARNING

        marker = self.profile / _MARKER
        witnessed = None
        if marker.exists() or marker.is_symlink():
            try:
                saved = json.loads(_read_bounded(marker, 1024))
                token = saved.get("token") if isinstance(saved, dict) and saved.get("version") == 1 else None
                if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token):
                    raise ValueError("Invalid clear marker")
                witnessed = next((c for c in cookies if _internal(c, _CLEAR_PREFIX) and c["value"] == token), None)
            except (ValueError, UnicodeError):
                warning = _WARNING
            if witnessed is None:
                self.needs_cookie_clear = True
                # The last native snapshot predates a requested clear. Never
                # resurrect old partitioned OR unpartitioned cookies from it.
                # Persistent cookies are Firefox-owned in cookies.sqlite: keep
                # the marker and require a live BiDi clear after our ready
                # sentinel restores, before any login navigation can occur.
                cookies = []

        # Only our exact reserved-origin marker namespace is removed. Site
        # cookie dictionaries (including unknown metadata) are left untouched.
        cookies = [c for c in cookies if not _internal(c, _READY_PREFIX)
                   and (not _internal(c, _CLEAR_PREFIX) or c is witnessed)]
        ready = _native_cookie(_READY_PREFIX, uuid.uuid4().hex)
        cookies.append(ready)
        now = int(time.time() * 1000)
        clean = {"version": ["sessionrestore", 1], "cookies": cookies,
                 "windows": [{"tabs": [{"entries": [{"url": "about:blank"}], "index": 1}], "selected": 1}],
                 "selectedWindow": 1, "session": {"lastUpdate": now, "startTime": now, "recentCrashes": 0}}
        data = json.dumps(clean, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(data) > _MAX_STATE:
            raise BrowserProfileError("浏览器恢复状态过大，无法安全准备资料。")
        packed = _MAGIC + lz4.block.compress(data, store_size=True)
        # Write every existing fallback, then the primary. If interrupted, the
        # next invocation repeats preparation under both locks before launching.
        for path in targets:
            _atomic_write(path, packed if _compressed(path) else data)
        _atomic_write(self.profile / _CORE[0], packed)
        if marker.exists() and witnessed is not None:
            # Retain the witnessed cookie until this removal is durable. A crash
            # here can retry without throwing away cookies from a new login.
            marker.unlink()
            _sync_directory(self.profile)
        self.ready_cookie = _bidi_cookie(ready)
        return warning

    def mark_cookies_cleared(self):
        """Persist intent BEFORE deleteCookies; return the post-clear sentinel.

        Integration order: mark -> BiDi deleteCookies({}) -> BiDi setCookie with
        returned cookie -> confirm_cookies_cleared(). The marker must survive a
        crash until prepare() observes its exact witness in a native snapshot.
        """
        if self._release is None:
            raise BrowserProfileError("浏览器资料未被当前会话锁定。")
        token = uuid.uuid4().hex
        payload = json.dumps({"version": 1, "token": token}).encode("utf-8")
        _atomic_write(self.profile / _MARKER, payload)
        self._clear_token = token
        return _bidi_cookie(_native_cookie(_CLEAR_PREFIX, token))

    def confirm_cookies_cleared(self):
        """Record successful BiDi sequencing; do NOT remove the durable marker."""
        if self._clear_token is None:
            raise BrowserProfileError("清除 Cookie 的状态顺序无效。")
        self._clear_token = None
        self.needs_cookie_clear = False

    def close(self):
        """Release only our lease, never touch a running Firefox's native state."""
        if self._release is not None:
            release, self._release = self._release, None
            release()

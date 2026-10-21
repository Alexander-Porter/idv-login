"""Owned external Firefox sessions over the standard WebDriver BiDi protocol.

No WebView, patched browser, browser extension or browser-driver runtime is
bundled. Only a dedicated application profile is opened. The browser's local
Remote Agent rejects web Origin headers; system access is never enabled.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import threading
import uuid
from urllib.parse import urljoin, urlsplit

import aiohttp

from browser_profile import BrowserProfileError, ProfileLease, validate_profile_path, native_profile_unlocked
from browser_cookies import CookieExportError

UI_ORIGIN = "https://idv-login.invalid"
SUPPORTED_FIREFOX_MAJORS = (153, 158)


class BrowserUnavailable(RuntimeError):
    pass


class _CommandError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__("Browser command failed: " + code)


_GONE_REALM = {"no such frame", "no such realm", "no such handle", "no such window"}


def browser_executable() -> str:
    """Find an ordinary installed Firefox, never install it or use its profile."""
    candidates = []
    if sys.platform == "win32":
        for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(variable)
            if base:
                candidates.append(Path(base) / "Mozilla Firefox" / "firefox.exe")
        # App Paths supports a user-selected install location. No account or
        # browser-profile registry data is inspected.
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            with contextlib.suppress(OSError):
                with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe") as key:
                    candidates.append(Path(winreg.QueryValue(key, None)))
    elif sys.platform == "darwin":
        homes = [Path.home()]
        if os.environ.get("SUDO_USER"):
            import pwd
            with contextlib.suppress(KeyError):
                homes.append(Path(pwd.getpwnam(os.environ["SUDO_USER"]).pw_dir))
        for folder in [Path("/Applications"), *(home / "Applications" for home in homes)]:
            candidates.append(folder / "Firefox.app/Contents/MacOS/firefox")
    executable = shutil.which("firefox")
    if executable:
        candidates.append(Path(executable))
    unsupported = None
    for candidate in dict.fromkeys(candidates):
        if candidate.is_file():
            try:
                _check_browser_version(str(candidate))
                return str(candidate)
            except BrowserUnavailable as error:
                unsupported = str(error)
    if unsupported:
        raise BrowserUnavailable(unsupported)
    raise BrowserUnavailable(
        "此版本使用独立 Firefox 窗口，不再内嵌浏览器。请从 https://www.mozilla.org/firefox/ "
        "安装受支持的 Firefox 153 ESR 或 158 正式版后重试。工具不会自动安装，也不会读取您日常浏览器的资料。"
    )



def _check_browser_version(executable):
    """Check without opening any profile; unknown sessionstore layouts are unsafe.

    Firefox handles --version before XPCOM/profile startup. Ordinary supported
    ESR/release builds are used, but a future major must be audited before its
    recovery-file set is trusted. Never discover incompatibility *after* opening
    an existing profile with automatic native session restoration enabled.
    """
    import subprocess
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    try:
        command = [executable, "--version"]
        if sys.platform == "win32":
            # Keep the Windows launcher attached to our inherited stdout pipes
            # even when the native host is elevated. This is version-only: the
            # browser exits before profile startup.
            command.append("--wait-for-browser")
        result = subprocess.run(command, capture_output=True,
                                timeout=10, check=True, **options)
        output = (result.stdout + result.stderr).decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError):
        raise BrowserUnavailable("无法检查 Firefox 版本，请确认官方 Firefox 可以启动后重试。") from None
    match = re.search(r"(?m)^Mozilla Firefox (153\.\d+(?:\.\d+)?esr|158\.\d+(?:\.\d+)?)\s*$", output)
    if not match:
        raise BrowserUnavailable(
            "当前工具已验收 Firefox 153 ESR 和 158 正式版的资料格式；不会用未经核验的新版本打开登录资料。"
            "请使用 Firefox 153 ESR，或更新本工具后重试。")
    return match[1]


def _protect_profile(profile):
    """Restrict only the application's own profile, including child DB files."""
    if sys.platform != "win32":
        profile.chmod(0o700)
        return
    # Python 3.12 mkdir(mode=0700) does not implement a private Windows DACL.
    # Use the current token's SID, not an unqualified account name. Neither the
    # command output nor the profile's account data is ever written to a log.
    import csv
    import subprocess
    system32 = Path(os.environ["SystemRoot"]) / "System32"
    output = subprocess.check_output(
        [str(system32 / "whoami.exe"), "/user", "/fo", "csv", "/nh"],
        timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
    row = next(csv.reader([output.decode("utf-8", "replace").strip()]))
    sid = row[-1]
    if not re.fullmatch(r"S-1-(?:[0-9]+-)*[0-9]+", sid):
        raise RuntimeError("Unable to determine profile owner")
    subprocess.run(
        [str(system32 / "icacls.exe"), str(profile), "/inheritance:r", "/grant:r",
         f"*{sid}:(OI)(CI)(F)", "*S-1-5-18:(OI)(CI)(F)",
         "*S-1-5-32-544:(OI)(CI)(F)"],
        check=True, capture_output=True, timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW)


def _decode(value):
    kind = value.get("type")
    raw = value.get("value")
    if kind in ("undefined", "null"):
        return None
    if kind == "array":
        return [_decode(item) for item in raw]
    if kind == "object":
        return {key if isinstance(key, str) else str(_decode(key)): _decode(item)
                for key, item in raw}
    return raw


def _bytes(value):
    if value.get("type") == "base64":
        return base64.b64decode(value["value"])
    return value.get("value", "").encode("utf-8")


def _http_origin(url):
    """Canonical HTTP origin for browser-provided provenance, never a log value."""
    parsed = urlsplit(url)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username is not None or parsed.password is not None):
        raise ValueError("Invalid browser origin")
    port = parsed.port
    return (parsed.scheme, parsed.hostname.lower(),
            port if port is not None else (443 if parsed.scheme == "https" else 80))


class BrowserRuntime:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.sessions = set()
        self.thread = threading.Thread(target=self.loop.run_forever,
                                       name="external-browser", daemon=True)
        self.thread.start()

    @classmethod
    def instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def submit(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop)

    @classmethod
    def shutdown(cls):
        runtime = cls._instance
        if runtime is None:
            return

        async def stop():
            await asyncio.gather(*(session._finish() for session in tuple(runtime.sessions)),
                                 return_exceptions=True)
        try:
            runtime.submit(stop()).result(timeout=20)
        except Exception:
            pass
        finally:
            runtime.loop.call_soon_threadsafe(runtime.loop.stop)
            runtime.thread.join(timeout=2)
            cls._instance = None


class _Frame:
    def __init__(self, context, url="about:blank", parent=None):
        self.context = context
        self.url = url
        self.parent = parent
        self.page = None
        self.navigation = None
        self.document_ready = False
        self.suspended_realms = set()


class _Page:
    def __init__(self, session, page_id, frame, owned=True):
        self.session, self.page_id, self.main_frame = session, page_id, frame
        self.owned = owned
        frame.page = self

    async def close(self):
        await self.session.command("browsingContext.close", {"context": self.main_frame.context})


class _Request:
    def __init__(self, *, url, method, frame, headers=None, body=None,
                 navigation=False, source_url=None):
        self.url, self.method, self.frame = url, method, frame
        self.headers, self.post_data = headers or {}, body
        self.source_url = frame.url if source_url is None else source_url
        self._navigation = navigation

    def is_navigation_request(self):
        return self._navigation


class _Route:
    """Minimal shared transport for virtual document loads and native fetch RPC."""
    def __init__(self, session, request, request_id=None, reply=None):
        self.session, self.request = session, request
        self.request_id, self.reply = request_id, reply
        self.done = False

    async def fulfill(self, *, status=200, headers=None, body=b"", content_type=None):
        if self.done:
            return
        self.done = True
        headers = dict(headers or {})
        if content_type:
            headers["Content-Type"] = content_type
        if isinstance(body, str):
            body = body.encode("utf-8")
        encoded = base64.b64encode(body).decode("ascii")
        if self.reply:
            realm, request_id = self.reply
            # Reply only to the originating realm. A new page after navigation
            # cannot receive an earlier account response.
            payload = {"id": request_id, "status": status, "headers": headers, "body": encoded}
            try:
                await self.session._evaluate(
                    f"globalThis[{json.dumps(self.session._reply_name)}]({json.dumps(payload)})",
                    realm=realm)
            except _CommandError as error:
                if error.code not in _GONE_REALM:
                    raise  # Navigating away cancels a reply, not the whole UI.
        else:
            await self.session.command("network.provideResponse", {
                "request": self.request_id, "statusCode": status,
                "headers": [{"name": name, "value": {"type": "string", "value": str(value)}}
                            for name, value in headers.items()],
                "body": {"type": "base64", "value": encoded},
            })

    async def abort(self, reason="blockedbyclient"):
        if self.done:
            return
        if self.reply:
            await self.fulfill(status=403, body="Forbidden")
        else:
            self.done = True
            await self.session.command("network.failRequest", {"request": self.request_id})

    async def continue_(self):
        if not self.done:
            self.done = True
            await self.session.command("network.continueRequest", {"request": self.request_id})


class BrowserSession:
    def __init__(self, *, dispatch, on_event, profile_path, persistent=True,
                 user_agent="", scripts=(), size=(1000, 750),
                 callback_schemes=(), route_handler=None, bridge_messages=False, cookie_export=None):
        self.runtime = BrowserRuntime.instance()
        self.dispatch, self.on_event = dispatch, on_event
        self.profile_path, self.persistent = profile_path, persistent
        self.user_agent, self.scripts, self.size = user_agent, tuple(scripts), size
        self.callback_schemes = frozenset(callback_schemes)
        self.route_handler = route_handler
        self.bridge_messages = bridge_messages
        self.cookie_export = cookie_export
        self._export_context = None
        self.pages, self.frames = {}, {}
        self._main_context = None
        self._live_realms = {}
        self._closing_pages = set()
        self._process_lock = asyncio.Lock()
        self._stdout_eof = asyncio.Event()
        self._endpoint_future = None
        self._owned_profile = None
        self._exit_confirmed = False
        self._startup_complete = False
        self._finished_event = asyncio.Event()
        self._finish_task = None
        self._profile_lease = None
        self._sequence, self._pending = 0, {}
        self._finishing = self._finished = False
        self._process = self._http = self._ws = self._temp_profile = None
        self._tasks = set()
        self._cookie_snapshot = []
        self._have_cookie_snapshot = False
        self._cookie_exports = {}
        self._cookie_export_urls = {}
        self._cookie_revision = 0
        self._cookie_export_error = False
        self._cookie_clear_pending = False
        self._cookie_clear_epoch = 0
        self._committed_cookie_token = None
        self._channel = uuid.uuid4().hex
        self._reply_name = "__idv_reply_" + uuid.uuid4().hex

    @property
    def is_closing(self):
        return self._finishing or self._finished

    def emit(self, event, *args):
        self.dispatch(lambda: self.on_event(event, *args))

    def _page_event(self, event, page_id, *args, cookie_token=None):
        # Keep the public provider url/loaded signatures unchanged. The adjacent
        # boundary binds that exact event to an immutable, scoped export.
        if self.cookie_export is not None:
            self.emit("cookie_boundary", page_id, cookie_token)
        self.emit(event, page_id, *args)

    def _task(self, coroutine):
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        def done(future):
            if not future.cancelled() and future.exception() and not self._finishing:
                if isinstance(future.exception(), CookieExportError):
                    self._cookie_export_failed()
                else:
                    self.emit("error", "独立浏览器通信失败，请取消本次操作后重试。")
                self._task(self._finish())
        task.add_done_callback(done)
        return task

    def start(self, url):
        self.runtime.submit(self._start(url))

    async def _start(self, url):
        self.runtime.sessions.add(self)
        try:
            executable = await asyncio.to_thread(browser_executable)
            expected_version = await asyncio.to_thread(_check_browser_version, executable)
            async with self._process_lock:
                if self._finishing:
                    return
                if self.persistent:
                    profile = validate_profile_path(self.profile_path)
                    profile.mkdir(parents=True, mode=0o700, exist_ok=True)
                else:
                    self._temp_profile = tempfile.TemporaryDirectory(prefix="idv-login-firefox-")
                    profile = Path(self._temp_profile.name).resolve()
                self._owned_profile = profile
                await asyncio.to_thread(_protect_profile, profile)
                if self.persistent:
                    self._profile_lease = ProfileLease(profile)
                    warning = await asyncio.to_thread(self._profile_lease.prepare)
                    if warning:
                        self.emit("warning", warning)
                # Every preference below applies ONLY to our own profile. Explicit
                # scheme preferences precede Firefox's external handler dispatch,
                # including when another installed application owns that scheme.
                prefs = {
                    "network.proxy.type": 0,
                    "network.protocol-handler.external-default": False,
                    "remote.prefs.recommended": False,
                    "browser.shell.checkDefaultBrowser": False,
                    "browser.aboutwelcome.enabled": False,
                    "signon.rememberSignons": False,
                    "browser.formfill.enable": False,
                    "browser.startup.page": 3 if self.persistent else 0,
                    "browser.sessionstore.privacy_level": 0,
                    "browser.startup.homepage": "about:blank",
                    "browser.startup.homepage_override.mstone": "ignore",
                    "browser.sessionstore.resume_from_crash": False,
                    "dom.serviceWorkers.enabled": self.route_handler is None,
                    "devtools.jsonview.enabled": False,
                    "intl.accept_languages": "zh-CN,zh,en-US,en",
                }
                for scheme in self.callback_schemes:
                    prefs["network.protocol-handler.external." + scheme] = False
                if self.user_agent:
                    prefs["general.useragent.override"] = self.user_agent
                from secure_write import write_file_restricted
                write_file_restricted(str(profile / "user.js"), "\n".join(
                    f"user_pref({json.dumps(key)}, {json.dumps(value)});"
                    for key, value in prefs.items()).encode("utf-8"))
                env = dict(os.environ)
                for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy",
                            "all_proxy", "MOZ_REMOTE_ALLOW_SYSTEM_ACCESS", "MOZ_DISABLE_CONTENT_SANDBOX"):
                    env.pop(key, None)
                options = {}
                if sys.platform == "win32":
                    import subprocess
                    options["creationflags"] = subprocess.CREATE_NO_WINDOW
                if self._finishing:
                    return
                self._process = await asyncio.create_subprocess_exec(
                        executable, "--no-remote", "--profile", str(profile),
                        "--remote-debugging-port=0", "--width", str(self.size[0]),
                        "--height", str(self.size[1]), "about:blank",
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                        env=env, **options)
                # Exactly one reader owns the pipe from launch through EOF,
                # including cancellation before an endpoint has been printed.
                self._endpoint_future = asyncio.get_running_loop().create_future()
                self._task(self._drain_process())
            address = await asyncio.wait_for(self._endpoint_future, 30)
            if self._finishing:
                return
            self._http = aiohttp.ClientSession(trust_env=False)
            # No Origin header, allow-origin override, system access or public
            # bind. Never attach to an existing browser/debugging endpoint.
            self._ws = await self._http.ws_connect(address, max_msg_size=16 * 1024 * 1024)
            if self._finishing:
                await self._ws.close()
                return
            self._task(self._read())
            result = await self.command("session.new", {"capabilities": {"alwaysMatch": {"acceptInsecureCerts": False}}})
            version = result["capabilities"]["browserVersion"]
            if version.removesuffix("esr") != expected_version.removesuffix("esr"):
                raise BrowserUnavailable("Firefox 在启动期间发生更新，请退出浏览器后重试。")
            tree = await self.command("browsingContext.getTree", {})
            self._main_context = tree["contexts"][0]["context"]
            for info in tree["contexts"]:
                self._register_context(info)
            await self.command("session.subscribe", {"events": [
                "browsingContext.contextCreated", "browsingContext.contextDestroyed",
                "browsingContext.navigationStarted", "browsingContext.navigationFailed",
                "browsingContext.domContentLoaded", "browsingContext.load",
                "browsingContext.fragmentNavigated", "browsingContext.historyUpdated",
                "log.entryAdded", "script.message", "script.realmDestroyed", "network.responseStarted",
            ]})
            if self.route_handler:
                await self.command("session.subscribe", {"events": ["network.beforeRequestSent"]})
                await self.command("network.addIntercept", {"phases": ["beforeRequestSent"]})
            script = self._preload_script()
            await self.command("script.addPreloadScript", {
                "functionDeclaration": script,
                "arguments": [{"type": "channel", "value": {"channel": self._channel}}],
            })
            if self._profile_lease:
                await self._wait_for_native_restore()
            await self._cookies()
            if self.cookie_export is not None:
                self._task(self._poll_cookies())
            if self._finishing:
                return
            self._startup_complete = True
            self.emit("ready", "main")
            await self._navigate("main", url)
        except Exception as error:
            if self._finishing:
                return
            self.emit("startup_failed", str(error) if isinstance(error, (BrowserUnavailable, BrowserProfileError)) else
                      "无法启动独立 Firefox。请确认浏览器已更新、资料目录未被占用，且未受组织策略限制。")
            await self._finish()

    async def command(self, method, params, timeout=30):
        if self._finishing and method not in ("storage.getCookies", "browser.close"):
            raise RuntimeError("Browser closing")
        if self._ws is None or self._ws.closed:
            raise RuntimeError("Browser transport closed")
        self._sequence += 1
        sequence = self._sequence
        future = asyncio.get_running_loop().create_future()
        self._pending[sequence] = future
        try:
            await self._ws.send_json({"id": sequence, "method": method, "params": params})
            return await asyncio.wait_for(future, timeout)
        finally:
            self._pending.pop(sequence, None)

    async def _read(self):
        async for message in self._ws:
            if message.type != aiohttp.WSMsgType.TEXT:
                continue
            data = json.loads(message.data)
            if "id" in data:
                future = self._pending.get(data["id"])
                if future is not None and not future.done():
                    if data.get("type") == "error":
                        # Remote exception strings can include login secrets.
                        future.set_exception(_CommandError(data.get("error", "unknown")))
                    else:
                        future.set_result(data.get("result", {}))
            elif data.get("type") == "event":
                self._task(self._event(data["method"], data["params"]))
        for future in tuple(self._pending.values()):
            if not future.done():
                future.set_exception(RuntimeError("Browser disconnected"))
        if not self._finishing:
            await self._finish()

    async def _drain_process(self):
        # Browser diagnostics can contain URLs. Consume but never persist them.
        buffer = b""
        while True:
            chunk = await self._process.stdout.read(4096)
            if not chunk:
                self._stdout_eof.set()
                break
            if self._endpoint_future is not None and not self._endpoint_future.done():
                buffer = (buffer + chunk)[-16384:]
                match = re.search(rb"(?m)^WebDriver BiDi listening on (ws://(?:127\.0\.0\.1|localhost|\[::1\]):\d+)\r?\n", buffer)
                if match:
                    self._endpoint_future.set_result(match[1].decode("ascii") + "/session")
                    buffer = b""
        if self._endpoint_future is not None and not self._endpoint_future.done():
            self._endpoint_future.set_exception(BrowserUnavailable(
                "Firefox 未能启动，专用资料目录可能正在使用。请关闭工具上次打开的浏览器窗口后重试。"))
        await self._process.wait()
        if not self._finishing and self._startup_complete:
            await self._finish()

    def _register_context(self, info, page_id=None):
        context = info["context"]
        if context in self.frames:
            return self.frames[context]
        parent = self.frames.get(info.get("parent"))
        frame = _Frame(context, info.get("url", "about:blank"), parent)
        self.frames[context] = frame
        if info.get("parent") is None:
            identity = page_id or ("main" if context == self._main_context else context)
            opener = self.frames.get(info.get("originalOpener"))
            owned = context == self._main_context or bool(opener and opener.page and opener.page.owned)
            page = _Page(self, identity, frame, owned=owned)
            self.pages[identity] = page
            self.emit("page", identity)
        elif parent:
            frame.page = parent.page
        for child in info.get("children") or []:
            self._register_context(child)
        return frame

    async def _event(self, method, params):
        if self._finishing:
            return
        if method == "browsingContext.contextCreated":
            self._register_context(params)
            return
        if method == "browsingContext.contextDestroyed":
            frame = self.frames.pop(params["context"], None)
            if frame and frame.page and frame is frame.page.main_frame:
                self.pages.pop(frame.page.page_id, None)
                self.emit("page_closed", frame.page.page_id)
                if frame.context == self._main_context:
                    await self._finish()
            return
        if method == "script.realmDestroyed":
            realm = params["realm"]
            self._live_realms.pop(realm, None)
            for frame in self.frames.values():
                frame.suspended_realms.discard(realm)
            self.emit("realm_destroyed", realm)
            return
        if method == "script.message":
            await self._message(params)
            return
        if method == "network.beforeRequestSent":
            await self._request(params)
            return
        context = params.get("context") or params.get("source", {}).get("context")
        frame = self.frames.get(context)
        if frame is None or frame.page is None:
            return
        if not frame.page.owned:
            return
        page_id = frame.page.page_id
        if method == "network.responseStarted":
            response = params.get("response", {})
            if 300 <= response.get("status", 0) < 400:
                location = next((_bytes(h["value"]).decode("utf-8", "replace")
                                 for h in response.get("headers", [])
                                 if h["name"].lower() == "location"), "")
                target = urljoin(params["request"]["url"], location)
                if urlsplit(target).scheme in self.callback_schemes:
                    # Gecko blocks OS dispatch in the profile before handling
                    # custom schemes. Redirects do not emit a second
                    # navigationStarted, so capture the original Location.
                    token = await self._cookies(frame.page.main_frame)
                    self._page_event("url", page_id, target, cookie_token=token)
        elif method == "log.entryAdded" and params.get("type") == "console":
            self.emit("console", page_id, params.get("level", "info"), params.get("text", ""), 0, "")
        elif method == "browsingContext.navigationStarted":
            frame.navigation = params.get("navigation")
            frame.document_ready = False
            for realm, owner_context in tuple(self._live_realms.items()):
                if owner_context == frame.context:
                    frame.suspended_realms.add(realm)
                    self._live_realms.pop(realm, None)
            if frame is frame.page.main_frame:
                self.emit("document_invalidated", page_id)
            url = params.get("url", "")
            if urlsplit(url).scheme in self.callback_schemes:
                token = await self._cookies(frame.page.main_frame)
                self._page_event("url", page_id, url, cookie_token=token)
        elif method in ("browsingContext.domContentLoaded", "browsingContext.fragmentNavigated",
                        "browsingContext.historyUpdated"):
            if (method == "browsingContext.domContentLoaded" and frame.navigation
                    and params.get("navigation") != frame.navigation):
                return
            frame.url = params.get("url", frame.url)
            if method == "browsingContext.domContentLoaded":
                frame.document_ready = True
                frame.suspended_realms.clear()
            if frame is frame.page.main_frame:
                navigation, source_url = frame.navigation, frame.url
                token = await self._cookies(frame)
                if frame.navigation != navigation or frame.url != source_url:
                    return
                self._page_event("url", page_id, source_url, cookie_token=token)
        elif method == "browsingContext.load":
            navigation = params.get("navigation")
            if frame.navigation and navigation != frame.navigation:
                return
            if frame is frame.page.main_frame:
                frame.url = params.get("url", frame.url)
                frame.document_ready = True
                frame.suspended_realms.clear()
                source_url = frame.url
                token = await self._cookies(frame)
                if frame.navigation and navigation != frame.navigation:
                    return
                if frame.url != source_url:
                    return
                self._page_event("url", page_id, source_url, cookie_token=token)
                self._page_event("loaded", page_id, True, cookie_token=token)
                if self.bridge_messages and frame.page.owned:
                    realms = await self.command("script.getRealms", {"context": frame.context, "type": "window"})
                    if frame.navigation and navigation != frame.navigation:
                        return
                    realm = next((r["realm"] for r in realms["realms"] if not r.get("sandbox")), None)
                    if realm:
                        self._live_realms[realm] = frame.context
                        self.emit("document_loaded", page_id, realm, frame.url)
        elif method == "browsingContext.navigationFailed":
            if frame is frame.page.main_frame:
                navigation = params.get("navigation")
                if navigation != frame.navigation:
                    return
                if self.bridge_messages and frame.suspended_realms:
                    with contextlib.suppress(_CommandError):
                        realms = await self.command("script.getRealms", {
                            "context": frame.context, "type": "window"})
                        if navigation != frame.navigation:
                            return
                        for item in realms["realms"]:
                            realm = item["realm"]
                            if "sandbox" in item or realm not in frame.suspended_realms:
                                continue
                            actual_url = await self._evaluate("location.href", realm=realm)
                            if (navigation != frame.navigation
                                    or realm not in frame.suspended_realms
                                    or self.frames.get(frame.context) is not frame):
                                return
                            if not isinstance(actual_url, str):
                                continue
                            frame.url = actual_url
                            frame.document_ready = True
                            self._live_realms[realm] = frame.context
                            self.emit("document_restored", page_id, realm, actual_url)
                        frame.suspended_realms.clear()
                self._page_event("loaded", page_id, False)

    async def _request(self, event):
        if not event.get("isBlocked"):
            return
        data = event["request"]
        frame = self.frames.get(event.get("context"))
        if frame is None:
            await self.command("network.failRequest", {"request": data["request"]})
            return
        headers = {item["name"].lower(): _bytes(item["value"]).decode("utf-8", "replace")
                   for item in data.get("headers", [])}
        request = _Request(url=data["url"], method=data["method"], frame=frame,
                           headers=headers, navigation=event.get("navigation") is not None)
        route = _Route(self, request, request_id=data["request"])
        try:
            await self.route_handler(route)
        finally:
            if not route.done:
                await route.abort()

    def _preload_script(self):
        # A single ordered MainWorld script preserves the OPPO/Bili bridges.
        # The UI fetch channel is installed only in the reserved trusted origin.
        bridge = r'''(send) => {
          const schemes = new Set(SCHEMES);
          const capture = value => {
            let url; try { url = new URL(String(value), location.href); } catch { return false; }
            if (!schemes.has(url.protocol.slice(0, -1))) return false;
            send({kind: 'callback', url: url.href}); return true;
          };
          const open = window.open;
          window.open = function(url, ...args) { return capture(url) ? null : open.call(this, url, ...args); };
          document.addEventListener('click', event => {
            const link = event.target.closest?.('a[href],area[href]');
            if (link && capture(link.href)) event.preventDefault();
          }, true);
          if (location.origin === ORIGIN && IS_UI) {
            const pending = new Map(); let sequence = 0;
            Object.defineProperty(globalThis, REPLY, {value: data => {
              const item = pending.get(data.id); if (!item) return;
              pending.delete(data.id); item.cleanup();
              const bytes = Uint8Array.from(atob(data.body), char => char.charCodeAt(0));
              item.resolve(new Response(bytes, {status: data.status, headers: data.headers}));
            }});
            const fetch = globalThis.fetch.bind(globalThis);
            globalThis.fetch = async (input, init) => {
              const request = new Request(input, init);
              const url = new URL(request.url);
              if (url.origin !== ORIGIN || !url.pathname.startsWith('/_idv-login/') || url.pathname === '/_idv-login/index') return fetch(request);
              const body = request.method === 'GET' || request.method === 'HEAD' ? null : await request.text();
              if (request.signal.aborted) throw new DOMException('Aborted', 'AbortError');
              return new Promise((resolve, reject) => {
                const id = ++sequence;
                const abort = () => { pending.delete(id); reject(new DOMException('Aborted', 'AbortError')); };
                const cleanup = () => request.signal.removeEventListener('abort', abort);
                pending.set(id, {resolve, reject, cleanup});
                request.signal.addEventListener('abort', abort, {once: true});
                send({kind: 'request', id, url: request.url, method: request.method, body});
              });
            };
          }
          SCRIPTS
        }'''
        return (bridge.replace("SCHEMES", json.dumps(sorted(self.callback_schemes)))
                .replace("ORIGIN", json.dumps(UI_ORIGIN))
                .replace("REPLY", json.dumps(self._reply_name))
                .replace("IS_UI", "true" if self.route_handler else "false")
                .replace("SCRIPTS", "\n;\n".join(self.scripts)))

    async def _message(self, params):
        if params.get("channel") != self._channel:
            return
        source = params["source"]
        frame = self.frames.get(source.get("context"))
        if frame is None or frame.page is None:
            return
        data = _decode(params["data"])
        if not isinstance(data, dict):
            return
        if data.get("kind") == "callback":
            url = str(data.get("url", ""))
            if frame.page.owned and urlsplit(url).scheme in self.callback_schemes:
                token = await self._cookies(frame.page.main_frame)
                self._page_event("url", frame.page.page_id, url, cookie_token=token)
        elif data.get("kind") == "native-message" and self.bridge_messages and frame.page.owned:
            # SDK's bridge is installed only after a trusted top-level document
            # has loaded. Ignore stale realms and arbitrary subframe shims.
            if self._live_realms.get(source["realm"]) != frame.context:
                return
            try:
                source_url = await self._evaluate("location.href", realm=source["realm"])
            except _CommandError as error:
                if error.code in _GONE_REALM:
                    return
                raise
            if (isinstance(data.get("request"), str)
                    and self._live_realms.get(source["realm"]) == frame.context):
                self.emit("native_message", frame.page.page_id, source["realm"], source_url, data["request"])
        elif data.get("kind") == "request" and self.route_handler:
            try:
                source_url = await self._evaluate("location.href", realm=source["realm"])
            except _CommandError as error:
                if error.code in _GONE_REALM:
                    return
                raise
            request = _Request(url=str(data.get("url", "")), method=str(data.get("method", "")),
                               frame=frame, body=data.get("body"), source_url=source_url)
            route = _Route(self, request, reply=(source["realm"], data.get("id")))
            try:
                await self.route_handler(route)
            finally:
                if not route.done:
                    await route.abort()

    def _cookie_export_failed(self):
        if self._committed_cookie_token is not None or self._cookie_export_error:
            return  # A later, unrelated page cannot undo an accepted transaction.
        self._cookie_export_error = True
        self._cookie_exports.clear()
        self._cookie_export_urls.clear()
        self._cookie_snapshot = []
        self.emit("cookies", [])
        self.emit("cookie_error", "登录 Cookie 的来源或作用范围无法安全确认，已取消本次操作。请强制退登后重试。")

    def _commit_cookies(self, token):
        if self.cookie_export is None:
            return
        if self._committed_cookie_token is not None:
            return
        try:
            records = self._cookie_exports.get(token)
        except TypeError:
            records = None
        if self._cookie_export_error or self._cookie_clear_pending or records is None:
            self._cookie_export_failed()
            return
        self._committed_cookie_token = token
        self._cookie_snapshot = [dict(cookie) for cookie in records]
        self.emit("cookies_committed", token, [dict(cookie) for cookie in records])

    async def _cookies(self, frame=None):
        # Only current consumers (vivo, 360, 4399 observation) opt in. Never
        # export a generic all-profile jar: BiDi omits partition ownership.
        if (self.cookie_export is None or self._finishing
                or self._committed_cookie_token is not None or self._cookie_export_error
                or self._cookie_clear_pending):
            return
        frame = frame or self.frames.get(self._export_context) or self.frames.get(self._main_context)
        if (frame is None or frame.page is None or not frame.page.owned
                or frame is not frame.page.main_frame or not frame.document_ready
                or not self.cookie_export.matches(frame.url)):
            return
        source_url, navigation = frame.url, frame.navigation
        clear_epoch = self._cookie_clear_epoch
        try:
            if self._ws is None or self._ws.closed:
                raise CookieExportError("Browser cookie transport is unavailable")
            result = await self.command("storage.getCookies", {"partition": {
                "type": "context", "context": frame.context}}, timeout=2)
        except Exception:
            if (clear_epoch != self._cookie_clear_epoch or self._cookie_clear_pending
                    or frame.navigation != navigation or not frame.document_ready
                    or self.frames.get(frame.context) is not frame):
                return
            self._cookie_export_failed()
            raise CookieExportError("Unable to read the completion page's cookies") from None
        if (self._finishing or self._cookie_export_error or self._cookie_clear_pending
                or clear_epoch != self._cookie_clear_epoch
                or self._committed_cookie_token is not None
                or frame.navigation != navigation or frame.url != source_url
                or not frame.document_ready or self.frames.get(frame.context) is not frame):
            return
        # The policy must also filter destination domain/path/secure/expiry and
        # reject ambiguous same-name credentials. Top-site filtering alone is
        # NOT sufficient: a partition may also contain third-party domains.
        try:
            partition = result["partitionKey"]
            if (partition.get("userContext") != "default"
                    or _http_origin(partition["sourceOrigin"]) != _http_origin(source_url)):
                raise CookieExportError("Completion cookie context changed")
            self._cookie_snapshot = self.cookie_export.select(result["cookies"], source_url)
        except Exception:
            self._cookie_export_failed()
            raise CookieExportError("Completion cookie scope could not be verified") from None
        self._have_cookie_snapshot = True
        self._export_context = frame.context
        self._cookie_revision += 1
        token = (frame.page.page_id, frame.context, navigation, self._cookie_revision)
        self._cookie_exports[token] = tuple(dict(cookie) for cookie in self._cookie_snapshot)
        # Keep the exact URL only in this ephemeral transaction, never in saved
        # account metadata. It binds a one-use JSON body read to the same page.
        self._cookie_export_urls[token] = source_url
        # Keep earlier load tokens for asynchronous one-use callback body reads,
        # without growing a credential history indefinitely during a stuck page.
        while len(self._cookie_exports) > 256:
            expired = next(iter(self._cookie_exports))
            self._cookie_exports.pop(expired)
            self._cookie_export_urls.pop(expired, None)
        self.emit("cookies_snapshot", token, [dict(cookie) for cookie in self._cookie_snapshot])
        self.emit("cookies", [dict(cookie) for cookie in self._cookie_snapshot])
        return token

    def navigate(self, page_id, url):
        self.runtime.submit(self._navigate(page_id, url))

    async def _navigate(self, page_id, url):
        page = self.pages.get(page_id)
        if page is None or self._finishing:
            return
        try:
            await self.command("browsingContext.navigate", {
                "context": page.main_frame.context, "url": url, "wait": "none"})
        except Exception:
            if not self._finishing:
                self._page_event("loaded", page_id, False)

    def new_page(self, url):
        page_id = uuid.uuid4().hex
        async def create():
            if self._finishing:
                return
            result = await self.command("browsingContext.create", {"type": "window", "referenceContext": self._main_context})
            context = result["context"]
            if self._finishing:
                return
            if page_id in self._closing_pages:
                await self.command("browsingContext.close", {"context": context})
                return
            # Context-created may precede the command response. Identity lives
            # on the page object, not in event-handler closures, so renaming is
            # atomic and all subsequent popup console/close events use this id.
            frame = self.frames.get(context) or self._register_context({"context": context, "parent": None}, page_id)
            self.pages.pop(frame.page.page_id, None)
            frame.page.page_id = page_id
            frame.page.owned = True  # Explicit host-created popup, not a user tab.
            self.pages[page_id] = frame.page
            await self._navigate(page_id, url)
        self.runtime.submit(create())
        return page_id

    async def _evaluate(self, script, *, context=None, realm=None, strict=False):
        result = await self.command("script.evaluate", {
            "expression": script, "target": {"realm": realm} if realm else {"context": context},
            "awaitPromise": True, "serializationOptions": {"maxObjectDepth": 16},
        })
        if result.get("type") != "success":
            if strict:
                raise RuntimeError("Browser script execution failed")
            return None
        return _decode(result["result"])

    def evaluate(self, page_id, script, callback=None, *, cookie_token=None):
        async def evaluate():
            page = self.pages.get(page_id)
            value = None
            if page is not None and not self._finishing:
                frame = page.main_frame
                def same_cookie_document():
                    return (cookie_token is None or (
                        cookie_token in self._cookie_exports
                        and cookie_token[:3] == (page_id, frame.context, frame.navigation)
                        and self.frames.get(frame.context) is frame and frame.document_ready))
                with contextlib.suppress(Exception):
                    if same_cookie_document():
                        if cookie_token is not None:
                            expected_url = self._cookie_export_urls[cookie_token]
                            realms = await self.command("script.getRealms", {
                                "context": frame.context, "type": "window"})
                            realm = next((item for item in realms["realms"]
                                          if "sandbox" not in item), None)
                            if (realm is not None and same_cookie_document()
                                    and _http_origin(realm["origin"]) == _http_origin(expected_url)):
                                # An exact realm never retargets a newer document
                                # if navigation events arrive late. Check URL in
                                # that realm before evaluating the body as well.
                                expression = ("(() => { if (location.href !== "
                                    + json.dumps(expected_url) + ") return null; const value = ("
                                    + script + "); return {url: location.href, value}; })()")
                                packet = await self._evaluate(expression, realm=realm["realm"])
                                if isinstance(packet, dict) and packet.get("url") == expected_url:
                                    value = packet.get("value")
                        else:
                            value = await self._evaluate(script, context=frame.context)
                        if not same_cookie_document():
                            value = None
            if callback:
                self.dispatch(lambda: callback(value))
        self.runtime.submit(evaluate())

    def is_live_realm(self, realm):
        return realm in self._live_realms and not self._finishing

    def evaluate_in_realm(self, realm, script):
        async def evaluate():
            if self._finishing:
                return
            try:
                await self._evaluate(script, realm=realm, strict=True)
            except _CommandError as error:
                if error.code not in _GONE_REALM:
                    raise
        # Attach the normal failure path rather than silently dropping an
        # exception on a run_coroutine_threadsafe Future nobody awaits.
        async def schedule():
            self._task(evaluate())
        self.runtime.submit(schedule())

    def focus(self, page_id="main"):
        async def focus():
            page = self.pages.get(page_id)
            if page is not None and not self._finishing:
                with contextlib.suppress(Exception):
                    await self.command("browsingContext.activate", {"context": page.main_frame.context})
        self.runtime.submit(focus())

    def clear_cookies(self):
        async def clear():
            try:
                if self._finishing:
                    return
                # Persist the clear intent *before* touching the live store.
                witness = None
                async with self._process_lock:
                    if self._finishing:
                        return
                    if self._profile_lease:
                        witness = await asyncio.to_thread(self._profile_lease.mark_cookies_cleared)
                if self._finishing:
                    return
                await self.command("storage.deleteCookies", {})
                if witness:
                    await self.command("storage.setCookie", {"cookie": witness})
                    self._profile_lease.confirm_cookies_cleared()
            except Exception:
                if self.cookie_export is not None:
                    self._cookie_export_failed()
                raise
            finally:
                self._cookie_clear_pending = False
            await self._cookies()
            await self.command("browsingContext.reload", {"context": self._main_context, "wait": "none"})

        def begin():
            if self._finishing or self._cookie_clear_pending:
                return
            # Revoke synchronously in this loop callback, before scheduling the
            # first filesystem/transport await. A queued success event must not
            # commit its pre-logout token while deletion is in flight.
            self._cookie_clear_pending = True
            self._cookie_clear_epoch += 1
            self._cookie_exports.clear()
            self._cookie_export_urls.clear()
            self._cookie_snapshot = []
            self._have_cookie_snapshot = True
            self.emit("cookies_reset")
            self.emit("cookies", [])
            self._task(clear())
        self.runtime.loop.call_soon_threadsafe(begin)

    def close_page(self, page_id):
        async def close():
            self._closing_pages.add(page_id)
            page = self.pages.get(page_id)
            if page:
                with contextlib.suppress(Exception):
                    await page.close()
        self.runtime.submit(close())

    def finish(self, cookie_token=None):
        self.runtime.submit(self._finish(cookie_token))

    async def _wait_for_native_restore(self):
        # Firefox restores native session cookies asynchronously. Do not send
        # the first login request until our cookie-only snapshot was consumed.
        cookie = self._profile_lease.ready_cookie
        query = {"name": cookie["name"], "domain": cookie["domain"]}
        deadline = asyncio.get_running_loop().time() + 15
        while not self._finishing:
            result = await self.command("storage.getCookies", {"filter": query})
            if any(c["name"] == cookie["name"] and c["value"] == cookie["value"]
                   for c in result["cookies"]):
                if self._profile_lease.needs_cookie_clear:
                    # A previous clear intent may have survived a crash before
                    # deleteCookies. SQLite-backed persistent cookies also must
                    # be removed before the first vendor request, not merely
                    # the session cookies sanitized on disk.
                    async with self._process_lock:
                        if self._finishing:
                            return
                        witness = await asyncio.to_thread(self._profile_lease.mark_cookies_cleared)
                    if self._finishing:
                        return
                    await self.command("storage.deleteCookies", {})
                    await self.command("storage.setCookie", {"cookie": witness})
                    self._profile_lease.confirm_cookies_cleared()
                else:
                    await self.command("storage.deleteCookies", {"filter": query})
                return
            if asyncio.get_running_loop().time() >= deadline:
                raise BrowserUnavailable("Firefox 未完成安全登录状态恢复，请关闭该窗口后重试。")
            await asyncio.sleep(0.05)

    async def _poll_cookies(self):
        while not self._finishing:
            await asyncio.sleep(1)
            if not self._finishing:
                token = await self._cookies()
                if token:
                    frame = self.frames.get(token[1])
                    if frame and frame.document_ready and frame.navigation == token[2]:
                        # Q/T may arrive asynchronously after a successful page
                        # load. Retry the ordinary URL predicate with THIS export.
                        self._page_event("url", frame.page.page_id, frame.url, cookie_token=token)

    async def _finish(self, cookie_token=None):
        # A one-use callback may have closed its context already. Its successful
        # event's exact snapshot is still commit-able; never re-query another page
        # or require that closed callback to be loaded a second time.
        if cookie_token is not None:
            self._commit_cookies(cookie_token)
        if self._finished:
            return
        if self._finishing:
            if self._finish_task is not asyncio.current_task():
                await self._finished_event.wait()
            return
        self._finishing = True
        self._finish_task = asyncio.current_task()
        try:
            # Startup cannot create a process after this barrier. If creation
            # is in flight, wait until ownership has been recorded, then close.
            async with self._process_lock:
                pass
            # Cookie handoff is a separately acknowledged transaction. Closing
            # never manufactures success from whatever snapshot was last seen.
            try:
                if self._ws and not self._ws.closed:
                    with contextlib.suppress(Exception):
                        await self.command("browser.close", {}, timeout=3)
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(self._ws.close(), 3)
                if self._http:
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(self._http.close(), 3)
            finally:
                await self._stop_owned_process()
                await self._confirm_owned_browser_exit()
        finally:
            # Do not release a profile which a still-running process can write,
            # or announce a completed close while its browser remains alive.
            if self._process is not None and not self._exit_confirmed:
                self.emit("error", "独立 Firefox 尚未退出，请关闭该登录浏览器窗口。资料目录仍保持锁定。")
                # Keep ownership, but permit a later drain/close to retry after
                # an interrupted cleanup rather than waiting on a dead task.
                self._finishing = False
                self._finish_task = None
                return
            for task in tuple(self._tasks):
                if task is not asyncio.current_task():
                    task.cancel()
            self.pages.clear()
            self.frames.clear()
            self._live_realms.clear()
            if self._profile_lease:
                self._profile_lease.close()
            if self._temp_profile:
                with contextlib.suppress(OSError):
                    self._temp_profile.cleanup()
            self._finished = True
            self._finished_event.set()
            self.runtime.sessions.discard(self)
            self.emit("finished")

    async def _stop_owned_process(self):
        try:
            if self._process and self._process.returncode is None:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._process.wait(), 4)
                if self._process.returncode is None:
                    with contextlib.suppress(OSError):
                        self._process.terminate()
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(self._process.wait(), 3)
                if self._process.returncode is None:
                    # Kill only the process created by this session, never an
                    # arbitrary Firefox process or the user's normal browser.
                    with contextlib.suppress(OSError):
                        self._process.kill()
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(self._process.wait(), 2)
        finally:
            if self._process and self._process.returncode is None:
                self.emit("error", "请关闭工具打开的 Firefox 登录窗口；退出确认前不会释放登录资料目录。")
                # Keep the lease and await this exact child, not arbitrary
                # Firefox processes. An OS refusal is not successful cleanup.
                await self._process.wait()

    async def _confirm_owned_browser_exit(self):
        if self._process is None:
            self._exit_confirmed = True
            return
        # Windows' launcher may have exited before its browser child. The child
        # inherits our pipe, and the native profile lock is a separate witness.
        # Root PID exit alone must never release a profile still being written.
        if not self._stdout_eof.is_set():
            try:
                await asyncio.wait_for(self._stdout_eof.wait(), 3)
            except asyncio.TimeoutError:
                self.emit("error", "Firefox 登录子窗口尚未完全退出，请关闭工具打开的浏览器窗口。")
                await self._stdout_eof.wait()
        warned = False
        while True:
            try:
                unlocked = await asyncio.to_thread(native_profile_unlocked, self._owned_profile)
            except BrowserProfileError:
                unlocked = False
            if unlocked:
                self._exit_confirmed = True
                return
            if not warned:
                self.emit("error", "Firefox 登录资料仍在使用或无法核验，请关闭工具打开的浏览器窗口；资料锁暂不释放。")
                warned = True
            await asyncio.sleep(0.25)

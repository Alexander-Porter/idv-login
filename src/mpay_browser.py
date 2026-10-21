# SPDX-License-Identifier: GPL-3.0-or-later
"""Pinned MPay helper ABI -> owned external Firefox, never a native renderer.

The SDK owns its login/verification protocol and supplies its own JS bridge.
Only the helper's URL, script and lifecycle boundary is translated here. See
native/mpay_browser_adapter/ABI.md for the version-locked x64 calling contract.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
from urllib.parse import urlsplit

import app_state
from browser_runtime import BrowserSession
from browser_setup import BrowserSetupDialog
from fever_assets import verified_install_asset


_REGISTER, _CREATE, _NAVIGATE, _SCRIPT, _CLEAR, _DESTROY = range(1, 7)
_MAX_MESSAGE = 1024 * 1024
_SHIM = r'''
Object.defineProperty(window, 'mwsInvoke', {configurable: false, value: function(options) {
  if (options && typeof options.request === 'string' && options.request.length <= 1048576) {
    send({kind: 'native-message', request: options.request});
  }
}});
'''


def _origin(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('MPay supplied an unsupported browser address')
    return (parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80))


@dataclass
class _Owner:
    bridge: object
    image: int
    generation: int
    game: str
    active: bool = True

    def valid(self):
        return (self.active and self.bridge._generation == self.generation
                and int(getattr(self.bridge._mpay, '_handle', 0) or 0) == self.image)


@dataclass
class _Context:
    handle: int
    owner: _Owner
    session: BrowserSession | None = None
    revoked: bool = False
    url: str = ''
    size: tuple = (800, 700)
    origins: set = field(default_factory=set)
    realms: dict = field(default_factory=dict)
    dispatch_realm: str | None = None
    startup_error: str | None = None
    dialog: BrowserSetupDialog | None = None
    fresh_profile: bool = False

    def valid(self):
        return not self.revoked and self.owner.valid()


class MpayBrowserAdapter:
    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        if sys.platform != 'win32' or ctypes.sizeof(ctypes.c_void_p) != 8:
            raise RuntimeError('MPay 独立浏览器适配层仅支持 Windows x64。')
        try:
            from mpay_browser_build import MPAY_BROWSER_HELPER_SHA256
        except ImportError as error:
            raise RuntimeError('缺少 MPay 浏览器适配层。源码运行请先执行 native/mpay_browser_adapter/build.ps1。') from error
        path = verified_install_asset('webview_support_helper.dll', MPAY_BROWSER_HELPER_SHA256)
        self.owners, self.contexts = {}, {}
        self._ui_thread = threading.get_ident()
        # The vendor delay-loader uses a basename. Preload our hash-verified
        # absolute path and reject any earlier same-name, foreign module.
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        kernel.GetModuleHandleW.restype = ctypes.c_void_p
        kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32]
        kernel.GetModuleFileNameW.restype = ctypes.c_uint32
        existing = kernel.GetModuleHandleW('webview_support_helper.dll')
        if existing:
            self._verify_module_path(kernel, existing, path)
        self.library = ctypes.CDLL(path)
        self._verify_module_path(kernel, self.library._handle, path)
        abi = self.library.IDV_MpayBrowser_ABIVersion
        abi.argtypes, abi.restype = [], ctypes.c_uint32
        if abi() != 1:
            raise RuntimeError('MPay 浏览器适配层 ABI 不匹配。')
        self._host_type = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_size_t, ctypes.c_int32,
                                          ctypes.c_char_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32)
        self._host_ref = self._host_type(self._host)
        register = self.library.IDV_MpayBrowser_SetHost
        register.argtypes, register.restype = [self._host_type], ctypes.c_uint8
        if not register(self._host_ref):
            raise RuntimeError('MPay 浏览器适配层已被其他宿主占用。')
        for name in ('Loaded', 'CloseHolder'):
            function = getattr(self.library, 'IDV_MpayBrowser_' + name)
            function.argtypes, function.restype = [ctypes.c_size_t], ctypes.c_uint8
        self.library.IDV_MpayBrowser_Message.argtypes = [ctypes.c_size_t, ctypes.c_char_p, ctypes.c_char_p]
        self.library.IDV_MpayBrowser_Message.restype = ctypes.c_uint8
        # Both this object and the CFUNCTYPE remain process-lifetime pinned.

    @staticmethod
    def _verify_module_path(kernel, handle, expected):
        path = ctypes.create_unicode_buffer(32768)
        count = kernel.GetModuleFileNameW(handle, path, len(path))
        if not count or count >= len(path) or os.path.normcase(os.path.realpath(path.value)) != os.path.normcase(os.path.realpath(expected)):
            raise RuntimeError('已加载其他来源的 MPay 浏览器模块，请退出工具后重试。')

    def attach(self, bridge, game):
        app_state._ensure_invoker()  # called on the SDK/Qt owning thread
        image = int(bridge._mpay._handle)
        previous = self.owners.get(image)
        if previous:
            self.retire(bridge, previous.generation)
        self.owners[image] = _Owner(bridge, image, bridge._generation, game)

    def retire(self, bridge, generation):
        for owner in tuple(self.owners.values()):
            if owner.bridge is bridge and owner.generation == generation:
                owner.active = False
                self.owners.pop(owner.image, None)
        for context in tuple(self.contexts.values()):
            if context.owner.bridge is bridge and context.owner.generation == generation:
                self._destroy(context)

    def _host(self, handle, event, text, parameter, width, height):
        """Native callbacks are synchronous on the original MPay UI thread."""
        try:
            if event != _DESTROY and threading.get_ident() != self._ui_thread:
                return 0
            if event == _REGISTER:
                owner = self.owners.get(parameter)
                if owner is None or not owner.valid() or handle in self.contexts:
                    return 0
                self.contexts[handle] = _Context(handle, owner)
                return 1
            context = self.contexts.get(handle)
            if context is None:
                return 0
            if event == _DESTROY:
                self._destroy(context)
                if text:
                    app_state.toast('MPay 独立浏览器无法继续，已取消本次网页登录。请重试。')
                return 1
            if not context.valid():
                return 0
            if event in (_CREATE, _NAVIGATE):
                url = (text or b'').decode('utf-8', 'strict')
                if len(url) > 65536:
                    return 0
                context.origins.add(_origin(url))
                context.url = url
                if event == _CREATE:
                    if context.session is not None:
                        return 0
                    context.size = (max(400, min(width, 1600)), max(400, min(height, 1200)))
                    self._start(context)
                elif context.session and not context.session.is_closing:
                    context.realms.clear()
                    context.session.navigate('main', url)
                else:
                    return 0
            elif event == _SCRIPT:
                script = (text or b'').decode('utf-8', 'strict')
                realm = context.dispatch_realm or context.realms.get('main')
                if not context.session or context.session.is_closing or not realm or len(script) > _MAX_MESSAGE:
                    return 0
                context.session.evaluate_in_realm(realm, script)
            elif event == _CLEAR:
                if context.session is None:
                    # The pinned SDK's ThirdPartyWebLoginForm clears data after
                    # Initialize/Register and BEFORE CreateWebviewAsChild. No
                    # renderer exists yet: its first page must get an entirely
                    # fresh profile, not merely a late cookie deletion.
                    context.fresh_profile = True
                elif context.session.is_closing:
                    return 0
                else:
                    context.session.clear_cookies()
            else:
                return 0
            return 1
        except Exception:
            # Never pass SDK payloads or Python exception strings into logs/UI.
            return 0

    def _start(self, context):
        if not context.valid():
            return
        context.startup_error = None
        context.realms.clear()
        game_key = hashlib.sha256(context.owner.game.encode('utf-8')).hexdigest()
        session = BrowserSession(
            dispatch=app_state.run_on_main_thread,
            on_event=lambda event, *args: self._event(context, session, event, *args),
            profile_path=str(Path.cwd() / 'mpay-browser' / game_key),
            persistent=not context.fresh_profile,
            scripts=(_SHIM,), size=context.size, bridge_messages=True)
        context.session = session
        session.start(context.url)

    def _event(self, context, session, event, *args):
        if not context.valid() or context.session is not session:
            return
        if event == 'warning':
            app_state.toast(args[0], 7000)
        elif event == 'document_invalidated':
            context.realms.pop(args[0], None)
        elif event == 'realm_destroyed':
            context.realms = {page: realm for page, realm in context.realms.items() if realm != args[0]}
        elif event in ('document_loaded', 'document_restored'):
            page, realm, url = args
            if not session.is_live_realm(realm):
                return
            try:
                trusted = _origin(url) in context.origins
            except ValueError:
                trusted = False
            if not trusted:
                return
            context.realms[page] = realm
            if event == 'document_loaded':
                self._invoke(context, realm, self.library.IDV_MpayBrowser_Loaded, context.handle)
            # A failed navigation may leave this exact old realm alive. It
            # already has SDK bridge JS; restore routing without running the
            # SDK load callback or page bootstrap twice.
        elif event == 'native_message':
            page, realm, url, request = args
            if not session.is_live_realm(realm):
                return
            try:
                if _origin(url) not in context.origins:
                    app_state.toast('平台网页在未经 SDK 指定的来源请求原生操作，已取消。请反馈此登录方式。', 8000)
                    self._close_holder(context)
                    self._destroy(context)
                    return
                if len(request) > _MAX_MESSAGE:
                    return
                name, payload = request.split(':', 1)
                if name != 'unisdk_js_native_call' or not isinstance(json.loads(payload), dict):
                    return
            except (ValueError, TypeError):
                return
            # Authoritative source realm from BiDi, not caller-supplied page ID.
            # SDK responses are restricted to this same realm, never a new page.
            self._invoke(context, realm, self.library.IDV_MpayBrowser_Message,
                         context.handle, name.encode('ascii'), payload.encode('utf-8'))
        elif event == 'page_closed':
            context.realms.pop(args[0], None)
        elif event == 'startup_failed':
            context.startup_error = args[0]
        elif event == 'error':
            app_state.toast('MPay 独立浏览器通信中断，已取消本次网页登录。')
        elif event == 'finished':
            context.session = None
            if context.startup_error:
                def dismiss():
                    dialog, context.dialog = context.dialog, None
                    if dialog:
                        dialog.deleteLater()
                def retry():
                    dismiss()
                    self._start(context)
                def cancel():
                    dismiss()
                    self._close_holder(context)
                dialog = BrowserSetupDialog(context.startup_error, on_retry=retry, on_cancel=cancel)
                context.dialog = dialog
                if context.valid():
                    dialog.show()
                else:
                    context.dialog = None
                    dialog.deleteLater()
            else:
                self._close_holder(context)

    def _invoke(self, context, realm, function, *args):
        previous = context.dispatch_realm
        context.dispatch_realm = realm
        try:
            if context.valid() and not function(*args) and context.valid():
                app_state.toast('MPay 浏览器回调失效，已取消本次网页登录。')
                self._close_holder(context)
                self._destroy(context)
        finally:
            context.dispatch_realm = previous

    def _close_holder(self, context):
        if context.valid() and not self.library.IDV_MpayBrowser_CloseHolder(context.handle):
            app_state.toast('MPay 登录窗口已失效，请重新打开平台登录。')
            self._destroy(context)

    def _destroy(self, context):
        # Revoke before closing browser/dialog: their late signals cannot call
        # into an SDK controller which has been destroyed or retired.
        context.revoked = True
        self.contexts.pop(context.handle, None)
        dialog, session = context.dialog, context.session
        context.dialog = context.session = None
        def cleanup():
            if dialog:
                dialog.reject()
            if session:
                session.finish()
        # Native Destroy may arrive from a non-UI thread. Revocation above is
        # synchronous; Qt object access and cleanup always use the Qt thread.
        app_state.run_on_main_thread(cleanup)

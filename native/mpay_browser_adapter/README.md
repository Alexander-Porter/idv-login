# MPay external-browser adapter

This source-built Windows x64 DLL replaces the **helper transport**, not MPay account protocols. It contains no browser engine, COM renderer, child renderer, WebView2/CEF, browser reparenting, or SDK byte patches. MPay provides its own JavaScript bridge and consumes its own login result. Python hosts the page in an independent Firefox process.

The 11 SDK exports match the observed caller in the pinned `assets/mpay.dll`, helper protocol version `2.0.0`. This is not a claim of a vendor-published stable ABI. Exact callsite evidence and unknowns are in [ABI.md](ABI.md).

## Build from source

Use an installed Microsoft C++ x64 Build Tools / Visual Studio toolchain and Windows PowerShell or PowerShell:

```powershell
./native/mpay_browser_adapter/build.ps1
```

The script uses the newest suitable installed toolchain, `/std:c++17 /O2 /MT /guard:cf /W4 /WX`, and verifies the output is x64 with exactly 11 SDK plus 5 host exports. It refuses known COM/browser-renderer or dynamically linked MSVC runtime imports. It does not download tools or accept an unknown prebuilt helper.

Generated outputs, not source files to hand-edit:
- `assets/webview_support_helper.dll`
- `src/mpay_browser_build.py`, containing `MPAY_BROWSER_HELPER_SHA256`
- Intermediate files in ignored `build/mpay_browser_adapter/`

A source checkout must build this helper before using MPay browser pages. Python must fail visibly when the generated manifest or matching DLL is absent. The helper must be hash-verified and preloaded by absolute install-owned path before SDK login. Keep the helper, MPay images, and host function pointer alive until process exit. A conflicting already-loaded DLL of the same basename must fail closed.

A successful build/export inspection is not a successful Windows SDK integration run or account login. The current Linux environment provided only `g++`: the implementation passed C++17 syntax/warning checking against a temporary WinAPI-declaration shim. MSVC compilation, PowerShell execution, native SDK lifecycle, and vendor-account acceptance remain separate validation steps. No unit tests were added.

## Host ABI version 1

All exports use the Windows x64 C ABI. All boolean results are `uint8_t` (use `ctypes.c_bool` or `c_uint8`), all handles and HWND/HMODULE payloads are pointer-width unsigned values. Header: [adapter.h](adapter.h).

```c
uint32_t IDV_MpayBrowser_ABIVersion(void); /* 1 */
uint8_t IDV_MpayBrowser_SetHost(IdvHostFn);
uint8_t IDV_MpayBrowser_Loaded(uintptr_t handle);
uint8_t IDV_MpayBrowser_Message(uintptr_t handle, const char *name, const char *json);
uint8_t IDV_MpayBrowser_CloseHolder(uintptr_t handle);

typedef int32_t (*IdvHostFn)(uintptr_t handle, int32_t event,
    const char *text, uintptr_t parameter, int32_t width, int32_t height);
```

`SetHost` permits first registration or the identical pointer again; replacement/unregistration is refused. Host must strongly retain its callback object. It must catch all exceptions, synchronously validate the handle/image/generation and copy input strings, enqueue asynchronous work to its application thread, and return nonzero only if that work was accepted. Do not call BiDi synchronously while servicing the native callback.

| Event | Value | text | parameter | width/height |
|---|---:|---|---|---|
| REGISTER | 1 | NULL | HMODULE owning SDK callback | 0/0 |
| CREATE | 2 | UTF-8 initial URL | SDK holder HWND | RECT dimensions |
| NAVIGATE | 3 | UTF-8 URL | 0 | 0/0 |
| SCRIPT | 4 | UTF-8 JavaScript | 0 | 0/0 |
| CLEAR | 5 | NULL | 0 | 0/0 |
| DESTROY | 6 | NULL normally; fixed error reason on failure | 0 | 0/0 |

REGISTER identifies the actual pinned MPay image via `GetModuleHandleExW(FROM_ADDRESS)` on the loading callback. Python must verify that HMODULE against the attached SDK image and the current login generation. The JS callback and all supplied non-null general callback pointers must belong to that same image; the single registered JS handler must be `unisdk_js_native_call`.

CREATE/NAVIGATE/SCRIPT/CLEAR rejection revokes the handle, emits DESTROY with a fixed non-sensitive reason, and posts WM_CLOSE to the owned SDK holder. REGISTER/ABI failures also revoke and emit the error. Python must present non-null DESTROY reasons as failures, not silently return to an empty login window. An asynchronous browser failure is reported by the host and closed via `CloseHolder` while the handle is still valid.

The host must restrict page/bridge origins, preserve page generation, copy all payloads, and never log URLs with auth queries, JSON bridge payloads, or cookies. Adapter strings are bounded to 4 MiB and checked as UTF-8; handler names are bounded to 64 bytes. Native input pointers are trusted ABI pointers, not arbitrary addresses from a web message. The host must not expose these native APIs directly to page code.

## Lifetime and callbacks

- Handles are monotonic opaque identifiers, not dereferenced addresses. They are never reused in the process. Invalid/destroyed handles are no-ops or return false.
- SDK Create/Initialize may be a no-page probe and must not open Firefox. Settings80 and callbacks32 are copied synchronously. Only CREATE reserves an active page slot. The actual third-party form sends CLEAR before CREATE: acknowledge it and use a fresh temporary profile for that context, without launching a browser merely to clear it. Contexts without CLEAR retain their dedicated persistent profile; see the precise call sequence in ABI.md.
- The SDK's callbacks use a module-global current controller. A new registration overlapping that image's active page invalidates **both** controllers before pending events can invoke either callback. Stale no-page controllers cannot later create a page. Merely rejecting a second CREATE while allowing the first page to call back would be unsafe.
- Loaded/Message must be invoked on the thread which created the native handle. Python should marshal these to the same native application event thread that invokes MPay. Wrong-thread reverse calls return false.
- Loaded calls the SDK's first callback with `false`; the SDK responds with SCRIPT containing its complete bridge. The host should install only its minimal `mwsInvoke` transport before page scripts, then call Loaded after document readiness and execute the supplied SDK SCRIPT in the main world. Do not copy SDK JavaScript implementation into this adapter.
- `mwsInvoke.request` is `unisdk_js_native_call:` followed by JSON. Split only the first colon, validate the registered name, then invoke Message on the owning thread. Pass the complete JSON unchanged, including nested `ngwebview_notify_native`. SDK handles onUserLogin/onVerify/closeWebView/openBrowser itself.
- No mutex is held during SDK or host callbacks. A lifetime lease makes synchronous callback-triggered Destroy safe. A destroy on another thread revokes first and waits for previously admitted SDK callbacks to return; same-thread reentrant destruction never waits on itself.
- Destroy synchronously removes callback access before telling the host to finish the external page. The host must discard all later events and must not call CloseHolder in response to ordinary SDK Destroy. User-closing an independent page instead invokes CloseHolder, which checks HWND process/thread ownership and queues WM_CLOSE to let the SDK perform its own cancellation.
- All API failures are represented by return value / fixed failure reason, not C++ exceptions escaping the ABI. Host callbacks must not throw or synchronously wait on the browser loop.

## Mandatory skin/integration rule

The verified skin ZIP has exactly two browser tags. Replace `layout/webview.xml`'s eager `WebBrowser` with a non-browser placeholder to remove the ActiveX fallback. Keep `layout/webview_cef.xml`'s `WebviewControl`: the fixed SDK dereferences its native placement wrapper without a null check. The wrapper forwards geometry to this helper but this helper creates no child renderer. Replacing that wrapper with generic Control would crash.

Keep the external-verification option if desired: third-party login independently lazy-loads this helper. Preload/validate the adapter before SDK login; no-page initialization probes must remain safe. If the adapter or browser fails, surface/cancel the attempt rather than restoring the original embedded fallback.

## Required acceptance before a complete-migration claim

1. MSVC x64 build and exact exports/import inspection.
2. Fixed SDK no-page probe, third-party page creation, main-world bridge injection and delivery.
3. User close, SDK close, navigation during callbacks, creation failure, and synchronous callback-triggered destruction.
4. A second controller in one MPay image, two distinct pinned MPay images, and old-generation late events.
5. Missing/rejected helper or host, and proof that no ActiveX/CEF/WebView2 renderer is instantiated.
6. Authorized/user-operated vendor login paths. Static evidence and synthetic browser behavior do not establish live-account success.

The adapter implementation is original project code under GPL-3.0-or-later. The vendor DLL and its redistribution terms remain separate from this adapter's source.

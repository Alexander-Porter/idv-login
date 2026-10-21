# MPay external-browser helper: pinned x64 ABI audit

Date: 2026-10-21. This document records static evidence for the companion adapter implementation. No Windows SDK execution, credentials, devices, or added tests were used to establish it. See README.md for build and verification status.

## Implementation contract

The companion adapter.cpp exports the observed SDK surface below plus five host entry points. The host ABI, event payloads, thread ownership, error contract, and build procedure are specified in README.md. No original SDK implementation is copied or patched. The adapter records opaque settings and callback pointers and forwards page operations to the Python host.

## Conclusion and evidence boundary

The current `mpay_option_web_verify_is_outer_browser_open = 1` is insufficient for a complete no-embedded-browser migration. Native login has a real optional/config-controlled third-party browser path with an ActiveX fallback. A replacement `webview_support_helper.dll` is a genuine DLL import boundary, not a binary patch or inline hook. The pinned caller supplies enough machine-level ABI evidence for a **Windows x64-only compatible adapter**, with opaque handling of unused fields. It is not evidence of a published or stable vendor ABI. The adapter must be tied to the exact SDK hash, have a fail-closed skin, and be exercised against that DLL on Windows before claiming native compatibility.

Inputs:
- `assets/mpay.dll` SHA-256 `02d27ad37b1421e4b97e90b889c4f8a59a71279dd08e090b6f8bb1821fb3225c`
- `assets/mpay_default_skin.zip` SHA-256 `b12333267bcc512bc2a74363c3e628a87f9f322797cca27806c07f94ac058c1d`
- PE preferred image base `0x180000000`. All VA below are preferred-image VAs, **not** addresses to modify. RVA = VA - image base.
- Repository `src/fever_bridge.py:398–401` calls the SDK's native `login(instance, 1, 0)`; `src/fever_skin.py:112–116,142–144` only changes QR layout and preserves all other skin entries.

## Actual main-reachable chain

1. `layout/login.xml:24` has `thirdparty_login_entries`; SDK setup at `0x1800804d0` populates entries from its configured set, loading `layout/third_party_login_item.xml` at `0x18008061c`. It is not unconditional on every launch, but is native login capability retained by main.
2. Login notification handler `0x180082f10` matches `third_party_wechat_login`, `third_party_qq_login`, `third_party_weibo_login`, `third_party_battle_net_login`. Their callsites `0x180083ad3`, `0x180083b7a`, `0x180083c21`, `0x180083cc8` enter `0x180087600`.
3. That registers a lambda via vtable `0x1804c82f8`; invocation `0x180090e40` -> `0x180089f90`. It builds `api/users/login/pc/oauth` via `0x1801368e0`, registers the next lambda vtable `0x1804c8330`; invocation `0x1800914a0` -> `0x18007add0`.
4. `0x18007add0` allocates `ThirdPartyWebLoginForm` (`0x1800baa40`, verified via RTTI vtable `0x1804cf940`), installs completion callback, creates/shows the native window. Its inherited `GetSkinFile`, vtable +0x58, is `0x1800d70b0`, returning `layout/webview.xml`.
5. Third-party InitWindow `0x1800bb260` tries helper through `0x1800bb290 -> 0x1800d5520 -> 0x1800d57f0`. Failure explicitly jumps to generic `0x1800d70c0`.
6. Generic fallback finds the skin control named `webview`, dynamic-casts to `CWebBrowserUI`, attaches event handling `0x1801a66f0`, and navigates via `0x1801a6060` -> COM vtable +0x1a0 (`IWebBrowser2::Navigate2`). Skin `layout/webview.xml:4` contains `WebBrowser ... delaycreate="false"`.
7. Helper success bypasses that fallback InitWindow and later opens `CWebViewWindow`: `0x1800bbb40 -> 0x1800d5620 -> 0x1800d6510`. Its skin is `layout/webview_cef.xml`, whose line 12 is `WebviewControl name="webview_content"`. This control is the native placement wrapper; the renderer is supplied by the helper.

Current assets do not bundle `webview_support_helper.dll`. Deleting/not distributing a helper does NOT mean no embedded browser: the explicit fallback is ActiveX.

## Exact delayed import boundary

PE data-directory 13 contains a delay-import descriptor for `webview_support_helper.dll`; its IAT entries are:

| IAT VA | Exact export name |
|---|---|
| 0x180684128 | MpayWebviewSupport_RegisterJsBridgeHandlers |
| 0x180684130 | MpayWebviewSupport_ExecuteJavaScript |
| 0x180684138 | MpayWebviewSupport_LoadUrl |
| 0x180684140 | MpayWebviewSupport_RegisterCallbacks |
| 0x180684148 | CheckMpayWebviewHelperSupportVersion |
| 0x180684150 | CreateMpayWebviewHelperSupport |
| 0x180684158 | MpayWebviewSupport_CreateWebviewAsChild |
| 0x180684160 | MpayWebviewSupport_Initialize |
| 0x180684168 | MpayWebviewSupport_Destroy |
| 0x180684170 | MpayWebviewSupport_ClearBrowserData |
| 0x180684178 | MpayWebviewSupport_Resize |

The load probe `0x180131120 -> 0x1801662f4` resolves all imports for that DLL, so ALL 11 exports must exist even if some are operational no-ops. Names are unmangled C exports. Do not implement only the functions observed on one happy path.

## Smallest x64-compatible function surface

The declarations below describe the **observed Win64 register/stack calling shape**, not recovered vendor headers. For aggregates >8 bytes, the caller passes a pointer to a temporary copy; a pointer-taking adapter is ABI-compatible for this pinned x64 caller even if vendor source declared by-value structs. No C++ `std::string` or allocator ownership crosses these exports.

```c
#include <stdint.h>
#include <stddef.h>
#include <windows.h>
typedef void *MpayHelper;
typedef void (*MpayJsBridgeFn)(const char *name_utf8, const char *json_utf8);

/* Export all names literally with extern "C" / a .def file. x64 only. */
uint8_t CheckMpayWebviewHelperSupportVersion(const char *version_ascii);
MpayHelper CreateMpayWebviewHelperSupport(void);
uint8_t MpayWebviewSupport_Initialize(MpayHelper, int32_t mode,
                                     const void *settings_80_bytes);
uint8_t MpayWebviewSupport_RegisterCallbacks(MpayHelper,
                                            const void *callbacks_32_bytes);
uint8_t MpayWebviewSupport_RegisterJsBridgeHandlers(MpayHelper,
    MpayJsBridgeFn callback, const char *const *names_utf8, uint64_t count);

/* Caller ignores these returns; void is adequate for this caller. */
void MpayWebviewSupport_CreateWebviewAsChild(MpayHelper, HWND parent,
    const RECT *rect_copy, const char *initial_url_utf8, uint8_t unknown_false);
void MpayWebviewSupport_LoadUrl(MpayHelper, const char *url_utf8);
void MpayWebviewSupport_ExecuteJavaScript(MpayHelper, const char *js_utf8);
void MpayWebviewSupport_Resize(MpayHelper, const RECT *rect_copy);
void MpayWebviewSupport_ClearBrowserData(MpayHelper);
void MpayWebviewSupport_Destroy(MpayHelper);
```

**Verified callsites / return use:**
- Version: `0x1800d58da–0x1800d58e9` RCX points to ASCII `2.0.0`; result tested in AL. Restrict compatibility response to that observed version rather than accepting arbitrary versions.
- Create: `0x1800d58fd–0x1800d591a`, no arguments established; returned RAX stored as handle. SDK owns an additional 8-byte wrapper allocated/freed in its own CRT, not the handle allocation. Adapter owns/frees its returned opaque handle.
- Initialize: `0x1800d5969–0x1800d59e6`: 80-byte temporary zero-filled; float at offset 24 is SDK scale / 100; RCX handle, EDX=2, R8 points at a copied 80-byte aggregate; AL tested. Other fields have unknown names and should remain opaque, not guessed.
- RegisterCallbacks: `0x1800d59ec–0x1800d5a3e`: 32-byte aggregate passed by temporary pointer RDX, AL tested. Offset0 is `0x1800d64f0`; offset8 is NULL; offset16 and24 are `0x180006f60`, a literal `ret 0`. Copy all 32 bytes synchronously. Only offset0 has necessary known semantics.
- RegisterJsBridgeHandlers: `0x1800d5a40–0x1800d5a70`: RCX handle; RDX callback `0x1800d60d0`; R8 vector of C-string pointers; R9 pointer-difference/8 (64-bit count); AL tested. Copy the names before return. Static constructor `0x1800036e0` initializes the single registered name `unisdk_js_native_call` (string VA `0x1804d4df0`).
- CreateWebviewAsChild: `0x1800d66fa–0x1800d673b`: RCX handle, RDX HWND from `0x180199020`, R8 temporary RECT (16 bytes), R9 initial narrow URL, 5th stack argument low byte zero. Return ignored. The HWND is the SDK browser-holder window, not the application's global HWND. Store it only for native lifecycle/cancel synchronization; DO NOT embed or reparent Firefox.
- LoadUrl: `0x1800d5698–0x1800d56b3`: RCX handle, RDX narrow URL, return ignored.
- ExecuteJavaScript: `0x1800d55a0–0x1800d55c2`: RCX handle, RDX narrow JS, return ignored.
- Resize: `0x1800d5302–0x1800d5323`: RCX handle, RDX copied 16-byte RECT, return ignored. External-browser implementation can ignore native placement changes.
- ClearBrowserData: `0x1800d54e0–0x1800d54f1`: RCX handle, return tail-jumped and not inspected by caller. Clear only adapter-owned isolated browser state, not the user's regular browser.
- Destroy: `0x1800d5474–0x1800d5482`, `0x1800d54a4–0x1800d54b2`, `0x1800d592e–0x1800d593c`: RCX handle, return ignored, SDK nulls wrapper value immediately afterward.
- URL narrow conversion `0x180162aa0` supplies code page `0xfde9 = 65001`, so URL/bridge transport is UTF-8.

### Clear before the first page is a real login path

The third-party login flow requires a successful no-page `ClearBrowserData`; it
is not merely a hypothetical helper operation or the global initialization
probe. In `0x18007add0`, native window creation at `0x18007b257` runs the form's
`InitWindow`. That initializes/registers its helper through
`0x1800bb290 -> 0x1800bb342 -> 0x1800d5520`, without opening a browser page.
After native layout, `0x18007b267` calls `0x1800bad40`, which forwards the helper
at form offset `0x988` to `0x1800d54e0` / `ClearBrowserData`. Only afterward does
`0x18007b274` invoke vtable slot `+0x38`. The verified third-party vtable at
`0x1804cf940` contains `0x1800bbb40` in that slot; its call at `0x1800bbba3`
enters `0x1800d5620`, which creates the holder and ultimately calls
`CreateWebviewAsChild` at `0x1800d673b`.

The host therefore acknowledges a pre-create CLEAR by marking this context for
a fresh temporary Firefox profile at CREATE. No browser is launched for CLEAR
alone. This starts that page with empty cookies, local storage and cache rather
than guessing that the vendor operation means only cookie deletion. Other
contexts that did **not** receive CLEAR retain their dedicated persistent
profile. This distinction matters: other callers of `0x1800d5620` include
verification-form paths at `0x1800d7e23` / `0x1800d7ea3` (source diagnostic
`form\\webview_verify_form.cpp`) and face-detection paths at `0x1800db36b` /
`0x1800db49b` (`impl\\face_detect_impl.cpp`). The third-party call order is not
evidence that every SDK browser context must discard cross-session state.

Within an already-created holder, `0x1800d5620` selects `LoadUrl` rather than
creating another page (`0x1800d5684–0x1800d56b3`), so its ordinary intra-flow
navigation continues in the same profile. The observed global no-page init
probe `0x18012d68f–0x18012d6df` initializes and destroys a helper but does not
perform this third-party CLEAR sequence.

## Browser-to-SDK callbacks, precise observed semantics

### Loading callback

Offset0 of the 32-byte callback aggregate is callable as `void callback(uint8_t is_loading)`. Function `0x1800d64f0` tests CL; when false it obtains global current controller and invokes `0x1800d5560`, which calls ExecuteJavaScript with the SDK's complete 2617-byte bridge script. Other parameters are not consumed. Do NOT claim field names/signatures for offset8/16/24; the current caller supplies NULL/no-op there.

For Firefox, install the low-level `window.mwsInvoke` shim at document start. After document completion, marshal loading(false) to the SDK's owning native UI thread. The resulting ExecuteJavaScript request executes the SDK-provided script in the page's main world. Preserve its ready event; do not synthesize different account fields or recreate its protocol. Beware document navigation during callback/JS execution; correlate page generation and discard old-realm work.

### JS request callback

`0x1800d60d0` accepts two C strings and forwards them to `0x1800d60f0`. First is logged as name; second is parsed as JSON. No response-function pointer, context parameter, string return, or C++ object is consumed. The SDK-provided script calls:

```javascript
window.mwsInvoke({
    request: 'unisdk_js_native_call:' + JSON.stringify(bridgeObjc),
    onSuccess: function (response) {},
    onFailure: function (error_code, error_message) {}
});
```

Split on the first `:` only. Validate against copied registered names. Marshal SDK callback(name, JSON) to the native UI thread; keep UTF-8 buffers alive through that synchronous invocation. SDK `0x1800d60f0` dispatches `openBrowser`, `ngwebview_notify_native`, `closeWebView` to its original handlers. Nested `ngwebview_notify_native` preserves `onUserLogin`, `onVerify`, `onRealnameVerify`, and `client_log` as supplied by SDK bridge. Do not intercept and fabricate login success. Completion remains SDK login callback -> GetUserTicket -> existing Fever IPC.

The SDK bridge constructors define `NeteaseMpayJSBridge.Common`, `window.UniSDKJSBridge`, and dispatch `NeteaseMpayJSBridgeReady`. The script is static data at VA `0x1804d43b0`, length 0xa39 (2617); static constructor `0x180003750` copies it into SDK state. Prefer accepting ExecuteJavaScript from SDK over copying this script into application code.

### Lifetime/thread restrictions (known and inferred)

- Important known constraint: `0x1800d5546` assigns a module-global `g_current_controller` at VA `0x180689370`. Both loading and bridge trampolines consult that global, not a callback user-data or handle. Thus only one active browser controller per SDK image is supported by this callback design. Reject/queue overlapping browser sessions for that image; multiple pinned MPay images must retain distinct callback pointers/host generation associations.
- SDK initialization can create/initialize/register/destroy a helper WITHOUT creating a page (`0x18012d68f–0x18012d6df`). Create/Initialize must not automatically open a page. Destroy must also work before CreateWebviewAsChild.
- Copy settings, callbacks, names, URL and JS before returning: several point into stack temporaries or short-lived SDK strings.
- Destroy must synchronously revoke native callbacks for that handle and discard future asynchronous browser events; callback trampolines otherwise refer to potentially freed SDK controller memory. Do not call back while destroying.
- The original helper's callback thread policy is not published in the available files. UI handlers consume these callbacks directly; therefore routing callbacks through the same native event thread which calls MPay is the safe implementation constraint, not a claim about the original helper implementation.
- Web `closeWebView` closes SDK holder via `0x1800d5ae0`; SDK holder close propagates through `0x1800d55e0` to controller delegate and third-party completion. For user-closing the independent browser, enqueue WM_CLOSE to the *owned* holder HWND from CreateWebviewAsChild, after validating it still belongs to that generation. Verify this cancellation path on Windows; do not assume the unused callback slots are close callbacks.
- Re-entrancy: callbacks may synchronously cause SDK window destruction and helper Destroy. Keep adapter object/event references safe for the duration; never hold a global/native lock while invoking SDK or Python callbacks.

## Loading path and integrity

`0x1800d57f0` calls the import-load probe with plain `webview_support_helper.dll`; delayed loader `0x1801664b6–0x1801664bf` calls imported `LoadLibraryExA` (IAT `0x1804ab478`) with RDX=0, R8D=0. This is ordinary basename DLL search, not guaranteed adjacent-to-SDK search. Existing Fever MPay image is deliberately copied to a per-generation shadow path (`src/fever_bridge.py:417–440`).

Host should verify its adapter artifact, preload it by absolute install-owned path before calling MPay, keep the loader handle pinned, register its host bridge first, and verify the actual module path if a module of the same basename was already loaded. Fail closed on a foreign/conflicting module. Do not depend on writable CWD or PATH. This can be normal documented DLL loading, with no import-table patching or machine-code rewriting.

## Outer option and skin requirements

- `SetOption` dereferences int32*, confirmed write at `0x18012f967` to `0x1806841f8`.
- Initialization checks that value at `0x18012d687`; value1 skips the early helper probe. `0x180150dab–0x180150dca` also places `is_outer_browser_open` in HTTP parameters.
- Third-party InitWindow independently lazy-loads the helper and does not check this flag. Therefore keeping outer verification=1 is compatible with the adapter and preserves external-verification behavior; the adapter still must be preloaded/validated by the host before SDK login. Setting0 is not required merely to make third-party helper load. If choosing0, the no-page init probe lifecycle described above becomes mandatory and server verification behavior changes.
- Full scan of every XML entry in the pinned skin ZIP found exactly two browser tags: `layout/webview.xml:4` WebBrowser and `layout/webview_cef.xml:12` WebviewControl; no other instances.
- `layout/webview.xml:4` has eager ActiveX `WebBrowser delaycreate=false`. Replace/remove that tag in the prepared skin. Changing only InitWindow behavior is insufficient because skin construction can eagerly instantiate it. With working helper, the third-party/verify InitWindow success branch never needs that control. With failed helper, fallback dynamic_cast sees no CWebBrowserUI and cannot create a renderer. A harmless generic Control placeholder under the same name is suitable if layout geometry needs retaining.
- Preserve `layout/webview_cef.xml`'s native `WebviewControl` wrapper: `0x1800d66d7–0x1800d66f7` dynamically casts and dereferences it without a null guard. Replacing that element with generic Control would crash. The wrapper itself only forwards handle/RECT to helper; the replacement helper must not create any renderer or embed Firefox.
- Other direct generic WebviewForm callers exist, including unused OpenTargetUrl-style APIs. Do not promise that removing an ActiveX control fully migrates every exported SDK API. Main's native login / server verification / third-party forms are the target, and the adapter must cover every main-reachable browser call. Audit any future new SDK API before enabling it.
- Fail-closed means loader/ABI/host-runtime failure visibly fails/cancels the login, not invisible blank native windows, ignored callbacks, or re-enabling ActiveX. Preflight alone is insufficient for mid-session failures; propagate them through the owned holder lifecycle.

## Privacy and logging

Default privacy/service hyperlinks already go through `SafeOpenUrl` -> ShellExecuteW (helper `0x1801622f0`, callsite in `0x1800893a6` path). The separate `mpay_option_open_privacy_service_in_protocol=1` changes to ApiCallBack slot27 (`0x18012128b`, vtable+0xd8, args0 + empty string); it is not an external-browser bridge and current host ignores it. Leave that option at default unless implementing its actual contract.

SDK JS callback `0x1800d60f0` logs entire bridge JSON (`onJsBridgeCall, name:%s, param:%s`). The original `src/fever_bridge.py:38–40` regex fails for JSON quoted keys such as `"token":` because it expects colon immediately after the key; original lines768–769 can therefore write raw account payload. The migration drops raw SDK hook messages instead. Neither adapter IPC nor BiDi logs should contain auth URL queries, cookies, bridge JSON, user objects, or script message bodies.

Native logging requires separate controls, established from the pinned DLL:

- `mpay_option_vlog_writefile` is the string at `0x1804e3350`. Its SetOption branch reads **one byte through the supplied pointer** (`0x18012f494`) and stores it at `0x1806841b9` (`0x18012f497`). Pass an address of `uint8_t(0)` / `ctypes.c_bool(False)`, not a null value pointer.
- This flag is **not** a complete file-logging disable switch. With a non-null hook, `0x180169154` invokes it, then `0x180169157–177` still forwards severity <=8 to the native writer when the flag is false. If initialization's configured level is >=14, `0x18011c942–952` also forces the verbose-file flag on.
- `mpay_option_plog_level` is the string at `0x1804e3338`. Its branch reads **int32 through a pointer** (`0x18012f472`) and stores it at `0x180652004` (`0x18012f474`). Set it to **0 before init**, retaining the non-null discard hook and writefile=false. A negative value is unsuitable: initialization resets it to default8 at `0x18011c937–940`.
- The dispatcher `0x180168d7b`, hook path `0x18016909e`, and native writer `0x1801693ea` all reject a message whose severity is greater than the configured level. The bridge-payload call explicitly uses level14 (`0x1800d614c`). Observed direct constant logger callsites use6/8/14/16, not0. This establishes suppression of the audited SDK log paths; it does not assert absence of arbitrary future SDK diagnostics or OS crash dumps.

## OAuth navigation trust boundary

`0x1801368e0` constructs the initial third-party page URL locally; it is not an HTTP response parser returning the provider's URL. It combines the current SDK service base (`0x180136cd2 -> 0x18001f720`) with `api/users/login/pc/oauth` (`0x18013693d`) and parameters including `device_id`, `login_type`, and `opt_fields`. The production base literal is `https://service.mkey.163.com/mpay/` at `0x1804ac970`; test environments have different service-map entries. No client-side `redirect_uri` construction was found in this path. Provider redirects and the final return document are controlled by the server.

Allowing cross-origin HTTP(S) navigation does not imply granting native bridge access to every redirect destination. Keep bridge authority scoped to SDK-supplied initial/LoadUrl origins and owned browsing-context descendants; do not promote arbitrary HTTP Location targets or user-created tabs. Returning to the original MPay origin remains supported. A necessary bridge call from a different origin must produce a visible, safe failure pending an authoritative contract, not silently hang or expand privileges. Static caller evidence alone cannot establish every server-dependent return origin.

## What is and is not established

Established statically: exact import names, consumed arguments/registers, opaque object ownership boundary, struct sizes/layout actually supplied, consumed bool returns, JS request format, required injection callback, real ActiveX fallback, fixed SDK dependency and ordinary loader behavior.

Not established by a stripped caller alone: vendor source-level typedefs for ignored returns/opaque fields, original helper's thread policy, all server-dependent login configurations and verification variants, Windows cancellation/focus/message-pump behavior of the new adapter, or end-to-end vendor authentication success. These are explicit validation requirements, not reasons to omit the known ActiveX path.

Evidence sufficient to continue implementation: this pinned x64 ABI plus a source-controlled adapter and a synthetic Windows host that loads the fixed DLL and exercises helper initialization, page/JS callbacks, close/cancel, navigation generation, two game-image generations, helper absence/failure, and no ActiveX/CEF/WebView2 renderer creation. Public vendor headers or a redistributable official helper SDK would remove source-level ABI uncertainty and improve forward-version support. Account-dependent acceptance is a later authorized/user-operated validation, not something this audit performed.

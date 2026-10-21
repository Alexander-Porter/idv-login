// SPDX-License-Identifier: GPL-3.0-or-later
// Pinned MPay 2.0.0 helper ABI, Windows x64 only. See ABI.md.
#pragma once
#include <stdint.h>
#include <windows.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef void *MpayHelper;
typedef void (__cdecl *MpayJsBridgeFn)(const char *name, const char *json);
typedef int32_t (__cdecl *IdvHostFn)(uintptr_t handle, int32_t event,
    const char *text, uintptr_t parameter, int32_t width, int32_t height);

enum IdvMpayBrowserEvent {
    IDV_MPAY_REGISTER = 1, IDV_MPAY_CREATE = 2, IDV_MPAY_NAVIGATE = 3,
    IDV_MPAY_SCRIPT = 4, IDV_MPAY_CLEAR = 5, IDV_MPAY_DESTROY = 6
};

uint8_t __cdecl CheckMpayWebviewHelperSupportVersion(const char *version);
MpayHelper __cdecl CreateMpayWebviewHelperSupport(void);
uint8_t __cdecl MpayWebviewSupport_Initialize(MpayHelper, int32_t mode, const void *settings80);
uint8_t __cdecl MpayWebviewSupport_RegisterCallbacks(MpayHelper, const void *callbacks32);
uint8_t __cdecl MpayWebviewSupport_RegisterJsBridgeHandlers(MpayHelper,
    MpayJsBridgeFn callback, const char *const *names, uint64_t count);
void __cdecl MpayWebviewSupport_CreateWebviewAsChild(MpayHelper, HWND parent,
    const RECT *rect, const char *url, uint8_t unknown_false);
void __cdecl MpayWebviewSupport_LoadUrl(MpayHelper, const char *url);
void __cdecl MpayWebviewSupport_ExecuteJavaScript(MpayHelper, const char *script);
void __cdecl MpayWebviewSupport_Resize(MpayHelper, const RECT *rect);
void __cdecl MpayWebviewSupport_ClearBrowserData(MpayHelper);
void __cdecl MpayWebviewSupport_Destroy(MpayHelper);

uint32_t __cdecl IDV_MpayBrowser_ABIVersion(void);
uint8_t __cdecl IDV_MpayBrowser_SetHost(IdvHostFn);
uint8_t __cdecl IDV_MpayBrowser_Loaded(uintptr_t handle);
uint8_t __cdecl IDV_MpayBrowser_Message(uintptr_t handle, const char *name, const char *json);
uint8_t __cdecl IDV_MpayBrowser_CloseHolder(uintptr_t handle);

#ifdef __cplusplus
}
#endif

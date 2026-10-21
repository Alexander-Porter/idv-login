// SPDX-License-Identifier: GPL-3.0-or-later
// An import-compatible transport adapter, not an embedded browser implementation.
#include "adapter.h"
#include <array>
#include <atomic>
#include <condition_variable>
#include <cstring>
#include <limits>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>

static_assert(sizeof(void *) == 8, "The audited MPay ABI is Windows x64 only");
static_assert(sizeof(RECT) == 16, "Unexpected Windows RECT layout");
static_assert(sizeof(MpayJsBridgeFn) == 8, "Unexpected function pointer layout");

namespace {
using LoadingFn = void (__cdecl *)(uint8_t);
constexpr size_t kTextLimit = 4 * 1024 * 1024;
constexpr char kHandler[] = "unisdk_js_native_call";

struct Session {
    uintptr_t id = 0;
    DWORD thread = 0;
    HMODULE image = nullptr;
    HWND holder = nullptr;
    std::array<unsigned char, 80> settings{};
    std::array<uintptr_t, 4> callbacks{};
    MpayJsBridgeFn bridge = nullptr;
    bool active = true;
    bool initialized = false;
    bool registered = false;
    bool page = false;
    unsigned in_callback = 0;
};

std::mutex g_mutex;
std::condition_variable g_callbacks_done;
std::unordered_map<uintptr_t, std::shared_ptr<Session>> g_sessions;
std::unordered_map<HMODULE, uintptr_t> g_pages;
std::unordered_map<HMODULE, uintptr_t> g_controller;
std::atomic<IdvHostFn> g_host{nullptr};
uintptr_t g_next_id = 1; // Opaque monotonic IDs, never heap addresses or reusable IDs.

uintptr_t key(MpayHelper handle) { return reinterpret_cast<uintptr_t>(handle); }
HMODULE module_of(uintptr_t address) {
    HMODULE module = nullptr;
    if (!address || !GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
            GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
            reinterpret_cast<LPCWSTR>(address), &module)) return nullptr;
    return module;
}
bool owned_window(HWND hwnd, DWORD thread) {
    DWORD process = 0;
    return hwnd && IsWindow(hwnd) && GetWindowThreadProcessId(hwnd, &process) == thread &&
        process == GetCurrentProcessId();
}
bool copy_text(const char *text, std::string &out, size_t limit = kTextLimit) {
    if (!text) return false;
    size_t size = 0;
    while (size <= limit && text[size]) ++size;
    if (size > limit) return false;
    if (size && !MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text,
                                    static_cast<int>(size), nullptr, 0)) return false;
    out.assign(text, size);
    return true;
}
std::shared_ptr<Session> lookup(uintptr_t id, bool owning_thread = true) {
    std::lock_guard<std::mutex> lock(g_mutex);
    auto it = g_sessions.find(id);
    if (it == g_sessions.end() || !it->second->active ||
        (owning_thread && it->second->thread != GetCurrentThreadId())) return {};
    return it->second;
}
bool notify(const std::shared_ptr<Session> &session, int32_t event,
            const char *text = nullptr, uintptr_t parameter = 0,
            int32_t width = 0, int32_t height = 0) {
    auto host = g_host.load();
    if (!host) return false;
    try { return host(session->id, event, text, parameter, width, height) != 0; }
    catch (...) { return false; } // No C++ exception crosses either ABI boundary.
}
void retire(uintptr_t id, const char *reason = nullptr, bool close_holder = false) {
    std::shared_ptr<Session> session;
    HWND holder = nullptr;
    DWORD thread = 0;
    {
        std::unique_lock<std::mutex> lock(g_mutex);
        auto it = g_sessions.find(id);
        if (it == g_sessions.end()) return;
        session = it->second;
        session->active = false;
        holder = session->holder;
        thread = session->thread;
        session->holder = nullptr;
        session->callbacks.fill(0);
        session->bridge = nullptr;
        auto page = g_pages.find(session->image);
        if (page != g_pages.end() && page->second == id) g_pages.erase(page);
        auto controller = g_controller.find(session->image);
        if (controller != g_controller.end() && controller->second == id) g_controller.erase(controller);
        g_sessions.erase(it); // Revoke before any host or SDK callback.
        // A concurrent destroy waits for an already admitted SDK callback. A
        // callback's own reentrant Destroy must not wait on itself.
        if (GetCurrentThreadId() != thread)
            g_callbacks_done.wait(lock, [&] { return session->in_callback == 0; });
    }
    notify(session, IDV_MPAY_DESTROY, reason);
    if (close_holder && owned_window(holder, thread)) PostMessageW(holder, WM_CLOSE, 0, 0);
}
void fail(uintptr_t id, const char *reason) noexcept {
    try { retire(id, reason, true); } catch (...) {}
}

// Admission and revocation are serialized, but SDK callbacks NEVER run locked.
// A shared_ptr keeps our own record alive if the callback synchronously destroys it.
struct CallbackLease {
    std::shared_ptr<Session> session;
    explicit CallbackLease(std::shared_ptr<Session> s) : session(std::move(s)) {}
    ~CallbackLease() {
        if (!session) return;
        std::lock_guard<std::mutex> lock(g_mutex);
        --session->in_callback;
        g_callbacks_done.notify_all();
    }
};

void command(MpayHelper handle, int32_t event, const char *text) {
    const auto id = key(handle);
    try {
        auto session = lookup(id);
        if (!session) return;
        std::string copied;
        if (text && !copy_text(text, copied)) { fail(id, "invalid_utf8_or_oversize_text"); return; }
        {
            std::lock_guard<std::mutex> lock(g_mutex);
            if (!session->active) return;
            if (!session->registered || !session->bridge ||
                (event != IDV_MPAY_CLEAR && !session->page) ||
                !g_controller.count(session->image) || g_controller.at(session->image) != id) {
                // No callback or renderer fallback while initialization is incomplete.
                session.reset();
            }
        }
        if (!session) { fail(id, "browser_not_ready"); return; }
        if (!notify(session, event, text ? copied.c_str() : nullptr)) fail(id, "host_command_failed");
    } catch (...) { fail(id, "adapter_command_failed"); }
}
} // namespace

extern "C" uint32_t __cdecl IDV_MpayBrowser_ABIVersion(void) { return 1; }
extern "C" uint8_t __cdecl IDV_MpayBrowser_SetHost(IdvHostFn host) {
    if (!host) return 0;
    IdvHostFn expected = nullptr;
    return g_host.compare_exchange_strong(expected, host) || expected == host;
}
extern "C" uint8_t __cdecl CheckMpayWebviewHelperSupportVersion(const char *version) {
    // The fixed SDK passes this literal. No claim of forward-version support.
    return version && std::strcmp(version, "2.0.0") == 0 && g_host.load();
}
extern "C" MpayHelper __cdecl CreateMpayWebviewHelperSupport(void) {
    try {
        if (!g_host.load()) return nullptr;
        auto session = std::make_shared<Session>();
        session->thread = GetCurrentThreadId();
        std::lock_guard<std::mutex> lock(g_mutex);
        if (g_next_id == (std::numeric_limits<uintptr_t>::max)()) return nullptr;
        session->id = g_next_id++;
        g_sessions.emplace(session->id, session);
        return reinterpret_cast<MpayHelper>(session->id);
    } catch (...) { return nullptr; }
}
extern "C" uint8_t __cdecl MpayWebviewSupport_Initialize(
        MpayHelper handle, int32_t mode, const void *settings) {
    try {
        auto session = lookup(key(handle));
        if (!session) return 0;
        if (mode != 2 || !settings) { fail(session->id, "unsupported_sdk_settings"); return 0; }
        std::lock_guard<std::mutex> lock(g_mutex);
        if (!session->active || session->initialized) return 0;
        std::memcpy(session->settings.data(), settings, session->settings.size());
        session->initialized = true;
        return 1;
    } catch (...) { fail(key(handle), "adapter_initialize_failed"); return 0; }
}
extern "C" uint8_t __cdecl MpayWebviewSupport_RegisterCallbacks(MpayHelper handle, const void *raw) {
    const auto id = key(handle);
    try {
        auto session = lookup(id);
        if (!session) return 0;
        if (!raw) { fail(id, "missing_sdk_callbacks"); return 0; }
        std::array<uintptr_t, 4> callbacks{};
        std::memcpy(callbacks.data(), raw, sizeof(callbacks));
        const auto image = module_of(callbacks[0]);
        if (!image || callbacks[1] || !callbacks[2] || !callbacks[3] ||
            module_of(callbacks[2]) != image || module_of(callbacks[3]) != image) {
            fail(id, "unsupported_sdk_callbacks"); return 0;
        }
        uintptr_t conflicting_page = 0;
        {
            std::lock_guard<std::mutex> lock(g_mutex);
            if (!session->active || !session->initialized || session->registered) return 0;
            session->image = image;
            session->callbacks = callbacks;
            session->registered = true;
            auto old = g_pages.find(image);
            if (old != g_pages.end() && old->second != id) conflicting_page = old->second;
            // SDK sets a module-global controller even if initialization fails.
            // Changing this gate first prevents an old page's pending callback
            // from ever reaching the newly registered controller.
            g_controller[image] = id;
        }
        if (conflicting_page) {
            fail(conflicting_page, "sdk_image_controller_overlap");
            fail(id, "sdk_image_controller_overlap");
            return 0;
        }
        if (!notify(session, IDV_MPAY_REGISTER, nullptr, reinterpret_cast<uintptr_t>(image))) {
            fail(id, "host_rejected_sdk_image"); return 0;
        }
        std::lock_guard<std::mutex> lock(g_mutex);
        return session->active ? 1 : 0;
    } catch (...) { fail(id, "adapter_register_failed"); return 0; }
}
extern "C" uint8_t __cdecl MpayWebviewSupport_RegisterJsBridgeHandlers(
        MpayHelper handle, MpayJsBridgeFn callback, const char *const *names, uint64_t count) {
    const auto id = key(handle);
    try {
        auto session = lookup(id);
        if (!session) return 0;
        std::string name;
        if (!callback || count != 1 || !names || !copy_text(names[0], name, 64) || name != kHandler) {
            fail(id, "unsupported_sdk_bridge"); return 0;
        }
        const auto image = module_of(reinterpret_cast<uintptr_t>(callback));
        bool valid = false;
        {
            std::lock_guard<std::mutex> lock(g_mutex);
            valid = session->active && session->registered && !session->bridge && image == session->image;
            if (valid) session->bridge = callback;
        }
        if (!valid) fail(id, "sdk_bridge_image_mismatch");
        return valid ? 1 : 0;
    } catch (...) { fail(id, "adapter_bridge_register_failed"); return 0; }
}
extern "C" void __cdecl MpayWebviewSupport_CreateWebviewAsChild(
        MpayHelper handle, HWND parent, const RECT *rect, const char *url, uint8_t unknown_false) {
    const auto id = key(handle);
    try {
        auto session = lookup(id);
        if (!session) return;
        std::string copied;
        if (!rect || unknown_false || !owned_window(parent, session->thread) || !copy_text(url, copied)) {
            fail(id, "invalid_browser_creation"); return;
        }
        const int64_t width = static_cast<int64_t>(rect->right) - rect->left;
        const int64_t height = static_cast<int64_t>(rect->bottom) - rect->top;
        if (width < 0 || height < 0 || width > INT32_MAX || height > INT32_MAX) {
            fail(id, "invalid_browser_bounds"); return;
        }
        bool ready = false;
        {
            std::lock_guard<std::mutex> lock(g_mutex);
            if (!session->active) return;
            session->holder = parent;
            ready = session->registered && session->bridge && !session->page &&
                g_controller.count(session->image) && g_controller.at(session->image) == id &&
                !g_pages.count(session->image);
            if (ready) {
                g_pages.emplace(session->image, id);
                session->page = true;
            }
        }
        if (!ready) { fail(id, "sdk_image_page_already_active_or_not_ready"); return; }
        if (!notify(session, IDV_MPAY_CREATE, copied.c_str(), reinterpret_cast<uintptr_t>(parent),
                    static_cast<int32_t>(width), static_cast<int32_t>(height)))
            fail(id, "host_create_failed");
    } catch (...) { fail(id, "adapter_create_failed"); }
}
extern "C" void __cdecl MpayWebviewSupport_LoadUrl(MpayHelper handle, const char *url) {
    if (!url) { fail(key(handle), "missing_browser_url"); return; }
    command(handle, IDV_MPAY_NAVIGATE, url);
}
extern "C" void __cdecl MpayWebviewSupport_ExecuteJavaScript(MpayHelper handle, const char *script) {
    if (!script) { fail(key(handle), "missing_browser_script"); return; }
    command(handle, IDV_MPAY_SCRIPT, script);
}
extern "C" void __cdecl MpayWebviewSupport_Resize(MpayHelper, const RECT *) {
    // No child renderer. Native holder geometry must not resize/reparent Firefox.
}
extern "C" void __cdecl MpayWebviewSupport_ClearBrowserData(MpayHelper handle) {
    command(handle, IDV_MPAY_CLEAR, nullptr);
}
extern "C" void __cdecl MpayWebviewSupport_Destroy(MpayHelper handle) {
    try { retire(key(handle)); } catch (...) {} // Never throw across vendor C ABI.
}
extern "C" uint8_t __cdecl IDV_MpayBrowser_Loaded(uintptr_t id) {
    try {
        std::shared_ptr<Session> session;
        LoadingFn callback = nullptr;
        {
            std::lock_guard<std::mutex> lock(g_mutex);
            auto it = g_sessions.find(id);
            if (it == g_sessions.end()) return 0;
            session = it->second;
            if (!session->active || !session->page || session->thread != GetCurrentThreadId() ||
                !session->callbacks[0] || !g_controller.count(session->image) ||
                g_controller.at(session->image) != id) return 0;
            callback = reinterpret_cast<LoadingFn>(session->callbacks[0]);
            ++session->in_callback;
        }
        CallbackLease lease(session);
        callback(0);
        return 1;
    } catch (...) { fail(id, "sdk_loaded_callback_failed"); return 0; }
}
extern "C" uint8_t __cdecl IDV_MpayBrowser_Message(uintptr_t id, const char *name, const char *json) {
    try {
        std::string copied_name, copied_json;
        if (!copy_text(name, copied_name, 64) || copied_name != kHandler ||
            !copy_text(json, copied_json)) return 0;
        std::shared_ptr<Session> session;
        MpayJsBridgeFn callback = nullptr;
        {
            std::lock_guard<std::mutex> lock(g_mutex);
            auto it = g_sessions.find(id);
            if (it == g_sessions.end()) return 0;
            session = it->second;
            if (!session->active || !session->page || session->thread != GetCurrentThreadId() ||
                !session->bridge || !g_controller.count(session->image) ||
                g_controller.at(session->image) != id) return 0;
            callback = session->bridge;
            ++session->in_callback;
        }
        CallbackLease lease(session);
        callback(copied_name.c_str(), copied_json.c_str());
        return 1;
    } catch (...) { fail(id, "sdk_message_callback_failed"); return 0; }
}
extern "C" uint8_t __cdecl IDV_MpayBrowser_CloseHolder(uintptr_t id) {
    try {
        auto session = lookup(id);
        if (!session) return 0;
        HWND holder = nullptr;
        {
            std::lock_guard<std::mutex> lock(g_mutex);
            if (!session->active || !session->page) return 0;
            holder = session->holder;
        }
        return owned_window(holder, session->thread) && PostMessageW(holder, WM_CLOSE, 0, 0);
    } catch (...) { return 0; }
}

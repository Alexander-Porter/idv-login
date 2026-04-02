# coding=UTF-8
"""跨平台代理环境管理。

统一入口：set_proxy(port) / unset_proxy()
- Windows : 在 HKCU\\Environment 设置 HTTP_PROXY 等并广播 WM_SETTINGCHANGE
- macOS   : 通过 networksetup 设置系统级 HTTP/HTTPS 代理
- Linux   : 通过 gsettings 设置 GNOME 系统代理（Crossover/Wine 会读取 GNOME 代理配置）
"""

import ctypes
import os
import subprocess
import sys

from envmgr import genv

_logger = None

def _get_logger():
    global _logger
    if _logger is None:
        from logutil import setup_logger
        _logger = setup_logger()
    return _logger

_PROXY_ENV_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
# Windows 注册表值名不区分大小写，只需处理大写即可
_PROXY_ENV_VARS_WIN = ("HTTP_PROXY", "HTTPS_PROXY")
_NO_PROXY_ENV_VARS = ("NO_PROXY", "no_proxy")
_NO_PROXY_ENV_VARS_WIN = ("NO_PROXY",)


# ==================================================================
#  统一入口
# ==================================================================

def set_proxy(port: int):
    """根据当前平台设置系统/用户级代理。"""
    # 从云端获取 NO_PROXY 域名列表
    no_proxy_domains = _get_no_proxy_domains()
    if sys.platform == "win32":
        _set_win(port, no_proxy_domains)
    elif sys.platform == "darwin":
        _set_darwin(port)
    else:
        _set_linux(port)


def _get_no_proxy_domains():
    """从 CloudRes 获取 NO_PROXY 域名列表。"""
    try:
        from cloudRes import CloudRes
        cloudres = CloudRes()
        return cloudres.get_no_proxy_domains()
    except Exception as e:
        _get_logger().warning(f"获取 NO_PROXY 域名列表失败: {e}")
        return []


def unset_proxy():
    """根据当前平台恢复/清除代理设置。"""
    if sys.platform == "win32":
        _unset_win()
    elif sys.platform == "darwin":
        _unset_darwin()
    else:
        _unset_linux()


# ==================================================================
#  Windows — 用户级环境变量
# ==================================================================

def _set_win(port: int, no_proxy_domains: list = None):
    import winreg
    proxy_url = f"http://127.0.0.1:{port}"
    saved: dict = {}
    # 构建 NO_PROXY 值
    no_proxy_value = ",".join(no_proxy_domains) if no_proxy_domains else ""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS
        ) as key:
            # 保存并设置代理环境变量
            for var in _PROXY_ENV_VARS_WIN:
                try:
                    old_val, _ = winreg.QueryValueEx(key, var)
                    saved[var] = old_val
                except FileNotFoundError:
                    saved[var] = None
                winreg.SetValueEx(key, var, 0, winreg.REG_SZ, proxy_url)
            # 保存并设置 NO_PROXY 环境变量
            if no_proxy_value:
                for var in _NO_PROXY_ENV_VARS_WIN:
                    try:
                        old_val, _ = winreg.QueryValueEx(key, var)
                        saved[var] = old_val
                    except FileNotFoundError:
                        saved[var] = None
                    winreg.SetValueEx(key, var, 0, winreg.REG_SZ, no_proxy_value)
    except Exception as e:
        _get_logger().error(f"设置用户代理环境变量失败: {e}")
        return

    _broadcast_env_change()
    # 注册表代理仅供外部进程（如游戏）使用。
    # WM_SETTINGCHANGE 可能导致当前进程的环境块 (PEB) 被更新，
    # 必须立即清理，否则 QtWebEngine Chromium 子进程会继承代理设置。
    for var in _PROXY_ENV_VARS:
        os.environ.pop(var, None)
    for var in _NO_PROXY_ENV_VARS:
        os.environ.pop(var, None)
    genv.set("_SAVED_PROXY_ENV", saved)
    genv.set("_LAST_PROXY_PORT", port, True)  # 持久化记录使用的代理端口
    _get_logger().info(f"已设置用户代理环境变量: {proxy_url}")


def _unset_win():
    saved = genv.get("_SAVED_PROXY_ENV")
    if not saved:
        return
    import winreg
    from mitm_proxy import DEFAULT_PROXY_PORT

    # 判断是否应该直接清除而非恢复：
    # 如果保存的旧值指向本工具自身的代理端口（上次端口或默认端口），
    # 说明旧值是上次工具崩溃残留的，恢复它没有意义，直接清除。
    last_port = genv.get("_LAST_PROXY_PORT")
    should_clear = False
    for var, old_val in saved.items():
        if old_val is not None:
            for port in (last_port, DEFAULT_PROXY_PORT):
                if port and f":{port}" in old_val:
                    should_clear = True
                    break
        if should_clear:
            break

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS
        ) as key:
            for var, old_val in saved.items():
                if should_clear or old_val is None:
                    try:
                        winreg.DeleteValue(key, var)
                    except FileNotFoundError:
                        pass
                else:
                    winreg.SetValueEx(key, var, 0, winreg.REG_SZ, old_val)
    except Exception as e:
        _get_logger().error(f"恢复用户代理环境变量失败: {e}")
        return
    # 注册表已修改完成，广播通知可以异步进行——不阻塞退出流程
    import threading
    threading.Thread(target=_broadcast_env_change, daemon=True).start()
    genv.set("_SAVED_PROXY_ENV", None)
    if should_clear:
        _get_logger().info("检测到残留代理（本工具端口），已直接清除用户代理环境变量")
    else:
        _get_logger().info("已恢复用户代理环境变量")


def _broadcast_env_change():
    """广播 WM_SETTINGCHANGE 通知其他进程重新读取环境变量。"""
    HWND_BROADCAST = 0xFFFF
    WM_SETTINGCHANGE = 0x1A
    SMTO_ABORTIFHUNG = 0x0002
    result = ctypes.c_ulong(0)
    ctypes.windll.user32.SendMessageTimeoutW(
        HWND_BROADCAST, WM_SETTINGCHANGE, 0,
        "Environment", SMTO_ABORTIFHUNG, 5000, ctypes.byref(result),
    )


# ==================================================================
#  macOS — networksetup 系统代理
# ==================================================================

def _get_network_services() -> list:
    """列出 macOS 上所有网络服务名称。"""
    try:
        result = subprocess.run(
            ["networksetup", "-listnetworkserviceorder"],
            capture_output=True, text=True, timeout=5,
        )
        services = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("(") and ")" in line:
                svc = line.split(")", 1)[1].strip()
                if svc and not svc.startswith("*"):
                    services.append(svc)
        return services or ["Wi-Fi"]
    except Exception:
        return ["Wi-Fi"]


def _set_darwin(port: int):
    services = _get_network_services()
    saved = {}
    for svc in services:
        try:
            subprocess.run(
                ["networksetup", "-setwebproxy", svc, "127.0.0.1", str(port)],
                capture_output=True, timeout=5,
            )
            subprocess.run(
                ["networksetup", "-setsecurewebproxy", svc, "127.0.0.1", str(port)],
                capture_output=True, timeout=5,
            )
            saved[svc] = True
            _get_logger().info(f"已为网络服务 {svc} 设置系统代理 127.0.0.1:{port}")
        except Exception as e:
            _get_logger().warning(f"为 {svc} 设置系统代理失败: {e}")
    genv.set("_SAVED_DARWIN_PROXY_SVCS", saved)


def _unset_darwin():
    saved = genv.get("_SAVED_DARWIN_PROXY_SVCS")
    if not saved:
        return
    for svc in saved:
        try:
            subprocess.run(
                ["networksetup", "-setwebproxystate", svc, "off"],
                capture_output=True, timeout=5,
            )
            subprocess.run(
                ["networksetup", "-setsecurewebproxystate", svc, "off"],
                capture_output=True, timeout=5,
            )
            _get_logger().info(f"已为网络服务 {svc} 关闭系统代理")
        except Exception:
            pass
    genv.set("_SAVED_DARWIN_PROXY_SVCS", None)


# ==================================================================
#  Linux — gsettings (GNOME 系统代理)
#
#  Crossover/Wine 在 Linux 上使用 Wine 框架，Wine 的 WinHTTP/WinINET
#  实现会读取 GNOME 的系统代理设置。因此通过 gsettings 设置代理后，
#  用户通过 Crossover 启动的 Windows 游戏也能走 mitmproxy。
#
#  工具以 root 运行 (sudo)，需要以实际用户身份执行 gsettings 才能
#  修改用户的 GNOME 代理配置。
# ==================================================================

def _get_real_user() -> str:
    """获取 sudo 前的真实用户名。"""
    return os.environ.get("SUDO_USER", "")


def _gsettings_cmd(args: list, user: str = "") -> bool:
    """以指定用户执行 gsettings 命令。如果 user 为空则直接执行。"""
    cmd = ["gsettings"] + args
    if user:
        cmd = ["sudo", "-u", user] + cmd
    try:
        subprocess.run(cmd, capture_output=True, timeout=5, check=True)
        return True
    except Exception:
        return False


def _has_gsettings() -> bool:
    """检测 gsettings 是否可用。"""
    try:
        subprocess.run(
            ["gsettings", "--version"],
            capture_output=True, timeout=5,
        )
        return True
    except Exception:
        return False


def _set_linux(port: int):
    if not _has_gsettings():
        _get_logger().warning(
            "未检测到 gsettings（非 GNOME 桌面环境）。"
            "请手动设置系统代理为 http://127.0.0.1:%d，"
            "或在启动游戏前设置环境变量 http_proxy / https_proxy。",
            port,
        )
        return

    user = _get_real_user()
    ok = True
    ok &= _gsettings_cmd(["set", "org.gnome.system.proxy", "mode", "manual"], user)
    ok &= _gsettings_cmd(["set", "org.gnome.system.proxy.http", "host", "127.0.0.1"], user)
    ok &= _gsettings_cmd(["set", "org.gnome.system.proxy.http", "port", str(port)], user)
    ok &= _gsettings_cmd(["set", "org.gnome.system.proxy.https", "host", "127.0.0.1"], user)
    ok &= _gsettings_cmd(["set", "org.gnome.system.proxy.https", "port", str(port)], user)

    if ok:
        genv.set("_SAVED_LINUX_PROXY", {"user": user, "port": port})
        _get_logger().info(f"已通过 gsettings 设置 GNOME 系统代理 127.0.0.1:{port}")
    else:
        _get_logger().warning(
            "gsettings 设置代理失败。"
            "请手动设置系统代理为 http://127.0.0.1:%d，"
            "或在启动游戏前设置环境变量 http_proxy / https_proxy。",
            port,
        )


def _unset_linux():
    saved = genv.get("_SAVED_LINUX_PROXY")
    if not saved:
        return
    user = saved.get("user", "")
    _gsettings_cmd(["set", "org.gnome.system.proxy", "mode", "none"], user)
    genv.set("_SAVED_LINUX_PROXY", None)
    _get_logger().info("已通过 gsettings 恢复 GNOME 系统代理设置")

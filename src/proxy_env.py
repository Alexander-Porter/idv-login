# coding=UTF-8
"""跨平台代理环境管理。

统一入口：set_proxy(port) / unset_proxy()
- Windows : 在 HKCU\\Environment 设置 HTTP_PROXY 等并广播 WM_SETTINGCHANGE
- macOS   : 通过 networksetup 设置系统级 HTTP/HTTPS 代理
- Linux   : 通过 gsettings 设置 GNOME 系统代理（Crossover/Wine 会读取 GNOME 代理配置）
"""

import ctypes
import copy
from contextlib import contextmanager
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
# 本工具使用的代理端口范围（10717~10727）
_TOOL_PORTS = set(range(10717, 10728))


def _is_tool_proxy(val) -> bool:
    """判断一个注册表代理值是否属于本工具（127.0.0.1:10717~10727）。"""
    return bool(val) and any(f"127.0.0.1:{p}" in val for p in _TOOL_PORTS)


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


def reset_proxy_state():
    """恢复代理并删除工具配置，整个操作共用同一把跨进程锁。"""
    with _proxy_state_lock():
        if sys.platform == "darwin":
            _unset_darwin_locked()
        elif sys.platform == "linux":
            _unset_linux_locked()
        else:
            raise OSError("此平台不使用系统代理恢复记录")
        return genv.reset_cache()


# ==================================================================
#  Windows — 用户级环境变量
# ==================================================================

def _set_win(port: int, no_proxy_domains: list = None):
    import winreg
    proxy_url = f"http://127.0.0.1:{port}"
    no_proxy_value = ",".join(no_proxy_domains) if no_proxy_domains else ""

    # 如果已存在保存的状态（来自上次崩溃的会话），保留它——里面有用户原始值。
    # 但需验证注册表中仍有本工具的代理残留；若用户已手动修复，丢弃旧状态。
    existing_saved = genv.get("_SAVED_PROXY_ENV") or None

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS
        ) as key:
            if existing_saved:
                # 验证崩溃残留是否仍存在
                still_tool_owned = False
                for var in _PROXY_ENV_VARS_WIN:
                    try:
                        val, _ = winreg.QueryValueEx(key, var)
                        if _is_tool_proxy(val):
                            still_tool_owned = True
                            break
                    except FileNotFoundError:
                        pass
                if not still_tool_owned:
                    # 注册表已无工具代理（用户手动修复），丢弃旧状态
                    existing_saved = None

            if not existing_saved:
                # 保存当前注册表值以便退出时恢复
                saved = {}
                any_tool_owned = False
                for var in _PROXY_ENV_VARS_WIN:
                    try:
                        old_val, _ = winreg.QueryValueEx(key, var)
                        if _is_tool_proxy(old_val):
                            any_tool_owned = True
                            saved[var] = None
                        else:
                            saved[var] = old_val
                    except FileNotFoundError:
                        saved[var] = None
                for var in _NO_PROXY_ENV_VARS_WIN:
                    try:
                        old_val, _ = winreg.QueryValueEx(key, var)
                        # 如果代理变量是工具残留，NO_PROXY 也视为工具设置
                        saved[var] = None if any_tool_owned else old_val
                    except FileNotFoundError:
                        saved[var] = None
                genv.set("_SAVED_PROXY_ENV", saved, True)

            # 写入代理
            for var in _PROXY_ENV_VARS_WIN:
                winreg.SetValueEx(key, var, 0, winreg.REG_SZ, proxy_url)
            if no_proxy_value:
                for var in _NO_PROXY_ENV_VARS_WIN:
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
    _get_logger().info(f"已设置用户代理环境变量: {proxy_url}")


def _is_proxy_reachable(proxy_url: str, timeout: float = 2.0) -> bool:
    """快速 TCP 检查代理是否可达。"""
    import socket
    from urllib.parse import urlparse
    try:
        parsed = urlparse(proxy_url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if not host:
            return False
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((host, port))
            return True
    except (socket.error, ValueError, TypeError, OSError):
        return False


def _unset_win():
    saved = genv.get("_SAVED_PROXY_ENV")
    if not saved:
        return
    import winreg
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS
        ) as key:
            for var, old_val in saved.items():
                if old_val is None:
                    try:
                        winreg.DeleteValue(key, var)
                    except FileNotFoundError:
                        pass
                elif var in _PROXY_ENV_VARS_WIN and not _is_proxy_reachable(old_val):
                    # 旧代理不可达，恢复它会导致用户无法上网
                    _get_logger().warning(f"旧代理 {var}={old_val} 不可达，已删除而非恢复")
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
    genv.set("_SAVED_PROXY_ENV", {}, True)  # 用空 dict 清除持久化状态（None 不会被持久化）
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

_DARWIN_PROXY_STATE = "_SAVED_DARWIN_PROXY_SVCS"
_LINUX_PROXY_STATE = "_SAVED_LINUX_PROXY"


@contextmanager
def _proxy_state_lock():
    """串行化系统代理修改；进程退出后内核会自动释放文件锁。"""
    import fcntl
    workdir = genv.get("FP_WORKDIR") or os.getcwd()
    fd = os.open(os.path.join(workdir, ".proxy-state.lock"), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise OSError("另一个进程正在修改系统代理，请稍后重试") from None
        yield
    finally:
        os.close(fd)


def _save_proxy_state(key, state):
    # 必须先落盘，失败时不能改变系统设置或发布新的内存状态。
    genv.set(key, state, True, require_saved=True)


def _load_proxy_state(key):
    # 不能信任 genv 的进程内缓存：其他进程可能已经接管或清除了记录。
    saved = genv.get_from_file(key, None, require_read=True)
    if not saved:
        return None
    if not isinstance(saved, dict) or saved.get("version") != 1:
        raise OSError("代理恢复记录格式不支持，请手动检查系统代理设置")
    owner = saved.get("owner_pid")
    if type(owner) is not int or owner <= 0:
        raise OSError("代理恢复记录无效")
    if owner != os.getpid():
        try:
            os.kill(owner, 0)
        except ProcessLookupError:
            pass
        except OSError:
            raise OSError("无法确认代理记录所属进程已退出，未修改系统代理") from None
        else:
            raise OSError("另一个工具进程仍持有系统代理设置")
    return copy.deepcopy(saved)


def _networksetup(args):
    try:
        result = subprocess.run(
            ["networksetup"] + args, capture_output=True, text=True,
            timeout=5, check=True, env=dict(os.environ, LC_ALL="C", LANG="C"),
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        raise OSError("无法读取或修改 macOS 系统代理设置") from None


def _get_network_services() -> list:
    """只返回实际查询到的、已启用的 macOS 网络服务。"""
    services = []
    for line in _networksetup(["-listnetworkserviceorder"]).splitlines():
        line = line.strip()
        if line.startswith("(") and ")" in line:
            number, service = line[1:].split(")", 1)
            service = service.strip()
            if number.isdigit() and service and not service.startswith("*"):
                services.append(service)
    return services


def _read_darwin_proxy(service, protocol):
    fields = {}
    for line in _networksetup([f"-get{protocol}proxy", service]).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    try:
        if fields["Enabled"] not in ("Yes", "No") or fields["Authenticated Proxy Enabled"] not in ("0", "1"):
            raise ValueError()
        port = int(fields["Port"])
        if not 0 <= port <= 65535:
            raise ValueError()
        return dict(enabled=fields["Enabled"] == "Yes", server=fields["Server"],
                    port=port, authenticated=fields["Authenticated Proxy Enabled"] == "1")
    except (KeyError, ValueError):
        raise OSError("无法解析 macOS 系统代理设置，未修改该网络服务") from None


def _validate_darwin_state(saved):
    services = saved.get("services")
    if not isinstance(services, dict):
        raise OSError("代理恢复记录无效")
    for service, protocols in services.items():
        if not isinstance(service, str) or not isinstance(protocols, dict) or set(protocols) != {"web", "secureweb"}:
            raise OSError("代理恢复记录无效")
        for entry in protocols.values():
            if not isinstance(entry, dict):
                raise OSError("代理恢复记录无效")
            for name in ("before", "after"):
                state = entry.get(name)
                if (not isinstance(state, dict) or set(state) != {"enabled", "server", "port", "authenticated"}
                        or type(state["enabled"]) is not bool or state["authenticated"] is not False
                        or not isinstance(state["server"], str) or type(state["port"]) is not int
                        or not 0 <= state["port"] <= 65535):
                    raise OSError("代理恢复记录无效")
            after = entry["after"]
            if after != dict(enabled=True, server="127.0.0.1", port=after["port"], authenticated=False):
                raise OSError("代理恢复记录无效")


def _set_darwin(port: int):
    with _proxy_state_lock():
        _set_darwin_locked(port)


def _set_darwin_locked(port):
    _unset_darwin_locked()
    services = {}
    for service in _get_network_services():
        before = {protocol: _read_darwin_proxy(service, protocol) for protocol in ("web", "secureweb")}
        if any(state["authenticated"] for state in before.values()):
            _get_logger().warning("网络服务使用认证代理，已跳过以保留原凭据")
            continue
        services[service] = {
            protocol: dict(before=state, after=dict(enabled=True, server="127.0.0.1", port=port, authenticated=False))
            for protocol, state in before.items()
        }
    if not services:
        raise OSError("没有可安全设置代理的网络服务")
    saved = dict(version=1, owner_pid=os.getpid(), services=services)
    _validate_darwin_state(saved)
    _save_proxy_state(_DARWIN_PROXY_STATE, saved)
    try:
        for service, protocols in services.items():
            for protocol, entry in protocols.items():
                _networksetup([f"-set{protocol}proxy", service, "127.0.0.1", str(port), "off"])
                if _read_darwin_proxy(service, protocol) != entry["after"]:
                    raise OSError("系统代理设置未生效")
    except OSError:
        try:
            _unset_darwin_locked()
        except OSError:
            _get_logger().warning("部分代理设置未能恢复，已保留记录供下次启动重试")
        raise OSError("设置 macOS 系统代理失败") from None
    _get_logger().info("已设置 macOS 系统代理并保存原始配置")


def _unset_darwin():
    with _proxy_state_lock():
        _unset_darwin_locked()


def _unset_darwin_locked():
    saved = _load_proxy_state(_DARWIN_PROXY_STATE)
    if not saved:
        return
    _validate_darwin_state(saved)
    if saved["owner_pid"] != os.getpid():
        saved["owner_pid"] = os.getpid()
        _save_proxy_state(_DARWIN_PROXY_STATE, saved)
    failed = False
    for service, protocols in saved["services"].items():
        for protocol, entry in protocols.items():
            try:
                before, after = entry["before"], entry["after"]
                current = _read_darwin_proxy(service, protocol)
                if current == before:
                    continue
                # 恢复地址的命令会同时启用代理；持久化恢复阶段以跨越此崩溃窗口。
                endpoints = [(state["server"], state["port"]) for state in (before, after)]
                restoring = (entry.get("restoring") and not current["authenticated"]
                             and (current["server"], current["port"]) in endpoints)
                if current != after and not restoring:
                    _get_logger().warning("系统代理已被外部修改，保留当前设置")
                    continue
                entry["restoring"] = True
                _save_proxy_state(_DARWIN_PROXY_STATE, saved)
                try:
                    _networksetup([f"-set{protocol}proxy", service, before["server"], str(before["port"]), "off"])
                finally:
                    _networksetup([f"-set{protocol}proxystate", service, "on" if before["enabled"] else "off"])
                if _read_darwin_proxy(service, protocol) != before:
                    raise OSError("系统代理恢复未生效")
            except OSError:
                failed = True
    if failed:
        raise OSError("部分 macOS 系统代理未能恢复，已保留记录供重试")
    _save_proxy_state(_DARWIN_PROXY_STATE, {})
    _get_logger().info("已恢复 macOS 原始系统代理配置")


# ==================================================================
#  Linux — gsettings (GNOME 系统代理)
# ==================================================================

def _get_real_user() -> str:
    """获取 sudo 前的真实用户名。"""
    return os.environ.get("SUDO_USER", "")


def _gsettings_cmd(args: list, user: str = "") -> str:
    """以原用户身份执行命令，保留 get 返回的 GVariant 文本用于精确恢复。"""
    cmd = ["gsettings"] + args
    if user:
        cmd = ["sudo", "-u", user] + cmd
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=True)
        return (result.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        raise OSError("无法读取或修改 GNOME 系统代理设置") from None


def _has_gsettings() -> bool:
    try:
        subprocess.run(["gsettings", "--version"], capture_output=True, timeout=5, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _validate_linux_state(saved):
    groups, mode = saved.get("groups"), saved.get("mode")
    if (not isinstance(saved.get("user"), str) or not isinstance(groups, list) or len(groups) != 2
            or not isinstance(mode, dict) or mode.get("before") not in ("'auto'", "'manual'", "'none'")
            or mode.get("after") != "'manual'" or not all(isinstance(group, dict) for group in groups)):
        raise OSError("代理恢复记录无效")
    if {group.get("schema") for group in groups} != {"org.gnome.system.proxy.http", "org.gnome.system.proxy.https"}:
        raise OSError("代理恢复记录无效")
    for group in groups:
        for phase in ("before", "after"):
            values = group.get(phase)
            if (not isinstance(values, dict) or set(values) != {"host", "port"}
                    or not all(isinstance(value, str) and value for value in values.values())
                    or not values["port"].isdigit() or not 0 <= int(values["port"]) <= 65535):
                raise OSError("代理恢复记录无效")
        if group["after"]["host"] != "'127.0.0.1'":
            raise OSError("代理恢复记录无效")


def _set_linux(port: int):
    with _proxy_state_lock():
        _set_linux_locked(port)


def _set_linux_locked(port):
    _unset_linux_locked()
    if not _has_gsettings():
        _get_logger().warning("未检测到 gsettings，请手动配置游戏代理")
        return
    user = _get_real_user()
    groups = []
    for protocol in ("http", "https"):
        schema = "org.gnome.system.proxy." + protocol
        before = {key: _gsettings_cmd(["get", schema, key], user) for key in ("host", "port")}
        groups.append(dict(schema=schema, before=before, after=dict(host="'127.0.0.1'", port=str(port))))
    mode = _gsettings_cmd(["get", "org.gnome.system.proxy", "mode"], user)
    saved = dict(version=1, owner_pid=os.getpid(), user=user, groups=groups, mode=dict(before=mode, after="'manual'"))
    _validate_linux_state(saved)
    _save_proxy_state(_LINUX_PROXY_STATE, saved)
    try:
        for group in groups:
            for key, value in group["after"].items():
                _gsettings_cmd(["set", group["schema"], key, value], user)
                if _gsettings_cmd(["get", group["schema"], key], user) != value:
                    raise OSError("系统代理设置未生效")
        _gsettings_cmd(["set", "org.gnome.system.proxy", "mode", "'manual'"], user)
        if _gsettings_cmd(["get", "org.gnome.system.proxy", "mode"], user) != "'manual'":
            raise OSError("系统代理设置未生效")
    except OSError:
        try:
            _unset_linux_locked()
        except OSError:
            _get_logger().warning("部分代理设置未能恢复，已保留记录供下次启动重试")
        raise OSError("设置 GNOME 系统代理失败") from None
    _get_logger().info("已设置 GNOME 系统代理并保存原始配置")


def _unset_linux():
    with _proxy_state_lock():
        _unset_linux_locked()


def _unset_linux_locked():
    saved = _load_proxy_state(_LINUX_PROXY_STATE)
    if not saved:
        return
    _validate_linux_state(saved)
    user = saved["user"]
    if saved["owner_pid"] != os.getpid():
        saved["owner_pid"] = os.getpid()
        _save_proxy_state(_LINUX_PROXY_STATE, saved)
    failed = external = False
    for group in saved["groups"]:
        try:
            schema, before, after = group["schema"], group["before"], group["after"]
            current = {key: _gsettings_cmd(["get", schema, key], user) for key in before}
            if any(current[key] not in (before[key], after[key]) for key in before):
                external = True
                _get_logger().warning("系统代理已被外部修改，保留当前设置")
                continue
            for key, value in before.items():
                if current[key] != value:
                    _gsettings_cmd(["set", schema, key, value], user)
                    if _gsettings_cmd(["get", schema, key], user) != value:
                        raise OSError("系统代理恢复未生效")
        except OSError:
            failed = True
    if not failed and not external:
        current = _gsettings_cmd(["get", "org.gnome.system.proxy", "mode"], user)
        if current == saved["mode"]["after"] and current != saved["mode"]["before"]:
            _gsettings_cmd(["set", "org.gnome.system.proxy", "mode", saved["mode"]["before"]], user)
            if _gsettings_cmd(["get", "org.gnome.system.proxy", "mode"], user) != saved["mode"]["before"]:
                failed = True
    if failed:
        raise OSError("部分 GNOME 系统代理未能恢复，已保留记录供重试")
    _save_proxy_state(_LINUX_PROXY_STATE, {})
    _get_logger().info("已恢复 GNOME 原始系统代理配置")

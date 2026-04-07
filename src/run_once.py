from envmgr import genv
from logutil import setup_logger

def _show_msgbox(title: str, text: str, *, is_error: bool = False):
    """弹窗提示（Qt 尚未初始化，用 Win32 MessageBox）"""
    import sys
    if sys.platform == "win32":
        import ctypes
        style = 0x10 if is_error else 0x40  # MB_ICONERROR / MB_ICONINFORMATION
        ctypes.windll.user32.MessageBoxW(0, text, title, style)
    else:
        print(f"[{title}] {text}")



def run_once():
    """一次性任务，通过 genv 键控制只执行一次"""
    logger = setup_logger()

    # config.json 写入健康检查
    if not genv.get("config_fixed_0403", False):
        import hotfixmgr, os
        if not hotfixmgr.probe_cache_write_once():
            logger.warning("config.json 写入探测失败，尝试修复...")
            try:
                cache_path = "config.json"
                if os.path.exists(cache_path):
                    os.remove(cache_path)
                    logger.info("已删除损坏的 config.json")
            except Exception as e:
                logger.error(f"删除 config.json 失败: {e}")

            # 尝试重新写入
            if hotfixmgr.probe_cache_write_once():
                genv.set("config_fixed_0403", True, True)
                _show_msgbox(
                    "配置文件已重置",
                    "检测到配置文件损坏，已自动重置。\n"
                    "您的账号记录不受影响，但部分设置（如自动登录延迟）可能需要重新配置。",
                )
                logger.info("config.json 修复成功")
            else:
                _show_msgbox(
                    "配置文件修复失败",
                    "无法写入配置文件，这通常是权限问题导致的。\n"
                    "请尝试以管理员身份运行，或联系开发者获取支持。",
                    is_error=True,
                )
                logger.error("config.json 修复失败，写入仍然不可用")
    
    # 清理旧版本遗留的 hosts 记录（修复 isExist bug 后需要重新执行）
    if not genv.get("hosts_cleanup_v600_done", False):
        try:
            from hostmgr import hostmgr
            h_mgr = hostmgr()
            domain_target = genv.get("DOMAIN_TARGET", "service.mkey.163.com")
            domain_oversea = genv.get("DOMAIN_TARGET_OVERSEA", "sdk-os.mpsdk.easebar.com")
            
            if h_mgr.isExist(domain_target):
                logger.warning(f"Hosts文件中已存在{domain_target}的记录，正在尝试删除旧记录...")
                h_mgr.remove(domain_target)
            if h_mgr.isExist(domain_oversea):
                logger.warning(f"Hosts文件中已存在{domain_oversea}的记录，正在尝试删除旧记录...")
                h_mgr.remove(domain_oversea)
            
            genv.set("hosts_cleanup_v600_done", True, True)
            logger.info("hosts 清理完成")
        except Exception as e:
            logger.error(f"删除可能存在的旧Hosts记录失败: {e}")

    # 一次性迁移到兼容模式
    if not genv.get("compat_mode_migrated", False):
        current_mode = genv.get("proxy_mode", "")
        if current_mode != "compat":
            genv.set("proxy_mode", "compat", True)
            logger.info("已自动迁移到兼容模式")
        genv.set("compat_mode_migrated", True, True)

    # 清理残留的系统代理环境变量（工具崩溃/异常退出可能遗留）
    if not genv.get("proxy_env_cleanup_v602_done", False):
        import sys
        if sys.platform == "win32":
            try:
                import winreg
                _stale_ports = ("10717", "10718")
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS
                ) as key:
                    for var in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"):
                        try:
                            val, _ = winreg.QueryValueEx(key, var)
                            if any(f":{p}" in val for p in _stale_ports):
                                winreg.DeleteValue(key, var)
                                logger.info(f"已清理残留环境变量: {var}={val}")
                        except FileNotFoundError:
                            pass
                genv.set("proxy_env_cleanup_v602_done", True, True)
            except Exception as e:
                logger.error(f"清理残留代理环境变量失败: {e}")
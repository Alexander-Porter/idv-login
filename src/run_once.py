import os

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


def _show_yesno(title: str, text: str) -> bool:
    """Yes/No 弹窗，返回用户是否选择 Yes"""
    import sys
    if sys.platform == "win32":
        import ctypes
        # MB_YESNO | MB_ICONQUESTION
        result = ctypes.windll.user32.MessageBoxW(0, text, title, 0x24)
        return result == 6  # IDYES
    else:
        print(f"[{title}] {text}")
        return input("(y/n): ").strip().lower() == 'y'


def _select_exe_file(title: str = "选择游戏可执行文件") -> str:
    """打开文件选择对话框选择 exe 文件"""
    import sys
    if sys.platform != "win32":
        return ""
    try:
        import ctypes
        from ctypes import wintypes
        
        OFN_FILEMUSTEXIST = 0x1000
        OFN_PATHMUSTEXIST = 0x800
        MAX_PATH = 260
        
        class OPENFILENAMEW(ctypes.Structure):
            _fields_ = [
                ("lStructSize", wintypes.DWORD),
                ("hwndOwner", wintypes.HWND),
                ("hInstance", wintypes.HINSTANCE),
                ("lpstrFilter", wintypes.LPCWSTR),
                ("lpstrCustomFilter", wintypes.LPWSTR),
                ("nMaxCustFilter", wintypes.DWORD),
                ("nFilterIndex", wintypes.DWORD),
                ("lpstrFile", wintypes.LPWSTR),
                ("nMaxFile", wintypes.DWORD),
                ("lpstrFileTitle", wintypes.LPWSTR),
                ("nMaxFileTitle", wintypes.DWORD),
                ("lpstrInitialDir", wintypes.LPCWSTR),
                ("lpstrTitle", wintypes.LPCWSTR),
                ("Flags", wintypes.DWORD),
                ("nFileOffset", wintypes.WORD),
                ("nFileExtension", wintypes.WORD),
                ("lpstrDefExt", wintypes.LPCWSTR),
                ("lCustData", wintypes.LPARAM),
                ("lpfnHook", wintypes.LPVOID),
                ("lpTemplateName", wintypes.LPCWSTR),
                ("pvReserved", wintypes.LPVOID),
                ("dwReserved", wintypes.DWORD),
                ("FlagsEx", wintypes.DWORD),
            ]
        
        file_buffer = ctypes.create_unicode_buffer(MAX_PATH)
        ofn = OPENFILENAMEW()
        ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
        ofn.lpstrFilter = "可执行文件\0*.exe\0所有文件\0*.*\0\0"
        ofn.lpstrFile = ctypes.cast(file_buffer, wintypes.LPWSTR)
        ofn.nMaxFile = MAX_PATH
        ofn.lpstrTitle = title
        ofn.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST
        
        if ctypes.windll.comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
            return file_buffer.value
        return ""
    except Exception:
        return ""


def _probe_game_setup(logger):
    """游戏设置引导：检查路径/自启配置并按数量应用策略。"""
    import sys
    import os
    if sys.platform != "win32":
        return
    
    # 已经引导过了
    if genv.get("game_setup_probe_done_0403", False):
        return
    
    from gamemgr import GameManager
    from channelHandler.channelUtils import getShortGameId
    game_mgr = GameManager()
    
    all_games = game_mgr.list_games()
    auto_start_games = game_mgr.list_auto_start_games()
    fever_games = game_mgr.list_fever_games()
    
    # 建立发烧平台游戏的短id映射
    fever_by_short_id = {}
    for fg in fever_games:
        short_id = getShortGameId(fg.get("game_id", ""))
        if short_id:
            fever_by_short_id[short_id] = fg
    
    configured_game_ids = []
    shortcut_created_ids = set()

    def _record_game(gid, shortcut_created=False):
        if not gid:
            return
        if gid not in configured_game_ids:
            configured_game_ids.append(gid)
        if shortcut_created:
            shortcut_created_ids.add(gid)

    def _apply_startup_strategy():
        """按本轮配置数量应用策略：1个自启；>=2个走快捷方式且不自启。"""
        if not configured_game_ids:
            return

        if len(configured_game_ids) == 1:
            gid = configured_game_ids[0]
            if game_mgr.set_game_auto_start(gid, True):
                logger.info(f"本轮仅配置 1 个游戏，已设为自启: {gid}")
            return

        # >=2：关闭这些游戏的自启，统一推荐快捷方式启动
        for gid in configured_game_ids:
            game_mgr.set_game_auto_start(gid, False)
            game_obj = game_mgr.get_existing_game(gid)
            if not game_obj or not game_obj.path or not os.path.exists(game_obj.path):
                continue
            if gid in shortcut_created_ids:
                logger.info(f"游戏 {gid} 在导入阶段已创建快捷方式，跳过重复创建")
                continue
            try:
                game_obj.create_tool_launch_shortcut(game_obj.path)
                logger.info(f"已为游戏创建快捷方式: {gid}")
            except Exception as e:
                logger.error(f"创建快捷方式失败 {gid}: {e}")
        logger.info("本轮配置 >=2 个游戏，已关闭自启并切换为快捷方式启动")

    if not all_games:
        # 情况 1：游戏列表为空 → 建议导入发烧平台游戏
        if fever_games:
            for fg in fever_games:
                name = fg.get("display_name") or fg.get("game_id", "未知游戏")
                if _show_yesno(
                    "导入游戏",
                    f"检测到您尚未添加任何游戏。\n\n"
                    f"在发烧平台发现游戏：{name}\n"
                    f"是否导入此游戏？"
                ):
                    try:
                        final_gid = game_mgr.import_fever_game(fg["game_id"])
                        logger.info(f"已导入发烧平台游戏: {fg['game_id']}")
                        _record_game(final_gid, shortcut_created=True)
                    except Exception as e:
                        logger.error(f"导入游戏失败 {fg['game_id']}: {e}")

        _apply_startup_strategy()
        genv.set("game_setup_probe_done_0403", True, True)
        return

    if all_games and not auto_start_games:
        # 情况 2：有游戏但没有自启游戏 → 引导配置路径/启动方式
        for g in all_games:
            game_id = g["game_id"]
            game_name = g.get("name") or game_id
            game_obj = game_mgr.get_existing_game(game_id)
            has_path = bool(game_obj and game_obj.path and os.path.exists(game_obj.path))
            short_id = getShortGameId(game_id)

            # 检查发烧平台是否有对应游戏
            fever_match = fever_by_short_id.get(short_id)

            if has_path:
                if _show_yesno(
                    "配置启动方式",
                    f'是否将"{game_name}"纳入启动方案？\n\n'
                    "单个游戏会设为自启；多个游戏会改为快捷方式启动。"
                ):
                    _record_game(game_id, shortcut_created=False)
                continue

            if fever_match:
                # 发烧平台有对应游戏，可自动获取路径
                if _show_yesno(
                    "设置游戏路径",
                    f'游戏"{game_name}"尚未设置路径。\n\n'
                    "已在发烧平台找到对应路径，是否自动导入？"
                ):
                    try:
                        final_gid = game_mgr.import_fever_game(fever_match["game_id"])
                        logger.info(f"已从发烧平台导入游戏路径: {game_id}")
                        # import_fever_game 内部已创建快捷方式，后续策略阶段跳过重复创建
                        _record_game(final_gid, shortcut_created=True)
                    except Exception as e:
                        logger.error(f"导入路径失败 {game_id}: {e}")
            else:
                # 需要用户手动选择 exe 路径
                if _show_yesno(
                    "设置游戏路径",
                    f'游戏"{game_name}"尚未设置路径。\n\n'
                    "是否现在选择游戏可执行文件/快捷方式？"
                ):
                    exe_path = _select_exe_file(f"选择 {game_name} 的可执行文件")
                    if exe_path:
                        try:
                            game_mgr.set_game_path(game_id, exe_path)
                            logger.info(f"已设置游戏路径: {game_id}, 路径: {exe_path}")
                            _record_game(game_id, shortcut_created=False)
                        except Exception as e:
                            logger.error(f"设置路径失败 {game_id}: {e}")
                    else:
                        logger.info(f"用户未选择 {game_id} 的可执行文件，跳过")

        _apply_startup_strategy()
    
    # 情况 3：有游戏且有自启 → 什么都不提醒
    genv.set("game_setup_probe_done_0403", True, True)


def _probe_proxy_mode(logger):
    """代理模式引导：统一使用兼容模式。"""
    import sys
    import subprocess
    if sys.platform != "win32":
        return
    
    # 已经询问过了
    if genv.get("proxy_mode_asked_0403", False):
        if genv.get("proxy_mode", "") == "global" and not genv.get("proxy_mode_compat_prompted_0420", False):
            import hotfixmgr
            if not hotfixmgr.probe_cache_write_once():
                return
            genv.set("proxy_mode", "compat", True)
            genv.set("proxy_mode_compat_prompted_0420", True, True)
            logger.info("将已有的全局模式自动变更为兼容模式，即将重启...")
            try:
                from main import handle_exit
                handle_exit()
            except Exception:
                pass

            if getattr(sys, 'frozen', False):
                args = [sys.executable] + sys.argv[1:]
            else:
                args = [sys.executable] + sys.argv

            try:
                subprocess.Popen(args, cwd=genv.get("SCRIPT_DIR") or os.getcwd())
            except Exception:
                # last resort: try without cwd
                subprocess.Popen(args)
            os._exit(0)
        return

    # 首次探测：直接设置为兼容模式，不再承担快捷方式/路径引导。
    genv.set("proxy_mode", "compat", True)
    logger.info("首次探测，自动应用兼容模式")
    genv.set("proxy_mode_asked_0403", True, True)


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
    
    # 游戏设置引导
    try:
        _probe_game_setup(logger)
    except Exception as e:
        logger.error(f"游戏设置引导失败: {e}")
    
    # 代理模式引导（多游戏有账号时）
    try:
        _probe_proxy_mode(logger)
    except Exception as e:
        logger.error(f"代理模式引导失败: {e}")
    
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

    # 一次性清理残留的 NRPT 规则和代理环境变量（工具崩溃/异常退出可能遗留）
    if not genv.get("nrpt_env_cleanup_v603_done", False):
        import sys
        if sys.platform == "win32":
            try:
                from mitm_proxy import remove_all_nrpt_rules
                remove_all_nrpt_rules()
                logger.info("已清理残留 NRPT 规则")
            except Exception as e:
                logger.error(f"清理残留 NRPT 规则失败: {e}")
            try:
                from proxy_env import unset_proxy
                unset_proxy()
                logger.info("已清理残留代理环境变量")
            except Exception:
                pass
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
            except Exception as e:
                logger.error(f"清理残留代理环境变量失败: {e}")
            genv.set("nrpt_env_cleanup_v603_done", True, True)
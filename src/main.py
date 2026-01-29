# coding=UTF-8
"""
 Copyright (c) 2026 Alexander-Porter

 This program is free software: you can redistribute it and/or modify
 it under the terms of the GNU General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 This program is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 GNU General Public License for more details.

 You should have received a copy of the GNU General Public License
 along with this program. If not, see <https://www.gnu.org/licenses/>.
 """

import sys
import argparse
import shutil
import glob


def parse_command_line_args():
    """解析命令行参数"""
    arg_parser = argparse.ArgumentParser(description="第五人格登陆助手")
    arg_parser.add_argument('--mitm', action='store_true', help='直接使用备用模式 (mitmproxy)')
    arg_parser.add_argument('--download', type=str, default="", help='下载任务文件绝对路径')
    return arg_parser.parse_args()


CLI_ARGS = parse_command_line_args()
if not CLI_ARGS.download:
    from gevent import monkey
    monkey.patch_all()

from cloudRes import CloudRes
import socket
import os
import sys
import ctypes
import atexit
import requests
import requests.packages
import json
import random
import string

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(script_dir)

from envmgr import genv


# Global variable declarations
m_certmgr = None
m_hostmgr = None 
m_proxy = None
m_cloudres=None
logger = None # Will be initialized in __main__


def get_computer_name():
    try:
        # 获取计算机名
        computer_name = socket.gethostname()
        # 确保计算机名编码为 UTF-8
        computer_name_utf8 = computer_name.encode('utf-8').decode('utf-8')
        return computer_name_utf8
    except Exception as e:
        logger.exception(f"获取计算机名时发生异常: {e}")
        return None

def handle_exit():
    # Assuming logger is initialized by the time this is called via atexit or signal
    if logger:
        logger.info("程序关闭，正在清理！")
    else:
        print("程序关闭，正在清理！ (logger 未初始化)")

    if not genv.get("USING_BACKUP_VER", False) and m_hostmgr: # m_hostmgr is global
        if logger: logger.info("正在清理 hosts...")
        else: print("正在清理 hosts...")
        m_hostmgr.remove(genv.get("DOMAIN_TARGET"))
        m_hostmgr.remove(genv.get("DOMAIN_TARGET_OVERSEA"))
    
    if genv.get("USING_BACKUP_VER", False):
        backup_mgr = genv.get("backupVerMgr")
        if backup_mgr:
            if logger: logger.info("正在停止 mitmproxy...")
            else: print("正在停止 mitmproxy...")
            backup_mgr.stop_mitmproxy()
    from httpdnsblocker import HttpDNSBlocker
    HttpDNSBlocker().unblock_all()
    print("再见!")




def _check_and_copy_pyqt5_files():
    """
    在frozen模式下检查_MEIPASS路径，如果包含非ASCII字符，
    复制PyQt5相关文件到程序exe所在目录
    """
    try:
        meipass = getattr(sys, '_MEIPASS', None)
        
        if not meipass:
            return
        
        # 检查_MEIPASS路径是否包含非ASCII字符
        has_non_ascii = not all(ord(char) < 128 for char in meipass)
        
        if has_non_ascii:
            logger.info(f"检测到_MEIPASS路径包含非ASCII字符: {meipass}")
            logger.info("正在复制PyQt5文件到程序目录...")
            exe_dir = os.path.dirname(sys.executable)
            if not all(ord(char) < 128 for char in exe_dir):
                logger.error(f"程序exe目录包含非ASCII字符: {exe_dir}")
                input("程序exe目录包含非ASCII字符，可能导致程序异常。请将程序移动到仅包含英文路径的目录后重试，具体请参看《常见问题解决方案》问题十八。按回车键退出。")
                sys.exit(1)

            
            # 只复制Qt5目录下的bin和resources两个子文件夹到exe目录下的Qt5目录
            qt5_source = os.path.join(meipass, "PyQt5", "Qt5")
            qt5_target = os.path.join(exe_dir, "Qt5")

            for subfolder in ["bin", "resources"]:
                src = os.path.join(qt5_source, subfolder)
                dst = os.path.join(qt5_target, subfolder)
                if os.path.exists(src):
                    if os.path.exists(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                    logger.info(f"已复制Qt5子文件夹: {src} -> {dst}")
                else:
                    logger.warning(f"Qt5子文件夹不存在: {src}")
                
            logger.info("PyQt5文件复制完成")
        else:
            logger.debug("_MEIPASS路径仅包含ASCII字符，无需复制PyQt5文件")
            
    except Exception as e:
        logger.error(f"检查和复制PyQt5文件时发生错误: {e}")

def handle_update():

    
    from PyQt5.QtWidgets import QMessageBox, QToolButton, QMenu, QAction, QSizePolicy, QApplication
    from PyQt5.QtCore import Qt
    
    ignoredVersions=genv.get("ignoredVersions",[])
    #ignoredVersions=[]
    if "dev" in genv.get("VERSION","v5.4.0").lower() or "main" in genv.get("VERSION","v5.4.0").lower():
        print("【在线更新】当前版本为开发版本，更新功能已关闭。")
        return
    if genv.get("CLOUD_VERSION")==genv.get("VERSION"):
        print("【在线更新】当前版本已是最新版本。")
        return
    elif not genv.get("CLOUD_VERSION") in ignoredVersions:
        print(f"【在线更新】工具有新版本：{genv.get('CLOUD_VERSION')}。")
        details=CloudRes().get_detail()
        
        QApplication.setAttribute(Qt.AA_DontUseNativeDialogs, True)
        msg_box = QMessageBox()
        msg_box.setWindowTitle(f"新版本！")
        msg_box.setText(f"{genv.get('VERSION')} -> {genv.get('CLOUD_VERSION')}")
        # 将换行符转换为 HTML 换行符以支持富文本显示
        formatted_details = details.replace('\n', '<br>')
        msg_box.setInformativeText(f"{formatted_details}")
        
        yes_btn = msg_box.addButton("现在更新", QMessageBox.AcceptRole)
        
        # 创建带下拉菜单的“暂时跳过”按钮 (Split Button)
        no_btn = QToolButton()
        no_btn.setText("下次提醒我")
        no_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        no_btn.setPopupMode(QToolButton.MenuButtonPopup)
        no_btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        # 设置最小高度以匹配普通按钮
        no_btn.setMinimumHeight(23)
        if CloudRes().is_update_critical():
            pass
        else:
            # 创建“忽略此版本”菜单项
            ignore_action = QAction("忽略此版本", msg_box)
            def on_ignore(checked=False):
                print(f"【在线更新】用户选择忽略版本{genv.get('CLOUD_VERSION')}。")
                ignoredVersions.append(genv.get("CLOUD_VERSION"))
                genv.set("ignoredVersions",ignoredVersions,True)
                msg_box.close() 

            ignore_action.triggered.connect(on_ignore)
        
            menu = QMenu()
            menu.addAction(ignore_action)
            no_btn.setMenu(menu)
        
        # 将按钮点击（主区域）连接到对话框的 reject
        # QToolButton 的 clicked 信号在点击主区域时触发
        no_btn.clicked.connect(msg_box.reject)
        
        msg_box.addButton(no_btn, QMessageBox.RejectRole)
        msg_box.setDefaultButton(yes_btn)
        
        msg_box.exec_()
       
        def go_to_update():
            url=CloudRes().get_downloadUrl()
            import webbrowser
            webbrowser.open(url)
            QMessageBox.information(None, "提示", "请按照打开的网页指引下载更新。\n程序将自动退出。")
            sys.exit(0)
        if msg_box.clickedButton() == yes_btn:
            go_to_update()
        else:
            if CloudRes().is_update_critical():
                info_box = QMessageBox()
                info_box.setWindowTitle("提示")
                info_box.setText("本次更新为安全相关更新，为了保护你的账号安全，请及时更新。")
                update_btn = info_box.addButton("现在更新", QMessageBox.AcceptRole)
                remind_btn = info_box.addButton("我知道了，下次提醒我", QMessageBox.RejectRole)
                info_box.setDefaultButton(update_btn)
                info_box.exec_()
                if info_box.clickedButton() == update_btn:
                    go_to_update()
                else:
                    # 用户选择下次提醒，什么都不做
                    pass
            return
    else:
        print(f"【在线更新】检测到新版本{genv.get('CLOUD_VERSION')}，但已被用户永久跳过。")
        return

def ctrl_handler(ctrl_type):
    if ctrl_type == 2:  # 对应CTRL_CLOSE_EVENT
        handle_exit()
        return False
    return True


def initialize():
    # if we don't have enough privileges, relaunch as administrator
    if sys.platform=='win32':
        if ctypes.windll.shell32.IsUserAnAdmin() == 0:
            # 获取正确的可执行文件路径
            if getattr(sys, 'frozen', False):
                # 如果是PyInstaller打包的exe文件，使用sys.argv[0]
                executable = sys.argv[0]
            else:
                # 如果是Python脚本，使用sys.executable
                executable = sys.executable
            
            # 解决含空格的目录，准备命令行参数
            # 对于exe文件，不需要包含sys.argv[0]在参数中
            if getattr(sys, 'frozen', False):
                # exe文件：只传递从argv[1]开始的参数
                args = sys.argv[1:] if len(sys.argv) > 1 else []
                argvs = [f'"{arg}"' for arg in args]
            else:
                # Python脚本：需要传递完整的argv
                argvs = [f'"{i}"' for i in sys.argv]
            
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", executable, " ".join(argvs), script_dir, 1
            )
            sys.exit()
    else:
        #check if we have root privileges
        if os.geteuid() != 0:
            print("sudo required.")
            sys.exit(1)
    #全局变量声明
    global m_certmgr, m_hostmgr, m_proxy, m_cloudres

        # initialize workpath
    if not os.path.exists(genv.get("FP_WORKDIR")):
        os.mkdir(genv.get("FP_WORKDIR"))
    os.chdir(os.path.join(genv.get("FP_WORKDIR")))


    # initialize the global vars at first
    genv.set("DOMAIN_TARGET", "service.mkey.163.com")
    genv.set("DOMAIN_TARGET_OVERSEA","sdk-os.mpsdk.easebar.com")
    genv.set("FP_FAKE_DEVICE", os.path.join(genv.get("FP_WORKDIR"), "fakeDevice.json"))
    genv.set("FP_WEBCERT", os.path.join(genv.get("FP_WORKDIR"), "domain_cert_3.pem"))
    genv.set("FP_WEBKEY", os.path.join(genv.get("FP_WORKDIR"), "domain_key_3.pem"))
    genv.set("FP_CACERT", os.path.join(genv.get("FP_WORKDIR"), "root_ca_oversea.pem"))
    genv.set("FP_CHANNEL_RECORD", os.path.join(genv.get("FP_WORKDIR"), "channels.json"))
    genv.set("CHANNEL_ACCOUNT_SELECTED", "")
    genv.set("GLOB_LOGIN_PROFILE_PATH", os.path.join(genv.get("FP_WORKDIR"), "profile"))
    genv.set("GLOB_LOGIN_CACHE_PATH", os.path.join(genv.get("FP_WORKDIR"), "cache"))
    genv.set("SCRIPT_DIR", os.path.dirname(os.path.abspath(__file__)))
    CloudPaths = ["https://gitee.com/opguess/idv-login/raw/main/assets/cloudRes.json","https://cdn.jsdelivr.net/gh/Alexander-Porter/idv-login@main/assets/cloudRes.json"]

    # handle exit
    atexit.register(handle_exit)

    from cloudRes import CloudRes
    m_cloudres=CloudRes(CloudPaths,genv.get('FP_WORKDIR'))
    m_cloudres.update_cache_if_needed()
    genv.set("CLOUD_RES",m_cloudres)
    genv.set("CLOUD_VERSION",m_cloudres.get_version())
    genv.set("CLOUD_ANNO",m_cloudres.get_announcement())

    # disable warnings for requests
    requests.packages.urllib3.disable_warnings()



    if not os.path.exists(genv.get("FP_FAKE_DEVICE")):
        udid = "".join(random.choices(string.hexdigits, k=16))
        sdkDevice = {
            "device_model": "M2102K1AC",
            "os_name": "android",
            "os_ver": "12",
            "udid": udid,
            "app_ver": "157",
            "imei": "".join(random.choices(string.digits, k=15)),
            "country_code": "CN",
            "is_emulator": 0,
            "is_root": 0,
            "oaid": "",
        }
        with open(genv.get("FP_FAKE_DEVICE"), "w") as f:
            json.dump(sdkDevice, f)
    else:
        with open(genv.get("FP_FAKE_DEVICE"), "r") as f:
            sdkDevice = json.load(f)
    genv.set("FAKE_DEVICE", sdkDevice)
    
    if not os.path.exists(genv.get("GLOB_LOGIN_PROFILE_PATH")):
        os.makedirs(genv.get("GLOB_LOGIN_PROFILE_PATH"))
    
    from certmgr import certmgr
    from proxymgr import proxymgr
    from macProxyMgr import macProxyMgr
    from channelmgr import ChannelManager
    m_certmgr = certmgr()
    if sys.platform=='darwin':
        m_proxy = macProxyMgr()
    else:
        m_proxy = proxymgr()
    genv.set("CHANNELS_HELPER", ChannelManager())
    #blocks httpdns ips
    from httpdnsblocker import HttpDNSBlocker
    
    # 检查全局HTTPDNS屏蔽设置，默认启用
    httpdns_enabled = genv.get("httpdns_blocking_enabled", False)
    
    if httpdns_enabled:
        HttpDNSBlocker().apply_blocking()
        logger.info(f"HTTPDNS屏蔽已启用，封锁了{len(HttpDNSBlocker().blocked)}个HTTPDNS IP")
    else:
        # 确保之前的屏蔽规则被清除
        HttpDNSBlocker().unblock_all()
    # frozen模式下检查_MEIPASS路径，如果包含非ASCII字符则复制PyQt5文件
    if getattr(sys, 'frozen', False):
        _check_and_copy_pyqt5_files()

    logger.info("初始化内置浏览器")
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtWebEngineCore import QWebEngineUrlScheme
    from PyQt5.QtNetwork import QNetworkProxyFactory
    genv.set("APP",QApplication([]))
    QWebEngineUrlScheme.registerScheme(QWebEngineUrlScheme("hms".encode()))
    QNetworkProxyFactory.setUseSystemConfiguration(False)

    #该版本首次使用会弹出教程
    if genv.get(f"{genv.get('VERSION')}_first_use",True):
        
        import webbrowser
        url=CloudRes().get_guideUrl()
        genv.set("httpdns_blocking_enabled",False,True)
        webbrowser.open(url)
        genv.set(f"{genv.get('VERSION')}_first_use",False,True)
    try:
        setup_shortcuts()
    except:
        logger.error("创建快捷方式失败")
    computer_name = get_computer_name()
    if computer_name is not None and not all(ord(char) < 128 for char in computer_name):
        logger.error(f"计算机名包含非ASCII字符: {computer_name}，可能导致程序异常！")
        logger.error("如果程序出错，请将计算机名修改为纯英文后重试！具体请参见常见问题解决文档。")

    #如果是windows，清空DNS缓存
    if sys.platform=='win32':
        os.system("ipconfig /flushdns")

def welcome():
    print(f"[+] 欢迎使用第五人格登陆助手 {genv.get('VERSION')}!")
    print(" - 官方项目地址 : https://github.com/Alexander-Porter/idv-login/")
    print(" - 如果你的这个工具不能用了，请前往仓库检查是否有新版本发布或加群询问！")
    print(" - 本程序使用GNU GPLv3协议开源，完全免费，严禁倒卖！")
    print(" - This program is free software: you can redistribute it and/or modify")
    print(" - it under the terms of the GNU General Public License as published by")
    print(" - the Free Software Foundation, either version 3 of the License, or")
    print(" - (at your option) any later version.")
def handle_announcement():
    if genv.get("CLOUD_ANNO")!="":
        print(f"【公告】{genv.get('CLOUD_ANNO')}")
def cloudBuildInfo():
    try:
        from buildinfo import BUILD_INFO,VERSION
        message=BUILD_INFO
        genv.set("VERSION",VERSION)
        print(f"构建信息：{message}。如需校验此版本是否被篡改，请前往官方项目地址。")
    except:
        print("警告：没有找到校验信息，请不要使用本工具，以免被盗号。")

def prepare_platform_workdir():
    if sys.platform=='win32':
        kernel32 = ctypes.WinDLL("kernel32")
        HandlerRoutine = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
        handle_ctrl = HandlerRoutine(ctrl_handler)
        kernel32.SetConsoleCtrlHandler(handle_ctrl, True)
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-10), (0x4|0x80|0x20|0x2|0x10|0x1|0x00|0x100))
        genv.set("FP_WORKDIR", os.path.join(os.environ["PROGRAMDATA"], "idv-login"))
    elif sys.platform=='darwin':
        setup_signal_handlers()
        mac_app_support = os.path.expanduser("~/Library/Application Support")
        genv.set("FP_WORKDIR", os.path.join(mac_app_support, "idv-login"))
        os.environ["PROGRAMDATA"] = mac_app_support
    elif sys.platform=='linux':
        setup_signal_handlers()
        home = os.path.expanduser("~")
        genv.set("FP_WORKDIR", os.path.join(home, ".idv-login"))
        os.environ["PROGRAMDATA"] = genv.get("FP_WORKDIR")





def setup_work_directory():
    """设置和创建工作目录"""
    # 确保工作目录存在，使用makedirs可以创建多级目录
    if not os.path.exists(genv.get("FP_WORKDIR")):
        try:
            os.makedirs(genv.get("FP_WORKDIR"), exist_ok=True)
        except Exception as e:
            print(f"创建工作目录失败: {e}")
            # 如果无法创建标准目录，则尝试使用当前目录
            genv.set("FP_WORKDIR", os.path.join(os.getcwd(), "idv-login"))
            os.makedirs(genv.get("FP_WORKDIR"), exist_ok=True)
    
    # 切换到工作目录
    try:
        os.chdir(genv.get("FP_WORKDIR"))
        print(f"已将工作目录设置为 -> {genv.get('FP_WORKDIR')}")
    except Exception as e:
        print(f"切换到工作目录失败: {e}")

def handle_download_task(task_file_path):
    if not task_file_path:
        print("缺少下载任务文件路径")
        return False
    task_file_path = os.path.abspath(task_file_path)
    if not os.path.exists(task_file_path):
        print(f"下载任务文件不存在: {task_file_path}")
        return False
    prepare_platform_workdir()
    setup_work_directory()
    from logutil import setup_logger
    logger_local = setup_logger()
    task_data = None
    try:
        with open(task_file_path, "r", encoding="utf-8") as f:
            task_data = json.load(f)
    except Exception as e:
        logger_local.exception(f"读取下载任务文件失败: {e}")
        return False
    download_root = task_data.get("download_root", "")
    directories = task_data.get("directories", [])
    files = task_data.get("files", [])
    concurrent_files = int(task_data.get("concurrent_files", 2))
    game_id = task_data.get("game_id", "")
    version_code = task_data.get("version_code", "")
    distribution_id = int(task_data.get("distribution_id", -1))
    convert_to_normal = bool(task_data.get("convert_to_normal", False))
    result = True
    if files:
        from game_updater import GameUpdater
        updater = GameUpdater(
            download_root=download_root,
            concurrent_files=concurrent_files,
            directories=directories,
            files=files
        )
        result = updater.start()
    if result and game_id and version_code:
        from gamemgr import GameManager
        game_mgr = GameManager()
        game = game_mgr.get_game(game_id)
        if game:
            game.version = version_code
            if distribution_id != -1:
                game.default_distribution = distribution_id
            if convert_to_normal:
                game.convert_to_normal()
            game_mgr._save_games()
    try:
        os.remove(task_file_path)
    except Exception as e:
        logger_local.exception(f"删除下载任务文件失败: {e}")
    return result


def cleanup_expired_certificates():
    """清理过期的证书文件"""
    # 检查证书是否过期
    web_cert_expired = m_certmgr.is_certificate_expired(genv.get("FP_WEBCERT"))
    ca_cert_expired = m_certmgr.is_certificate_expired(genv.get("FP_CACERT"))

    if web_cert_expired or ca_cert_expired:
        logger.info("一个或多个证书已过期或不存在，正在重新生成...")
        # 删除旧证书文件（如果存在）
        cert_files = [
            (genv.get("FP_WEBCERT"), "网站证书"),
            (genv.get("FP_WEBKEY"), "网站密钥"),
            (genv.get("FP_CACERT"), "CA证书")
        ]
        
        for cert_path, cert_name in cert_files:
            if os.path.exists(cert_path):
                os.remove(cert_path)
                logger.info(f"已删除旧的{cert_name}: {cert_path}")
    
    return web_cert_expired, ca_cert_expired


def generate_certificates_if_needed():
    """检查并生成必要的证书文件"""
    web_cert_expired, ca_cert_expired = cleanup_expired_certificates()
    
    if (os.path.exists(genv.get("FP_WEBCERT")) == False) or \
       (os.path.exists(genv.get("FP_WEBKEY")) == False) or \
       (os.path.exists(genv.get("FP_CACERT")) == False) or \
       web_cert_expired or ca_cert_expired: # 添加过期检查条件
        logger.info("正在生成必要的证书文件...")

        ca_key = m_certmgr.generate_private_key(bits=2048)
        ca_cert = m_certmgr.generate_ca(ca_key)
        m_certmgr.export_cert(genv.get("FP_CACERT"), ca_cert)

        srv_key = m_certmgr.generate_private_key(bits=2048)
        srv_cert = m_certmgr.generate_cert(
            [genv.get("DOMAIN_TARGET"),genv.get("DOMAIN_TARGET_OVERSEA"),"localhost"], srv_key, ca_cert, ca_key
        )

        if m_certmgr.import_to_root(genv.get("FP_CACERT")) == False:
            logger.error("导入CA证书失败!")
            if sys.platform == 'win32': # Keep platform-specific behavior
                os.system("pause")
            else:
                input("导入CA证书失败，请按回车键退出。")
            sys.exit(-1)

        m_certmgr.export_cert(genv.get("FP_WEBCERT"), srv_cert)
        m_certmgr.export_key(genv.get("FP_WEBKEY"), srv_key)
        logger.info("证书初始化成功!")


def setup_backup_version_manager():
    """初始化备用版本管理器"""
    from backupvermgr import BackupVersionMgr
    backupVerMgr_instance = BackupVersionMgr(work_dir=genv.get("FP_WORKDIR"))
    backupVerMgr_instance._create_mitm_shortcut()
    return backupVerMgr_instance

def setup_shortcuts():
    """设置快捷方式"""
    from shortcutmgr import ShortcutMgr
    shortcutMgr_instance = ShortcutMgr()
    shortcutMgr_instance.handle_shortcuts()

def start_mitm_mode(backupVerMgr_instance):
    """启动MITM代理模式"""
    logger.warning("正在启动备用方案 (mitmproxy)...")
    pid = os.getpid()
    try:
        genv.set("backupVerMgr", backupVerMgr_instance)
        if backupVerMgr_instance.setup_environment(): 
            if backupVerMgr_instance.start_mitmproxy_redirect(pid):
                genv.set("USING_BACKUP_VER", True, False) # Mark as actively using MITM
                logger.info("备用方案 (mitmproxy) 启动成功!")
                return True
            else:
                logger.error("备用方案 (mitmproxy) 启动失败。程序将继续，但可能无法正常工作。")
        else:
            logger.error("备用方案 (mitmproxy) 环境设置失败。程序将继续，但可能无法正常工作。")
    except Exception as e_mitm:
        logger.exception(f"启动备用方案 (mitmproxy) 时发生错误: {e_mitm}")
        logger.error("备用方案 (mitmproxy) 启动时发生异常。程序将继续，但可能无法正常工作。")
    return False


def setup_host_manager():
    """设置Host管理器进行域名重定向"""
    global m_hostmgr
    logger.info("正在重定向目标地址到本机 (hosts 文件修改)...")
    try:
        from hostmgr import hostmgr 
        # m_hostmgr is a global variable, assign the instance to it.
        m_hostmgr = hostmgr() 

        if m_hostmgr.isExist(genv.get("DOMAIN_TARGET")) == True:
            logger.info("识别到手动定向!")
            logger.info(
                f"请确保已经将 {genv.get('DOMAIN_TARGET')}、{genv.get('DOMAIN_TARGET_OVERSEA')} 和 localhost 指向 127.0.0.1"
            )
        else:
            m_hostmgr.add(genv.get("DOMAIN_TARGET"), "127.0.0.1")
            m_hostmgr.add(genv.get("DOMAIN_TARGET_OVERSEA"), "127.0.0.1")
            m_hostmgr.add("localhost", "127.0.0.1")
        return True
    except Exception as e_hostmgr:
        logger.warning(f"Host管理器初始化失败 ({e_hostmgr})，正在尝试备用方案 (mitmproxy)...")
        return False


def fallback_to_mitm():
    """当Host管理器失败时，回退到MITM模式"""
    from backupvermgr import BackupVersionMgr
    pid = os.getpid()
    try:
        backupVerMgr_instance = BackupVersionMgr(work_dir=genv.get("FP_WORKDIR"))
        genv.set("backupVerMgr", backupVerMgr_instance) # Store for cleanup
        # Check if backupVer was already true (e.g. from config) or if env setup is ok
        if genv.get("backupVer", False) and backupVerMgr_instance.setup_environment():
            genv.set("backupVer", True, True) # Mark intention/attempt
            if backupVerMgr_instance.start_mitmproxy_redirect(pid):
                genv.set("USING_BACKUP_VER", True, False) # Mark as actively using MITM
                logger.info("备用方案 (mitmproxy) 启动成功!")
            else:
                logger.error("备用方案 (mitmproxy) 启动失败。")
        else:
            logger.error("备用方案 (mitmproxy) 环境设置失败。")
    except Exception as e_mitm_fallback:
        logger.exception(f"尝试备用方案 (mitmproxy) 时发生错误: {e_mitm_fallback}")
        logger.error("备用方案 (mitmproxy) 尝试时发生异常。")


def setup_network_proxy(force_mitm_mode):
    """设置网络代理（Host管理器或MITM模式）"""
    backupVerMgr_instance = setup_backup_version_manager()
    
    if force_mitm_mode:
        logger.info("命令行参数指定使用备用模式。")
        genv.set("backupVer", True, True)
        start_mitm_mode(backupVerMgr_instance)
    else:
        # Standard host modification logic
        if not setup_host_manager():
            # Fallback to MITM (original logic)
            fallback_to_mitm()


def handle_error_and_exit(e):
    """处理异常并退出程序"""
    try:
        import debugmgr
        debugmgr.DebugMgr().export_debug_info()
    except:
        pass
    if logger: # Check if logger was initialized
        logger.exception(
            f"发生未处理的异常:{e}.反馈时请发送日志！\n日志路径:{genv.get('FP_WORKDIR')}下的log.txt"
        )
    else:
        print(f"发生未处理的异常:{e}. 日志记录器未初始化。")
        # Try to provide workdir info if genv is available
        workdir_path = genv.get('FP_WORKDIR', '未知') if 'genv' in locals() else '未知'
        print(f"工作目录: {workdir_path}")

    # Original logic to open explorer, with safeguards
    try:
        log_file_path = os.path.join(genv.get("FP_WORKDIR"), "log.txt")
        if sys.platform == 'win32' and os.path.exists(log_file_path):
            # Ensure the path is quoted for explorer if it contains spaces
            os.system(f'explorer /select,"{log_file_path}"')
        input_message = "发生错误。如果可能，已尝试打开日志文件所在目录。按回车键退出。"
    except Exception: # Fallback if genv or FP_WORKDIR is not set
        input_message = "发生严重错误，无法获取日志路径。按回车键退出。"

    input(input_message)

def setup_signal_handlers():
    import signal
    
    def signal_handler(sig, frame):
        print(f"捕获到信号 {sig}，正在执行清理...")
        handle_exit()
        sys.exit(0)
    # 捕获常见的终止信号
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # kill 命令
    if sys.platform!='win32':
        signal.signal(signal.SIGHUP, signal_handler)   # 终端关闭
def main(cli_args=None):


    """主函数入口"""
    global logger
    if cli_args is None:
        cli_args = CLI_ARGS
    prepare_platform_workdir()
    
    # 设置工作目录
    setup_work_directory()

    # Initialize logger (assign to global logger variable)
    from logutil import setup_logger
    logger = setup_logger() 

    force_mitm_mode = cli_args.mitm

    try:
        cloudBuildInfo()
        initialize() # This sets up atexit(handle_exit) among other things
        welcome()
        handle_update()
        handle_announcement()
        
        # 证书管理
        generate_certificates_if_needed()

        # 网络代理设置
        setup_network_proxy(force_mitm_mode)
        
        # Start proxy server (m_proxy is global, initialized in initialize())
        logger.info("正在启动代理服务器...")
        m_proxy.run()

    except Exception as e:
        handle_error_and_exit(e)


if __name__ == "__main__":
    try:
        if CLI_ARGS.download:
            success = handle_download_task(CLI_ARGS.download)
            sys.exit(0 if success else 1)
    except:
        import traceback
        traceback.print_exception()
        traceback.print_stack()
    main(CLI_ARGS)

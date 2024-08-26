# coding=UTF-8
"""
 Copyright (c) 2024 Alexander-Porter & fwilliamhe

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
import pywintypes
import sys
import pyperclip as cb
if len(sys.argv) > 1 and sys.argv[-1].startswith("hms://"):
    try:
        cb.copy(sys.argv[-1])
    except pywintypes.error as e:
        print(f"Failed to write {sys.argv[-1]} to clipboard: {e}")
        input()
        sys.exit(1)
    sys.exit(0)

from gevent import monkey
monkey.patch_all()

import os
import sys
import ctypes
import atexit
import requests
import requests.packages
import json
import random
import string


from envmgr import genv
from logutil import setup_logger


m_certmgr = None
m_hostmgr = None
m_proxy = None
m_cloudres=None

import winreg as reg


def handle_exit():
    logger.info("程序关闭，正在清理 hosts ！")
    m_hostmgr.remove(genv.get("DOMAIN_TARGET"))  # 无论如何退出都应该进行清理
    print("再见!")

def handle_update():
    ignoredVersions=genv.get("ignoredVersions",[])
    if "dev" in genv.get("VERSION"):
        print("【在线更新】当前版本为开发版本，更新功能已关闭。")
        return
    if genv.get("CLOUD_VERSION")==genv.get("VERSION"):
        print("【在线更新】当前版本已是最新版本。")
        return
    elif not genv.get("CLOUD_VERSION") in ignoredVersions:
        print(f"【在线更新】检测到新版本{genv.get('CLOUD_VERSION')}，按回车跳转至新版本下载页面。按P+Enter暂时不更新，按N+Enter永久跳过此版本。")
        details=genv.get("CLOUD_RES").get_detail()
        print(f"{details}")
        choice=input()
        if choice.lower()=="p":
            return
        elif choice.lower()=="n":
            ignoredVersions.append(genv.get("CLOUD_VERSION"))
            genv.set("ignoredVersions",ignoredVersions,True)
            return
        else:
            url=genv.get("CLOUD_RES").get_downloadUrl()
            import webbrowser
            webbrowser.open(url)
            input("【更新方法】按照页面上的指引下载新的.exe文件即可。")
            sys.exit(0)
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
    if ctypes.windll.shell32.IsUserAnAdmin() == 0:
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        sys.exit()

    #全局变量声明
    global m_certmgr, m_hostmgr, m_proxy, m_cloudres

        # initialize workpath
    if not os.path.exists(genv.get("FP_WORKDIR")):
        os.mkdir(genv.get("FP_WORKDIR"))
    os.chdir(os.path.join(genv.get("FP_WORKDIR")))


    # initialize the global vars at first
    genv.set("DOMAIN_TARGET", "service.mkey.163.com")
    genv.set("FP_WEBCERT", os.path.join(genv.get("FP_WORKDIR"), "domain_cert_2.pem"))
    genv.set("FP_FAKE_DEVICE", os.path.join(genv.get("FP_WORKDIR"), "fakeDevice.json"))
    genv.set("FP_WEBKEY", os.path.join(genv.get("FP_WORKDIR"), "domain_key_2.pem"))
    genv.set("FP_CACERT", os.path.join(genv.get("FP_WORKDIR"), "root_ca.pem"))
    genv.set("FP_CHANNEL_RECORD", os.path.join(genv.get("FP_WORKDIR"), "channels.json"))
    genv.set("CHANNEL_ACCOUNT_SELECTED", "")
    CloudPath = "https://gitee.com/opguess/idv-login/raw/main/assets/cloudRes.json"

    # handle exit
    atexit.register(handle_exit)

    from cloudRes import CloudRes
    m_cloudres=CloudRes(CloudPath,genv.get('FP_WORKDIR'))
    m_cloudres.update_cache_if_needed()
    genv.set("CLOUD_RES",m_cloudres)
    genv.set("CLOUD_VERSION",m_cloudres.get_version())


    # (Can't) copy web assets! Have trouble using pyinstaller = =
    # shutil.copytree( "web_assets", genv.get("FP_WORKDIR"), dirs_exist_ok=True)

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
    from certmgr import certmgr
    from hostmgr import hostmgr
    from proxymgr import proxymgr
    from channelmgr import ChannelManager
    m_certmgr = certmgr()
    m_hostmgr = hostmgr()
    m_proxy = proxymgr()
    # 关于线程安全：谁？
    genv.set("CHANNELS_HELPER", ChannelManager())

    logger.info("初始化内置浏览器")
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtWebEngineCore import QWebEngineUrlScheme
    genv.set("APP",QApplication([]))
    QWebEngineUrlScheme.registerScheme(QWebEngineUrlScheme("hms".encode()))

    #该版本首次使用会弹出教程
    if genv.get(f"{genv.get('VERSION')}_first_use",True):
        import webbrowser
        url=genv.get("CLOUD_RES").get_guideUrl()
        webbrowser.open(url)
        genv.set(f"{genv.get('VERSION')}_first_use",False,True)

def welcome():
    print(f"[+] 欢迎使用第五人格登陆助手 {genv.get('VERSION')}!")
    print(" - 官方项目地址 : https://github.com/Alexander-Porter/idv-login/")
    print(" - 如果你的这个工具不能用了，请前往仓库检查是否有新版本发布或加群询问！")
    print(" - 本程序使用GNU GPLv3协议开源， 严禁将本程序用于任何商业行为！")
    print(" - This program is free software: you can redistribute it and/or modify")
    print(" - it under the terms of the GNU General Public License as published by")
    print(" - the Free Software Foundation, either version 3 of the License, or")
    print(" - (at your option) any later version.")

def cloudBuildInfo():
    try:
        from buildinfo import BUILD_INFO,VERSION
        message=BUILD_INFO
        genv.set("VERSION",VERSION)
        print(f"构建信息：{message}。如需校验此版本是否被篡改，请前往官方项目地址。")
    except:
        print("警告：没有找到校验信息，请不要使用本工具，以免被盗号。")

if __name__ == "__main__":
    kernel32 = ctypes.WinDLL("kernel32")
    HandlerRoutine = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
    handle_ctrl = HandlerRoutine(ctrl_handler)
    kernel32.SetConsoleCtrlHandler(handle_ctrl, True)
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-10), (0x4|0x80|0x20|0x2|0x10|0x1|0x00|0x100))

    genv.set("FP_WORKDIR", os.path.join(os.environ["PROGRAMDATA"], "idv-login"))
    if not os.path.exists(genv.get("FP_WORKDIR")):
        os.mkdir(genv.get("FP_WORKDIR"))
    os.chdir(os.path.join(genv.get("FP_WORKDIR")))
    print(f"已将工作目录设置为 -> {genv.get('FP_WORKDIR')}")
    logger = setup_logger(__name__)
    try:
        cloudBuildInfo()
        initialize()
        welcome()
        handle_update()
        if (os.path.exists(genv.get("FP_WEBCERT")) == False) or (
            os.path.exists(genv.get("FP_WEBKEY")) == False
        ):
            logger.info("正在生成必要的证书文件...")

            ca_key = m_certmgr.generate_private_key(bits=2048)
            ca_cert = m_certmgr.generate_ca(ca_key)
            m_certmgr.export_cert(genv.get("FP_CACERT"), ca_cert)

            srv_key = m_certmgr.generate_private_key(bits=2048)
            srv_cert = m_certmgr.generate_cert(
                [genv.get("DOMAIN_TARGET"), "localhost"], srv_key, ca_cert, ca_key
            )

            if m_certmgr.import_to_root(genv.get("FP_CACERT")) == False:
                logger.error("导入CA证书失败!")
                os.system("pause")
                sys.exit(-1)

            m_certmgr.export_cert(genv.get("FP_WEBCERT"), srv_cert)
            m_certmgr.export_key(genv.get("FP_WEBKEY"), srv_key)
            logger.info("初始化成功!")

        logger.info("正在重定向目标地址到本机...")
        if m_hostmgr.isExist(genv.get("DOMAIN_TARGET")) == True:
            logger.info("识别到手动定向!")
            logger.info(
                f"请确保已经将 {genv.get('DOMAIN_TARGET')} 和 localhost 指向 127.0.0.1"
            )
        else:
            m_hostmgr.add(genv.get("DOMAIN_TARGET"), "127.0.0.1")
            m_hostmgr.add("localhost", "127.0.0.1")

        logger.info("正在启动代理服务器...")

        m_proxy.run()

    except Exception as e:
        logger.exception(
            f"发生未处理的异常:{e}.反馈时请发送日志\n日志路径:{genv.get('FP_WORKDIR')}下的log.txt",
            stack_info=True,
            exc_info=True,
        )

        input("拦截退出事件.")

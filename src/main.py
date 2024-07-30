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
PIPE_NAME = r'\\.\pipe\idv-login'
import win32file
if len(sys.argv) > 2:
    try:
        handle = win32file.CreateFile(
            PIPE_NAME,
            win32file.GENERIC_WRITE,
            0, None,
            win32file.OPEN_EXISTING,
            0, None
        )
        win32file.WriteFile(handle, sys.argv[2].encode())
        handle.close()
    except pywintypes.error as e:
        print(f"Failed to write to named pipe: {e}")
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

import winreg as reg

def register_url_scheme(scheme_name, executable_path):
    try:
        # 打开 HKEY_CLASSES_ROOT 注册表项
        key = reg.CreateKey(reg.HKEY_CLASSES_ROOT, scheme_name)
        reg.SetValue(key, '', reg.REG_SZ, f'URL:{scheme_name} Protocol')
        reg.SetValueEx(key, 'URL Protocol', 0, reg.REG_SZ, '')

        # 创建 shell\open\command 子项
        command_key = reg.CreateKey(key, r'shell\open\command')
        reg.SetValue(command_key, '', reg.REG_SZ, f'"{executable_path}" "%1"')

        print(f'{scheme_name} URL scheme registered successfully.')
    except Exception as e:
        print(f'Failed to register {scheme_name} URL scheme: {e}')

def handle_exit():
    win32file.CloseHandle(genv.get("PIPE"))
    logger.info("程序关闭，正在清理 hosts ！")
    m_hostmgr.remove(genv.get("DOMAIN_TARGET"))  # 无论如何退出都应该进行清理
    print("再见!")


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
    #for huawei, register hms://
    
    executable_path = sys.executable
    #如果是从解释器启动，不做任何事
    if not executable_path.endswith("python.exe"):
        register_url_scheme('hms', executable_path)



    # initialize the global vars at first
    genv.set("DOMAIN_TARGET", "service.mkey.163.com")
    genv.set("FP_WEBCERT", os.path.join(genv.get("FP_WORKDIR"), "domain_cert_2.pem"))
    genv.set("FP_CONFIG", os.path.join(genv.get("FP_WORKDIR"), "config.json"))
    genv.set("FP_FAKE_DEVICE", os.path.join(genv.get("FP_WORKDIR"), "fakeDevice.json"))
    genv.set("FP_WEBKEY", os.path.join(genv.get("FP_WORKDIR"), "domain_key_2.pem"))
    genv.set("FP_CACERT", os.path.join(genv.get("FP_WORKDIR"), "root_ca.pem"))
    genv.set("FP_CHANNEL_RECORD", os.path.join(genv.get("FP_WORKDIR"), "channels.json"))
    genv.set("CHANNEL_ACCOUNT_SELECTED", "")

    # handle exit
    atexit.register(handle_exit)

    # initialize object
    from certmgr import certmgr
    from hostmgr import hostmgr
    from proxymgr import proxymgr
    from channelmgr import ChannelManager
    global m_certmgr, m_hostmgr, m_proxy
    m_certmgr = certmgr()
    m_hostmgr = hostmgr()
    m_proxy = proxymgr()

    # initialize workpath
    if not os.path.exists(genv.get("FP_WORKDIR")):
        os.mkdir(genv.get("FP_WORKDIR"))

    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-10), (0x4|0x80|0x20|0x2|0x10|0x1|0x00|0x100))
    # (Can't) copy web assets! Have trouble using pyinstaller = =
    # shutil.copytree( "web_assets", genv.get("FP_WORKDIR"), dirs_exist_ok=True)

    os.chdir(os.path.join(genv.get("FP_WORKDIR")))

    # 关于线程安全：谁？
    genv.set("CHANNELS_HELPER", ChannelManager())

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

    if not os.path.exists(genv.get("FP_CONFIG")):
        with open(genv.get("FP_CONFIG"), "w") as f:
            json.dump({}, f)
            genv.set("CONFIG", {})
    else:
        with open(genv.get("FP_CONFIG"), "r") as f:
            genv.set("CONFIG", json.load(f))


def welcome():
    print("[+] 欢迎使用第五人格登陆助手 version 5.2.2-beta")
    print(" - 官方项目地址 : https://github.com/Alexander-Porter/idv-login/")
    print(" - 如果你的这个工具不能用了，请前往仓库检查是否有新版本发布或加群询问！")
    print(" - 本程序使用GNU GPLv3协议开源， 严禁将本程序用于任何商业行为！")
    print(" - This program is free software: you can redistribute it and/or modify")
    print(" - it under the terms of the GNU General Public License as published by")
    print(" - the Free Software Foundation, either version 3 of the License, or")
    print(" - (at your option) any later version.")






if __name__ == "__main__":

    kernel32 = ctypes.WinDLL("kernel32")
    HandlerRoutine = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
    handle_ctrl = HandlerRoutine(ctrl_handler)
    kernel32.SetConsoleCtrlHandler(handle_ctrl, True)

    genv.set("FP_WORKDIR", os.path.join(os.environ["PROGRAMDATA"], "idv-login"))
    if not os.path.exists(genv.get("FP_WORKDIR")):
        os.mkdir(genv.get("FP_WORKDIR"))
    os.chdir(os.path.join(genv.get("FP_WORKDIR")))
    print(f"已将工作目录设置为 -> {genv.get('FP_WORKDIR')}")
    logger = setup_logger(__name__)
    try:
        welcome()
        initialize()

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
            f"发生未处理的异常:{e}.日志路径:{genv.get('FP_WORKDIR')}下的log.txt",
            stack_info=True,
            exc_info=True,
        )

        input("拦截退出事件.")

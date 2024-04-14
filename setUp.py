import os
import subprocess
import getpass
import shutil
import ctypes
import sys
import time

script_path = os.path.dirname(os.path.realpath(__file__))
print(f"脚本路径: {script_path}")
os.chdir(script_path)

# Check if we are running as an administrator
if ctypes.windll.shell32.IsUserAnAdmin() == 0:
    # We are not running "as Administrator" - so relaunch as administrator
    print("非管理员，按回车尝试以管理员身份重试")
    input("Press Enter to continue...")
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, __file__, None, 1)
    sys.exit(0)

print("Installing mitmproxy...")
subprocess.check_call(["pip", "uninstall", "mitmproxy"])
subprocess.check_call(["pip", "install", "mitmproxy"])
#生成证书
#启动mitmproxy，运行5s，然后关闭

cert_path = os.path.join(os.path.expanduser("~"), ".mitmproxy", "mitmproxy-ca-cert.cer")
mitmproxy_proc = subprocess.Popen(["mitmproxy"])
time.sleep(5)
print(f"证书路径：{cert_path}")
print("检查证书是否存在")
import time
if os.path.exists(cert_path):
    shutil.copy(cert_path, os.path.join(script_path, "mitmproxy-ca-cert.cer"))
else:
    print(f"证书不存在，请手动查找证书并将其复制到当前目录（{script_path}）下")
    input("Press Enter to continue...")

print("安装证书")
subprocess.check_call(["certutil", "-addstore", "root", os.path.join(script_path, "mitmproxy-ca-cert.cer")])
input("按回车键退出...下次运行run.py即可启动mitmproxy...")
mitmproxy_proc.terminate()
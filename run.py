import os
import subprocess
import sys
import ctypes

script_path = os.path.dirname(os.path.realpath(__file__))
print(f"脚本路径: {script_path}")
os.chdir(script_path)
print("待到玻璃碎后，关闭本程序")
# Check if we are running as an administrator
if ctypes.windll.shell32.IsUserAnAdmin() == 0:
    # We are not running "as Administrator" - so relaunch as administrator
    print("非管理员，重试")

    # Create a new process object that starts Python
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, __file__, None, 1)

    # Exit from the current, unelevated, process
    sys.exit(0)

# Start mitmweb with specified arguments
subprocess.call(["mitmweb", "-s", "netease.py", "--mode", "transparent", "--allow-hosts", "service.mkey.163.com", "--set", "block_global=false"])

input("按回车退出")
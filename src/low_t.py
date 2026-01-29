import ctypes
import sys
import os
import game_updater
print("欢迎使用IDV-LOGIN 新引擎下载工具V1.1。本工具支持覆盖安装，安装完成后会自动进行免发烧平台处理。请确保游戏目录下有15G左右的空闲空间。")
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(script_dir)
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

#请求用户指定dwrg.exe的位置，使用PyQt
from PyQt5.QtWidgets import QApplication, QFileDialog
import sys

app = QApplication(sys.argv)
options = QFileDialog.Options()
options |= QFileDialog.ReadOnly
file_path, _ = QFileDialog.getOpenFileName(None, "选择dwrg.exe", "", "Executable Files (*.exe);;All Files (*)", options=options)
if file_path:
    print(f"选择的文件路径: {file_path}")
else:
    print("未选择任何文件")
from gamemgr import GameManager,Game
game=Game("h55","第五人格",file_path,default_distribution=73)
#Qt询问下载线程数量
from PyQt5.QtWidgets import QApplication, QInputDialog
import sys


thread_count, ok = QInputDialog.getInt(None, "下载线程数量", "请输入下载线程数量:", 4, 1, 10, 1)
if ok:
    print(f"选择的线程数量: {thread_count}")
else:
    print("未选择任何线程数量")

distribution_id=73
download_root = game.get_root_path()
if not download_root or not os.path.exists(download_root):
    print(f"游戏路径无效或不存在: {download_root}")


file_distribution_info = game.get_file_distribution_info(distribution_id)
if not file_distribution_info:
    print(f"未找到分发ID {distribution_id} 的文件分发信息")

files = file_distribution_info.get("files", [])
directories = file_distribution_info.get("directories", [])
check_result, to_update = game.version_check(files)
#version_code=file_distribution_info.get("version_code", "")
#v3_2547


if not check_result:
    updater = game_updater.GameUpdater(
        download_root=game.get_root_path(),
        concurrent_files=thread_count,
        directories=directories,
        files=to_update
    )
    result = updater.start()
    if result:
        game.version = file_distribution_info.get("version_code", game.version)

    else:
        print(f"游戏更新失败")

#查找并删除游戏目录下的pack_config.xml
pack_config_path=os.path.join(game.get_root_path(),"pack_config.xml")
if os.path.exists(pack_config_path):
    os.remove(pack_config_path)
    print(f"已删除发烧平台相关文件，游戏愉快！")
input("按任意键继续...")
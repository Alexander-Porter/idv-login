import os
import sys

def get_executable_path():
    if getattr(sys, 'frozen', False):
        # Case 1: Using pyinstaller
        return sys.executable
    else:
        # Case 2: Using global python
        if os.path.isabs(sys.argv[0]):
            return sys.executable + " " + sys.argv[0]
        else:
            # Case 3: Using a specific python interpreter
            return sys.executable + " " + os.path.join(os.getcwd(), sys.argv[0])
    
def run_job(*args):
    # 获取可执行文件路径
    executable_path = get_executable_path()
    # 拼接命令
    command = f"{executable_path} {' '.join(args)}"
    # 执行命令
    result = os.system(command)
    return result == 0


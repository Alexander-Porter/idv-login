import platform
import webbrowser
import sys
import select
import time
from cloudRes import CloudRes
from const import VERSION
from envmgr import genv

class UpdateManager:
    """更新管理器，处理平台特定的版本检查和更新逻辑"""
    
    def __init__(self, cloud_res: CloudRes):
        self.cloud_res = cloud_res
        self.current_platform = self._get_current_platform()
    
    def _get_current_platform(self):
        """获取当前平台标识"""
        system = platform.system().lower()
        if system == 'windows':
            return 'windows'
        elif system == 'darwin':
            return 'darwin'
        elif system == 'linux':
            return 'linux'
        else:
            return 'unknown'
    
    def get_platform_version(self):
        """获取当前平台的目标版本"""
        platform_versions = self.cloud_res.get_platform_versions()
        if not platform_versions:
            # 如果没有平台版本信息，回退到通用版本
            return self.cloud_res.get_version()
        
        return platform_versions.get(self.current_platform, self.cloud_res.get_version())
    
    def should_update(self):
        """检查是否需要更新"""
        if VERSION.endswith('-dev'):
            return False
        
        current_version = VERSION
        target_version = self.get_platform_version()
        
        # 如果目标版本为空或与当前版本相同，则不需要更新
        if not target_version or current_version == target_version:
            return False
        
        # 检查是否被用户跳过
        ignored_versions = genv.get('ignoredVersions', [])
        if target_version in ignored_versions:
            return False
        
        return True
    
    def handle_update(self):
        """处理更新逻辑"""
        if not self.should_update():
            return
        
        target_version = self.get_platform_version()
        download_url = self.cloud_res.get_downloadUrl()
        
        print(f"【在线更新】发现新版本 {target_version}，当前版本 {VERSION}")
        
        # 显示更新详情
        update_detail = self.cloud_res.get_detail()
        if update_detail:
            print("\n=== 版本更新内容 ===")
            # 处理Unicode转义字符
            try:
                import codecs
                decoded_detail = codecs.decode(update_detail, 'unicode_escape')
                print(decoded_detail)
            except:
                print(update_detail)
            print("=" * 50)
        
        print("\n请在10秒内选择操作：")
        print("  按 P + 回车：暂时跳过")
        print("  按 N + 回车：永久跳过此版本")
        print("  直接按回车：立即更新")
        print("  10秒内无操作：自动跳转更新页面")
        
        user_choice = self._wait_for_user_input(10)
        
        if user_choice == 'p':
            print("【在线更新】已暂时跳过更新")
        elif user_choice == 'n':
            self._skip_version(target_version)
        elif user_choice == '' or user_choice is None:
            print("【在线更新】正在打开下载页面...")
            webbrowser.open(download_url)
        else:
            print("【在线更新】无效输入，正在打开下载页面...")
            webbrowser.open(download_url)
    
    def _wait_for_user_input(self, timeout):
        """等待用户输入，支持超时"""
        if sys.platform == 'win32':
            import msvcrt
            start_time = time.time()
            input_chars = []
            
            while time.time() - start_time < timeout:
                if msvcrt.kbhit():
                    char = msvcrt.getch().decode('utf-8', errors='ignore')
                    if char == '\r':  # 回车键
                        return ''.join(input_chars).lower().strip()
                    elif char == '\b':  # 退格键
                        if input_chars:
                            input_chars.pop()
                            sys.stdout.write('\b \b')
                            sys.stdout.flush()
                    elif char.isprintable():
                        input_chars.append(char)
                        sys.stdout.write(char)
                        sys.stdout.flush()
                time.sleep(0.1)
            return None  # 超时
        else:
            # Unix/Linux/macOS
            import termios
            import tty
            
            old_settings = termios.tcgetattr(sys.stdin)
            try:
                tty.setraw(sys.stdin.fileno())
                start_time = time.time()
                input_chars = []
                
                while time.time() - start_time < timeout:
                    if select.select([sys.stdin], [], [], 0.1)[0]:
                        char = sys.stdin.read(1)
                        if char == '\n' or char == '\r':  # 回车键
                            return ''.join(input_chars).lower().strip()
                        elif ord(char) == 127:  # 退格键
                            if input_chars:
                                input_chars.pop()
                                sys.stdout.write('\b \b')
                                sys.stdout.flush()
                        elif char.isprintable():
                            input_chars.append(char)
                            sys.stdout.write(char)
                            sys.stdout.flush()
                return None  # 超时
            finally:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
    
    def _skip_version(self, version):
        """跳过指定版本的更新"""
        ignored_versions = genv.get('ignoredVersions', [])
        if version not in ignored_versions:
            ignored_versions.append(version)
            genv.set('ignoredVersions', ignored_versions, True)  # 保存到配置文件
            print(f"【在线更新】已永久跳过版本 {version}")
        else:
            print(f"【在线更新】版本 {version} 已在跳过列表中")
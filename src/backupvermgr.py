from logutil import setup_logger
from cert_utils import is_mitmproxy_certificate_installed, install_certificate_to_store
from ssl_utils import should_verify_ssl
import os
import subprocess
import requests
import time
import shutil
import zipfile
import urllib.parse
import platform
import sys


logger = setup_logger()

class BackupVersionMgr:
    def __init__(self, work_dir=None):
        # 工作目录设置
        self.work_dir = work_dir or os.path.dirname(os.path.abspath(__file__))
        self.python_dir = os.path.join(self.work_dir, "python")
        self.python_exe = os.path.join(self.python_dir, "python.exe")
        self.pip_exe = os.path.join(self.python_dir, "Scripts", "pip.exe")
        self.mitm_proxy_exe = os.path.join(self.python_dir, "Scripts", "mitmdump.exe")
        self.mitm_proxy_process = None
        
        # Python下载源
        self.python_sources = {
            "official": "https://www.python.org/ftp/python/",
            "huawei": "https://mirrors.huaweicloud.com/python/"
        }
        
        # Pip镜像源
        self.pip_mirrors = {
            "tsinghua": "https://pypi.tuna.tsinghua.edu.cn/simple",
            "aliyun": "https://mirrors.aliyun.com/pypi/simple",
            "ustc": "https://pypi.mirrors.ustc.edu.cn/simple",
            "hust": "https://mirrors.hust.edu.cn/pypi/simple",
            "official": "https://pypi.python.org/simple"
        }
        
        # get-pip.py 镜像源
        self.get_pip_sources = {
            "official": "https://bootstrap.pypa.io/get-pip.py",
            "gitee": "https://gitee.com/opguess/idv-login/raw/main/assets/get-pip.py"
        }
    
    def test_url_speed(self, url):
        """测试URL的响应速度"""
        try:
            start_time = time.time()
            session = requests.Session()
            session.trust_env = False
            response = session.head(url, timeout=5, verify=should_verify_ssl())
            end_time = time.time()
            
            if response.status_code < 400:
                return end_time - start_time
            else:
                return float('inf')
        except Exception as e:
            logger.error(f"测试URL {url} 速度时出错: {e}")
            return float('inf')
    
    def find_fastest_source(self, sources, test_url_suffix=""):
        """找到最快的源"""
        results = {}
        for name, base_url in sources.items():
            test_url = urllib.parse.urljoin(base_url, test_url_suffix)
            speed = self.test_url_speed(test_url)
            results[name] = speed
            logger.debug(f"源 {name} ({test_url}) 的响应时间: {speed:.4f}秒")
        
        fastest = min(results.items(), key=lambda x: x[1])
        logger.info(f"最快的源是 {fastest[0]} 响应时间为 {fastest[1]:.4f}秒")
        return sources[fastest[0]]
    
    def download_file(self, url, save_path):
        """下载文件"""
        try:
            logger.info(f"正在从 {url} 下载文件到 {save_path}")
            session = requests.Session()
            session.trust_env = False
            response = session.get(url, stream=True, verify=should_verify_ssl())
            response.raise_for_status()
            
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"文件下载完成: {save_path}")
            return True
        except Exception as e:
            logger.error(f"下载文件时出错: {e}")
            return False
    
    def extract_zip(self, zip_path, extract_to):
        """解压ZIP文件"""
        try:
            logger.info(f"正在解压 {zip_path} 到 {extract_to}")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_to)
            logger.info(f"解压完成: {extract_to}")
            return True
        except Exception as e:
            logger.error(f"解压文件时出错: {e}")
            return False
    
    def install_portable_python(self, version="3.12.9"):
        """下载并安装便携版Python"""
        # 确保工作目录存在
        os.makedirs(self.work_dir, exist_ok=True)
        
        # 找到最快的Python下载源
        fastest_source = self.find_fastest_source(self.python_sources)
        
        # 构建下载URL (Windows embeddable版本)
        python_zip_name = f"python-{version}-embed-amd64.zip"
        download_url = urllib.parse.urljoin(fastest_source, f"{version}/{python_zip_name}")
        
        # 下载Python
        zip_path = os.path.join(self.work_dir, python_zip_name)
        if not self.download_file(download_url, zip_path):
            logger.error("无法下载Python安装包")
            return False
        
        # 解压Python
        if os.path.exists(self.python_dir):
            shutil.rmtree(self.python_dir)
        
        if not self.extract_zip(zip_path, self.python_dir):
            logger.error("无法解压Python安装包")
            return False
        
        # 删除下载的zip文件
        os.remove(zip_path)
        
        # 配置Python以支持pip
        self._enable_pip_for_embedded_python()
        
        return os.path.exists(self.python_exe)
    
    def _enable_pip_for_embedded_python(self):
        """为嵌入式Python启用pip"""
        # 找到python**._pth文件并修改它以启用import site
        pth_files = [f for f in os.listdir(self.python_dir) if f.endswith("._pth")]
        if not pth_files:
            logger.error("找不到Python的pth配置文件")
            return False
        
        pth_file = os.path.join(self.python_dir, pth_files[0])
        with open(pth_file, 'r') as f:
            content = f.read()
        
        # 取消注释 import site
        if "#import site" in content:
            content = content.replace("#import site", "import site")
            with open(pth_file, 'w') as f:
                f.write(content)
        
        # 选择最快的 get-pip.py 源
        fastest_get_pip = self.find_fastest_source(self.get_pip_sources)
        get_pip_path = os.path.join(self.python_dir, "get-pip.py")
        if not self.download_file(fastest_get_pip, get_pip_path):
            logger.error("无法下载get-pip.py")
            return False
        
        # 安装pip
        result = subprocess.run(
            [self.python_exe, get_pip_path],
            cwd=self.python_dir,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            logger.error(f"安装pip失败: {result.stderr}")
            return False
        
        logger.info("pip安装成功")
        return True
    
    def setup_pip_mirror(self):
        """设置pip镜像源"""
        # 首先检查pip是否已安装
        if not os.path.exists(self.pip_exe):
            logger.warning("pip可执行文件不存在，尝试重新安装pip")
            if not self._enable_pip_for_embedded_python():
                logger.error("重新安装pip失败")
                return False
            logger.info("pip重新安装成功")
        
        # 测试各个镜像的速度
        fastest_mirror = self.find_fastest_source(self.pip_mirrors)
          # 设置pip镜像
        try:
            result = subprocess.run(
                [self.pip_exe, "config", "set", "global.index-url", fastest_mirror],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                logger.error(f"设置pip镜像失败: {result.stderr}")
                return False
                
            logger.info(f"Pip镜像设置成功: {fastest_mirror}")
            return True
        except Exception as e:
            logger.error(f"设置pip镜像时出错: {e}")
            return False
    
    def _check_package_installed(self, package_name):
        """检查指定包是否已安装"""
        try:
            result = subprocess.run(
                [self.pip_exe, "show", package_name],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"检查包 {package_name} 是否安装时出错: {e}")
            return False
    
    def install_setuptools(self):
        """安装 setuptools 和 wheel（如果尚未安装）"""
        try:
            packages_to_install = []
            
            # 检查 setuptools 是否已安装
            if not self._check_package_installed("setuptools"):
                packages_to_install.append("setuptools")
                logger.info("setuptools 未安装，将进行安装")
            else:
                logger.debug("setuptools 已存在")
            
            # 检查 wheel 是否已安装
            if not self._check_package_installed("wheel"):
                packages_to_install.append("wheel")
                logger.info("wheel 未安装，将进行安装")
            else:
                logger.debug("wheel 已存在")
            
            # 如果没有需要安装的包，直接返回成功
            if not packages_to_install:
                logger.debug("setuptools 和 wheel 都已安装，跳过安装步骤")
                return True
            
            # 安装需要的包
            logger.info(f"开始安装: {', '.join(packages_to_install)}")
            result = subprocess.run(
                [self.pip_exe, "install"] + packages_to_install,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                logger.error(f"安装 {', '.join(packages_to_install)} 失败: {result.stderr}")
                return False
                
            logger.info(f"{', '.join(packages_to_install)} 安装成功")
            return True
        except Exception as e:
            logger.error(f"安装 setuptools 时出错: {e}")
            return False
    
    def install_mitmproxy(self):
        """安装mitmproxy（如果尚未安装）"""
        try:
            # 首先检查mitmproxy是否已安装
            if self._check_package_installed("mitmproxy"):
                logger.info("mitmproxy 已存在")
                # 进一步检查可执行文件是否存在
                if os.path.exists(self.mitm_proxy_exe):
                    logger.info("mitmproxy 可执行文件已存在，跳过安装步骤")
                    return True
                else:
                    logger.warning("mitmproxy 包已安装但可执行文件不存在，将重新安装")
            
            logger.info("开始安装mitmproxy")
            result = subprocess.run(
                [self.pip_exe, "install", "mitmproxy"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                logger.error(f"安装mitmproxy失败: {result.stderr}")
                return False
                
            logger.info("mitmproxy安装成功")
            return os.path.exists(self.mitm_proxy_exe)
        except Exception as e:
            logger.error(f"安装mitmproxy时出错: {e}")
            return False
    
    def init_mitmproxy_cert(self):
        """初始化mitmproxy证书"""
        try:
            # 首先检查证书是否已经安装在系统根证书存储中
            if is_mitmproxy_certificate_installed():
                logger.info("mitmproxy证书已安装在系统根证书存储中，跳过安装")
                return True
            
            # 运行一次mitmproxy以生成证书
            logger.info("运行mitmproxy以生成证书")
            
            # 运行mitmdump并立即停止
            process = subprocess.Popen(
                [self.mitm_proxy_exe, "--no-http2"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            time.sleep(3)
            
            # 终止进程
            process.terminate()
            
            # 检查证书文件是否生成
            cert_path = os.path.expanduser("~/.mitmproxy/mitmproxy-ca-cert.cer")
            if not os.path.exists(cert_path):
                logger.error(f"证书文件不存在: {cert_path}")
                return False
            
            # 再次检查证书是否已安装（可能在生成过程中已安装）
            if is_mitmproxy_certificate_installed():
                logger.info("mitmproxy证书已存在于系统根证书存储中")
                return True
            
            # 使用cert_utils安装证书
            logger.info("使用certutil安装证书到系统根证书存储")
            if install_certificate_to_store(cert_path, "ROOT"):
                logger.info("mitmproxy证书安装成功")
                return True
            else:
                logger.error("mitmproxy证书安装失败")
                return False
                
        except Exception as e:
            logger.error(f"初始化mitmproxy证书时出错: {e}")
            return False
    
    def start_mitmproxy_redirect(self, pid=None):
        """启动mitmproxy并重定向流量"""
        if self.mitm_proxy_process and self.mitm_proxy_process.poll() is None:
            logger.info("mitmproxy已经在运行中")
            return True
        
        try:
            logger.info("启动mitmproxy以重定向流量")
            
            # 创建一个简单的脚本来处理请求
            script_path = os.path.join(self.work_dir, "mitm_script.py")
            with open(script_path, "w") as f:
                f.write("""
from mitmproxy import http, ctx
import ssl

def request(flow: http.HTTPFlow) -> None:
    if "service.mkey.163.com" in flow.request.pretty_host:
        flow.request.host = "localhost"
        flow.request.scheme = "https"
        flow.request.port = 443
        
# Configure mitmproxy to ignore SSL verification
def running():
    ctx.options.ssl_insecure = True
""")
            
            # 使用 -s 参数运行这个脚本，将标准输出和标准错误重定向
            log_file = os.path.join(self.work_dir, "mitmproxy.log")
            with open(log_file, "w") as f_log:
                self.mitm_proxy_process = subprocess.Popen(
                    [
                        self.mitm_proxy_exe,
                        "--mode", f"local:!{pid}",
                        "-s", script_path
                    ],
                    stdout=f_log,
                    stderr=subprocess.STDOUT,
                    text=True
                )
            
            # 等待一小段时间确保进程启动
            time.sleep(2)
            
            # 检查是否成功启动
            if self.mitm_proxy_process.poll() is not None:
                with open(log_file, "r") as f:
                    error_output = f.read()
                logger.error(f"启动mitmproxy失败: {error_output}")
                return False
                
            logger.info("mitmproxy已在后台启动")
            return True
        except Exception as e:
            logger.error(f"启动mitmproxy时出错: {e}")
            return False
    
    def stop_mitmproxy(self):
        """停止mitmproxy"""
        if self.mitm_proxy_process and self.mitm_proxy_process.poll() is None:
            try:
                self.mitm_proxy_process.terminate()
                self.mitm_proxy_process.wait(timeout=5)
                logger.info("mitmproxy已停止")
                return True
            except Exception as e:
                logger.error(f"停止mitmproxy时出错: {e}")
                try:
                    self.mitm_proxy_process.kill()
                except:
                    pass
        return False

    def _detect_current_executable_path(self):
        """检测当前可执行文件或脚本的路径"""
        try:
            if getattr(sys, 'frozen', False):
                # 如果是PyInstaller打包的执行文件
                exe_path = sys.executable
                logger.debug(f"检测到PyInstaller打包环境，可执行文件路径: {exe_path}")
                return exe_path, True  # 返回路径和是否为exe的标志
            else:
                # 如果是Python脚本
                script_path = os.path.abspath(sys.argv[0])
                logger.debug(f"检测到Python脚本环境，脚本路径: {script_path}")
                return script_path, False  # 返回路径和是否为exe的标志
        except Exception as e:
            logger.error(f"检测可执行文件路径时出错: {e}")
            return None, False
    
    def _create_mitm_shortcut(self):
        """在当前程序位置创建启动备用模式的快捷方式"""
        if sys.platform != 'win32':
            return False
        try:
            # 检测当前可执行文件路径
            current_path, is_exe = self._detect_current_executable_path()
            if not current_path:
                logger.error("无法检测当前程序路径")
                return False
            
            current_dir = os.path.dirname(current_path)
            if is_exe:
                shortcut_dir = current_dir
            else:
                shortcut_dir = os.path.join(os.path.expanduser("~"), "Desktop")
                if not os.path.exists(shortcut_dir):
                    shortcut_dir = current_dir
            shortcut_path = os.path.join(shortcut_dir, "idv-login 启动备用模式.lnk")
            
            # 如果快捷方式已存在，先删除
            if os.path.exists(shortcut_path):
                os.remove(shortcut_path)
                logger.debug(f"已删除旧的快捷方式: {shortcut_path}")
            else:
                logger.info(f"首次启动，创建备用版本快捷方式: {shortcut_path}")

            # 使用COM接口创建快捷方式
            import win32com.client
            
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(shortcut_path)
            
            if is_exe:
                # 如果是exe文件，直接指向exe并添加--mitm参数
                shortcut.Targetpath = current_path
                shortcut.Arguments = "--mitm"
                shortcut.WorkingDirectory = current_dir
            else:                # 如果是Python脚本，指向Python解释器，脚本作为参数
                shortcut.Targetpath = sys.executable
                shortcut.Arguments = f'"{current_path}" --mitm'
                shortcut.WorkingDirectory = current_dir
            
            shortcut.Description = "第五人格登陆助手 - 备用模式"
            shortcut.IconLocation = current_path + ",0"  # 使用程序本身的图标
            
            shortcut.save()
            
            # 设置快捷方式以管理员权限运行
            if self._set_shortcut_admin_privileges(shortcut_path):
                logger.debug("快捷方式已设置为以管理员权限运行")
            else:
                logger.warning("设置管理员权限失败，但快捷方式仍可正常使用")
            return True
        except Exception as e:
            logger.error(f"创建快捷方式时出错: {e}")
            return False
    
    def _set_shortcut_admin_privileges(self, shortcut_path):
        """设置快捷方式以管理员权限运行"""
        try:
            # 读取快捷方式文件的二进制数据
            with open(shortcut_path, 'rb') as f:
                data = bytearray(f.read())
            
            # 根据官方Microsoft文档，设置RunAsAdministrator标志位
            # 需要修改字节21 (0x15)，设置bit 6 (0x20)为1
            if len(data) > 0x15:
                # 设置字节21的bit 6 (0x20)，这是RunAsAdministrator标志位
                data[0x15] = data[0x15] | 0x20
                
                # 保存修改后的文件
                with open(shortcut_path, 'wb') as f:
                    f.write(data)
                
                logger.debug(f"成功设置快捷方式管理员权限: {shortcut_path}")
                return True
            else:
                logger.warning("快捷方式文件格式异常，无法设置管理员权限")
                return False
                
        except Exception as e:
            logger.error(f"设置快捷方式管理员权限时出错: {e}")
            # 尝试使用备用方法（通过PowerShell）
            return False
    


    def setup_environment(self):
        """设置完整的环境"""
        logger.info("开始设置备用版本环境...")
        
        try:
            # 步骤1: 检查并安装便携版Python
            if not os.path.exists(self.python_exe):
                logger.info("便携版Python不存在，开始安装...")
                if not self.install_portable_python():
                    logger.error("便携版Python安装失败")
                    return False
                logger.info("便携版Python安装成功")
            else:
                logger.info("便携版Python已存在，跳过安装")
            
            # 步骤2: 设置pip镜像源
            logger.info("设置pip镜像源...")
            if not self.setup_pip_mirror():
                logger.error("pip镜像源设置失败")
                return False
            
            # 步骤3: 检查并安装setuptools和wheel
            logger.info("检查setuptools和wheel...")
            if not self.install_setuptools():
                logger.error("setuptools安装失败")
                return False

            # 步骤4: 检查并安装mitmproxy
            if not os.path.exists(self.mitm_proxy_exe):
                logger.info("mitmproxy可执行文件不存在，开始安装...")
                if not self.install_mitmproxy():
                    logger.error("mitmproxy安装失败")
                    return False
                logger.info("mitmproxy安装成功")
            else:
                logger.info("mitmproxy已存在，跳过安装")
                
            # 步骤5: 初始化mitmproxy证书
            logger.info("初始化mitmproxy证书...")
            if not self.init_mitmproxy_cert():
                logger.warning("mitmproxy证书初始化失败")
                return False
            
            # 步骤6: 在Windows系统上创建备用模式快捷方式
            if sys.platform == 'win32':
                logger.info("正在创建备用模式快捷方式...")
                try:
                    if self._create_mitm_shortcut():
                        pass
                    else:
                        logger.warning("快捷方式创建失败，但不影响主要功能")
                except Exception as e:
                    logger.warning(f"创建快捷方式时发生异常: {e}，但不影响主要功能")
            
            logger.info("备用版本环境设置完成！")
            return True
            
        except Exception as e:
            logger.exception(f"设置环境时发生未处理的异常: {e}")
            return False

if __name__ == "__main__":
    mgr = BackupVersionMgr()
    if not mgr.setup_environment():
        logger.error("环境设置失败")
        sys.exit(1)

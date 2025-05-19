from logutil import setup_logger
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
            "hust": "https://mirrors.hust.edu.cn/pypi/simple"
        }
    
    def test_url_speed(self, url):
        """测试URL的响应速度"""
        try:
            start_time = time.time()
            response = requests.head(url, timeout=5)
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
            logger.info(f"源 {name} ({test_url}) 的响应时间: {speed:.4f}秒")
        
        fastest = min(results.items(), key=lambda x: x[1])
        logger.info(f"最快的源是 {fastest[0]} 响应时间为 {fastest[1]:.4f}秒")
        return sources[fastest[0]]
    
    def download_file(self, url, save_path):
        """下载文件"""
        try:
            logger.info(f"正在从 {url} 下载文件到 {save_path}")
            response = requests.get(url, stream=True)
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
        
        # 下载get-pip.py
        get_pip_url = "https://bootstrap.pypa.io/get-pip.py"
        get_pip_path = os.path.join(self.python_dir, "get-pip.py")
        
        if not self.download_file(get_pip_url, get_pip_path):
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
    
    def install_mitmproxy(self):
        """安装mitmproxy"""
        try:
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
            
            # 安装证书
            cert_path = os.path.expanduser("~/.mitmproxy/mitmproxy-ca-cert.cer")
            if not os.path.exists(cert_path):
                logger.error(f"证书文件不存在: {cert_path}")
                return False
            
            # 使用certutil安装证书
            logger.info("使用certutil安装证书")
            result = subprocess.run(
                ["certutil", "-addstore", "ROOT", cert_path],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                logger.error(f"安装证书失败: {result.stderr}")
                return False
                
            logger.info("mitmproxy证书安装成功")
            return True
        except Exception as e:
            logger.error(f"初始化mitmproxy证书时出错: {e}")
            return False
    
    def start_mitmproxy_redirect(self):
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
                        "--mode", "local",
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
    
    def install_setuptools(self):
        """安装 setuptools"""
        try:
            logger.info("开始安装 setuptools")
            result = subprocess.run(
                [self.pip_exe, "install", "setuptools", "wheel"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                logger.error(f"安装 setuptools 失败: {result.stderr}")
                return False
                
            logger.info("setuptools 安装成功")
            return True
        except Exception as e:
            logger.error(f"安装 setuptools 时出错: {e}")
            return False
    
    def setup_environment(self):
        """设置完整的环境"""
        success = True
        try:
            # 步骤1: 安装便携版Python
            if not os.path.exists(self.python_exe):
                success = success and self.install_portable_python()
            else:
                logger.info("便携版Python已存在")
            
            # 步骤2: 设置pip镜像
            if success:
                success = success and self.setup_pip_mirror()
            
            # 步骤3: 安装setuptools
            if success:
                success = success and self.install_setuptools()

            # 步骤4: 安装mitmproxy
            if success and not os.path.exists(self.mitm_proxy_exe):
                success = success and self.install_mitmproxy()
            else:
                logger.info("mitmproxy已存在")
            
            # 步骤5: 初始化mitmproxy证书
            if success:
                success = success and self.init_mitmproxy_cert()
            
            return success
        except:
            logger.exception("Error: setup")
            return False
if __name__ == "__main__":
    mgr = BackupVersionMgr()
    if not mgr.setup_environment():
        logger.error("环境设置失败")
        sys.exit(1)

    # 启动mitmproxy
    if not mgr.start_mitmproxy_redirect():
        logger.error("启动mitmproxy重定向失败")
        sys.exit(1)
    
    logger.info("环境设置完成，mitmproxy已启动")
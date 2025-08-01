# coding=UTF-8
"""
 Copyright (c) 2025 Alexander-Porter

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

import platform
import socket
import getpass
import os
import subprocess
import json
from datetime import datetime
from logutil import setup_logger
from channelHandler.channelUtils import _get_my_ip

try:
    import psutil
except ImportError:
    psutil = None

try:
    import winreg
except ImportError:
    winreg = None

class DebugMgr:
    """调试管理器 - 仅限Windows系统使用"""
    
    @staticmethod
    def is_windows():
        """检查是否为Windows系统"""
        return platform.system().lower() == 'windows'
    
    @staticmethod
    def get_process_list():
        """获取当前进程列表"""
        if not psutil:
            return ["psutil库未安装，无法获取进程列表"]
        
        processes = []
        try:
            for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent']):
                try:
                    process_info = {
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'memory_mb': round(proc.info['memory_info'].rss / 1024 / 1024, 2) if proc.info['memory_info'] else 0,
                        'cpu_percent': proc.info['cpu_percent']
                    }
                    processes.append(process_info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            processes.append(f"获取进程列表时出错: {str(e)}")
        
        return processes
    
    @staticmethod
    def get_installed_apps():
        """获取已安装应用列表（Windows注册表）"""
        if not winreg or not DebugMgr.is_windows():
            return ["winreg库不可用或非Windows系统，无法获取已安装应用"]
        
        apps = []
        try:
            # 检查64位应用
            uninstall_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, uninstall_key) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, subkey_name) as subkey:
                            try:
                                display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                                try:
                                    display_version = winreg.QueryValueEx(subkey, "DisplayVersion")[0]
                                except FileNotFoundError:
                                    display_version = "未知版本"
                                apps.append(f"{display_name} - {display_version}")
                            except FileNotFoundError:
                                continue
                    except Exception:
                        continue
            
            # 检查32位应用（在64位系统上）
            try:
                uninstall_key_32 = r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, uninstall_key_32) as key:
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, subkey_name) as subkey:
                                try:
                                    display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                                    try:
                                        display_version = winreg.QueryValueEx(subkey, "DisplayVersion")[0]
                                    except FileNotFoundError:
                                        display_version = "未知版本"
                                    apps.append(f"{display_name} - {display_version} (32位)")
                                except FileNotFoundError:
                                    continue
                        except Exception:
                            continue
            except FileNotFoundError:
                pass  # 32位注册表项不存在（可能是32位系统）
                
        except Exception as e:
            apps.append(f"获取已安装应用时出错: {str(e)}")
        
        return apps
    
    @staticmethod
    def get_system_info():
        """获取系统信息"""
        info = {}
        try:
            # 基本系统信息
            info['操作系统'] = platform.system()
            info['系统版本'] = platform.version()
            info['系统发行版'] = platform.release()
            info['CPU架构'] = platform.machine()
            info['处理器'] = platform.processor()
            info['Python版本'] = platform.python_version()
            info['Python架构'] = platform.architecture()[0]
            
            # 用户和计算机信息
            info['用户名'] = getpass.getuser()
            info['计算机名'] = platform.node()
            
            # 网络信息
            try:
                hostname = socket.gethostname()
                info['主机名'] = hostname
                info['IP地址'] = _get_my_ip()
            except Exception as e:
                info['网络信息错误'] = str(e)
            
            # Windows特定信息
            if DebugMgr.is_windows():
                try:
                    # 获取制造商和型号信息
                    result = subprocess.run(['wmic', 'computersystem', 'get', 'manufacturer,model', '/format:csv'], 
                                          capture_output=True, text=True, timeout=10)
                    if result.returncode == 0:
                        lines = result.stdout.strip().split('\n')
                        for line in lines[1:]:  # 跳过标题行
                            if line.strip() and ',' in line:
                                parts = line.split(',')
                                if len(parts) >= 3:
                                    info['制造商'] = parts[1].strip()
                                    info['机器型号'] = parts[2].strip()
                                    break
                except Exception as e:
                    info['制造商信息错误'] = str(e)
                
                try:
                    # 获取BIOS信息
                    result = subprocess.run(['wmic', 'bios', 'get', 'version', '/format:csv'], 
                                          capture_output=True, text=True, timeout=10)
                    if result.returncode == 0:
                        lines = result.stdout.strip().split('\n')
                        for line in lines[1:]:
                            if line.strip() and ',' in line:
                                parts = line.split(',')
                                if len(parts) >= 2:
                                    info['BIOS版本'] = parts[1].strip()
                                    break
                except Exception as e:
                    info['BIOS信息错误'] = str(e)
            
            return info
        except Exception as e:
            info['系统信息获取错误'] = str(e)
            return info
    
    @staticmethod
    def get_proxy_info():
        """获取Windows代理信息，包括HTTPS代理和TUN模式代理"""
        if not DebugMgr.is_windows():
            return {"错误": "仅支持Windows系统"}
        
        proxy_info = {}
        
        try:
            # 1. 检查系统代理设置（注册表）
            if winreg:
                try:
                    # 打开Internet Settings注册表项
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                                       r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
                    
                    # 检查代理是否启用
                    try:
                        proxy_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
                        proxy_info['系统代理启用'] = bool(proxy_enable)
                    except FileNotFoundError:
                        proxy_info['系统代理启用'] = False
                    
                    # 获取代理服务器地址
                    try:
                        proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
                        proxy_info['代理服务器'] = proxy_server
                    except FileNotFoundError:
                        proxy_info['代理服务器'] = "未设置"
                    
                    # 获取代理覆盖（不使用代理的地址）
                    try:
                        proxy_override, _ = winreg.QueryValueEx(key, "ProxyOverride")
                        proxy_info['代理例外'] = proxy_override
                    except FileNotFoundError:
                        proxy_info['代理例外'] = "未设置"
                    
                    # 检查自动配置脚本
                    try:
                        auto_config_url, _ = winreg.QueryValueEx(key, "AutoConfigURL")
                        proxy_info['自动配置脚本'] = auto_config_url
                    except FileNotFoundError:
                        proxy_info['自动配置脚本'] = "未设置"
                    
                    winreg.CloseKey(key)
                    
                except Exception as e:
                    proxy_info['注册表读取错误'] = str(e)
            
            # 2. 检查环境变量代理
            env_proxies = {}
            for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'FTP_PROXY', 'ALL_PROXY', 'NO_PROXY']:
                value = os.environ.get(proxy_var) or os.environ.get(proxy_var.lower())
                if value:
                    env_proxies[proxy_var] = value
            
            if env_proxies:
                proxy_info['环境变量代理'] = env_proxies
            else:
                proxy_info['环境变量代理'] = "未设置"
            
            # 3. 检测TUN模式代理（通过网络适配器）
            tun_adapters = []
            if psutil:
                try:
                    # 获取网络接口信息
                    interfaces = psutil.net_if_addrs()
                    stats = psutil.net_if_stats()
                    
                    for interface_name, addresses in interfaces.items():
                        # 检查是否为TUN/TAP适配器
                        interface_lower = interface_name.lower()
                        if any(keyword in interface_lower for keyword in 
                               ['tun', 'tap', 'wintun', 'wireguard', 'openvpn', 'clash', 'v2ray', 'shadowsocks']):
                            
                            adapter_info = {
                                '名称': interface_name,
                                '状态': 'UP' if stats.get(interface_name, {}).isup else 'DOWN',
                                '地址': []
                            }
                            
                            for addr in addresses:
                                if addr.family == socket.AF_INET:  # IPv4
                                    adapter_info['地址'].append(f"IPv4: {addr.address}")
                                elif addr.family == socket.AF_INET6:  # IPv6
                                    adapter_info['地址'].append(f"IPv6: {addr.address}")
                            
                            tun_adapters.append(adapter_info)
                    
                    proxy_info['TUN模式适配器'] = tun_adapters if tun_adapters else "未检测到"
                    
                except Exception as e:
                    proxy_info['TUN适配器检测错误'] = str(e)
            
            # 4. 检查常见代理软件进程
            proxy_processes = []
            if psutil:
                try:
                    proxy_keywords = ['clash', 'v2ray', 'shadowsocks', 'proxifier', 'fiddler', 
                                    'charles', 'burp', 'mitmproxy', 'squid', 'privoxy']
                    
                    for proc in psutil.process_iter(['pid', 'name', 'exe']):
                        try:
                            proc_name = proc.info['name'].lower() if proc.info['name'] else ''
                            proc_exe = proc.info['exe'].lower() if proc.info['exe'] else ''
                            
                            for keyword in proxy_keywords:
                                if keyword in proc_name or keyword in proc_exe:
                                    proxy_processes.append({
                                        'PID': proc.info['pid'],
                                        '进程名': proc.info['name'],
                                        '路径': proc.info['exe'] or '未知'
                                    })
                                    break
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                    
                    proxy_info['代理软件进程'] = proxy_processes if proxy_processes else "未检测到"
                    
                except Exception as e:
                    proxy_info['进程检测错误'] = str(e)
            
            # 5. 检查网络连接（代理端口）
            proxy_connections = []
            if psutil:
                try:
                    # 常见代理端口
                    proxy_ports = [1080, 7890, 7891, 8080, 8081, 8888, 9090, 10809, 10810]
                    
                    connections = psutil.net_connections(kind='inet')
                    for conn in connections:
                        if conn.laddr and conn.laddr.port in proxy_ports and conn.status == 'LISTEN':
                            try:
                                proc = psutil.Process(conn.pid) if conn.pid else None
                                proxy_connections.append({
                                    '端口': conn.laddr.port,
                                    '地址': conn.laddr.ip,
                                    '进程': proc.name() if proc else '未知',
                                    'PID': conn.pid or '未知'
                                })
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                proxy_connections.append({
                                    '端口': conn.laddr.port,
                                    '地址': conn.laddr.ip,
                                    '进程': '未知',
                                    'PID': conn.pid or '未知'
                                })
                    
                    proxy_info['代理端口监听'] = proxy_connections if proxy_connections else "未检测到"
                    
                except Exception as e:
                    proxy_info['端口检测错误'] = str(e)
            
        except Exception as e:
            proxy_info['检测错误'] = str(e)
        
        return proxy_info
    
    @staticmethod
    def get_memory_info():
        """获取内存信息"""
        memory_info = {}
        
        try:
            # 内存信息
            if psutil:
                try:
                    memory = psutil.virtual_memory()
                    memory_info['总内存'] = f"{round(memory.total / 1024 / 1024 / 1024, 2)} GB"
                    memory_info['可用内存'] = f"{round(memory.available / 1024 / 1024 / 1024, 2)} GB"
                    memory_info['内存使用率'] = f"{memory.percent}%"
                except Exception as e:
                    memory_info['内存信息错误'] = str(e)
            else:
                memory_info['错误'] = 'psutil模块未安装'
        except Exception as e:
            memory_info['系统信息获取错误'] = str(e)
        
        return memory_info
    
    @staticmethod
    def export_debug_info():
        """导出调试信息到日志文件"""
        if not DebugMgr.is_windows():
            print("警告: debugmgr仅支持Windows系统")
            return False
        
        logger = setup_logger()
        
        try:
            logger.info("=" * 80)
            logger.info(f"调试信息导出开始 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 80)
            
            # 导出系统信息
            logger.info("[系统信息]")
            system_info = DebugMgr.get_system_info()
            for key, value in system_info.items():
                logger.info(f"{key}: {value}")
            
            # 导出进程列表
            logger.info("\n[当前进程列表]")
            processes = DebugMgr.get_process_list()
            if isinstance(processes, list) and len(processes) > 0:
                if isinstance(processes[0], dict):
                    logger.info(f"共找到 {len(processes)} 个进程:")
                    for proc in processes:
                        logger.info(f"PID: {proc['pid']}, 名称: {proc['name']}, 内存: {proc['memory_mb']}MB, CPU: {proc['cpu_percent']}%")

                else:
                    for proc in processes:
                        logger.info(proc)
            
            # 导出已安装应用
            logger.info("\n[已安装应用列表]")
            apps = DebugMgr.get_installed_apps()
            if isinstance(apps, list) and len(apps) > 0:
                if isinstance(apps[0], str) and not apps[0].startswith("winreg"):
                    logger.info(f"共找到 {len(apps)} 个已安装应用:")
                    for app in apps:
                        logger.info(f"应用: {app}")
                else:
                    for app in apps:
                        logger.info(app)
            
            # 导出代理信息
            logger.info("\n[代理信息]")
            proxy_info = DebugMgr.get_proxy_info()
            for key, value in proxy_info.items():
                if isinstance(value, list):
                    logger.info(f"{key}:")
                    if value:
                        for item in value:
                            if isinstance(item, dict):
                                logger.info(f"  - {item}")
                            else:
                                logger.info(f"  - {item}")
                    else:
                        logger.info(f"  未检测到")
                elif isinstance(value, dict):
                    logger.info(f"{key}:")
                    for sub_key, sub_value in value.items():
                        logger.info(f"  {sub_key}: {sub_value}")
                else:
                    logger.info(f"{key}: {value}")
            
            logger.info("=" * 80)
            logger.info(f"调试信息导出完成 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 80)
            
            return True
            
        except Exception as e:
            logger.error(f"导出调试信息时发生错误: {str(e)}")
            return False
    
    @staticmethod
    def export_debug_info_json(file_path=None):
        """导出调试信息到JSON文件"""
        if not DebugMgr.is_windows():
            print("警告: debugmgr仅支持Windows系统")
            return False
        
        if not file_path:
            file_path = f"debug_info_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        try:
            debug_data = {
                'export_time': datetime.now().isoformat(),
                'system_info': DebugMgr.get_system_info(),
                'processes': DebugMgr.get_process_list(),
                'installed_apps': DebugMgr.get_installed_apps(),
                'proxy_info': DebugMgr.get_proxy_info()
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(debug_data, f, ensure_ascii=False, indent=2)
            
            print(f"调试信息已导出到: {file_path}")
            return True
            
        except Exception as e:
            print(f"导出JSON调试信息时发生错误: {str(e)}")
            return False


if __name__ == "__main__":

    DebugMgr.export_debug_info()

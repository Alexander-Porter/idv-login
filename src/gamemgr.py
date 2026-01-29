# coding=UTF-8
"""
 Copyright (c) 2025 Alexander-Porter & fwilliamhe

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
import ctypes
import hashlib
import os
import json
import subprocess
import sys
import time
import winreg
import base64
import shutil
from typing import Dict, List, Optional, Tuple
import xxhash
from channelHandler.channelUtils import getShortGameId
from cloudRes import CloudRes
from envmgr import genv
from logutil import setup_logger

def calculate_xxh64(file_path):
    h = xxhash.xxh64() # 初始化 64位 对象
    with open(file_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()

class Game:
    def __init__(
        self,
        game_id: str,
        name: str = "",
        path: str = "",
        should_auto_start: bool = False,
        auto_close_after_login: bool = False,
        login_delay: int = 6,
        last_used_time: int = 0,
        version: str = "",
        default_distribution: int = -1,
    ) -> None:
        self.game_id = game_id
        self.name = name if name else game_id
        if sys.platform == "win32" and isinstance(path, str):
            self.path = path.replace("\\", "/")
        else:
            self.path = path
        self.should_auto_start = should_auto_start
        self.auto_close_after_login = auto_close_after_login
        self.login_delay = login_delay
        self.last_used_time = last_used_time or int(time.time())
        self.logger = setup_logger()
        self.version = version
        self.default_distribution = default_distribution
        self.last_update_async = False

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            game_id=data.get("game_id", ""),
            name=data.get("name", ""),
            path=data.get("path", ""),
            should_auto_start=data.get("should_auto_start", False),
            auto_close_after_login=data.get("auto_close_after_login", True),
            last_used_time=data.get("last_used_time", int(time.time())),
            login_delay=data.get("login_delay", 6),
            version=data.get("version", ""),
            default_distribution=data.get("default_distribution", -1)
        )

    def to_dict(self) -> dict:
        return {
            "game_id": self.game_id,
            "name": self.name,
            "path": self.path,
            "should_auto_start": self.should_auto_start,
            "auto_close_after_login": self.auto_close_after_login,
            "last_used_time": self.last_used_time,
            "login_delay": self.login_delay,
            "version": self.version,
            "default_distribution": self.default_distribution
        }

    def get_non_sensitive_data(self) -> dict:
        return {
            "game_id": self.game_id,
            "name": self.name,
            "last_used_time": self.last_used_time,
            "should_auto_start": self.should_auto_start,
            "path": self.path
        }

    def start(self):
        game_path = self.path
        if not game_path or not os.path.exists(game_path):
            self.logger.error(f"游戏路径无效或不存在: {game_path}")
            return False
        if sys.platform == "win32":
            # 规范化路径
            game_path = os.path.normpath(game_path)
            game_dir = os.path.dirname(game_path)
            
            # 设置进程的工作目录为游戏所在目录
            startupinfo = subprocess.STARTUPINFO()
            # 隐藏命令行窗口
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 1  # SW_SHOWNORMAL
            
            # 设置环境变量，模拟资源管理器启动
            env = os.environ.copy()
            env['COMSPEC'] = os.environ.get('COMSPEC', '%SystemRoot%\\system32\\cmd.exe')
            env['SYSTEMROOT'] = os.environ.get('SYSTEMROOT', '%SystemRoot%')
            
            try:
                import ctypes
                SEE_MASK_NOCLOSEPROCESS = 0x00000040
                SEE_MASK_NOASYNC = 0x00000100
                
                class SHELLEXECUTEINFO(ctypes.Structure):
                    _fields_ = [
                        ("cbSize", ctypes.c_uint32),
                        ("fMask", ctypes.c_ulong),
                        ("hwnd", ctypes.c_void_p),
                        ("lpVerb", ctypes.c_wchar_p),
                        ("lpFile", ctypes.c_wchar_p),
                        ("lpParameters", ctypes.c_wchar_p),
                        ("lpDirectory", ctypes.c_wchar_p),
                        ("nShow", ctypes.c_int),
                        ("hInstApp", ctypes.c_void_p),
                        ("lpIDList", ctypes.c_void_p),
                        ("lpClass", ctypes.c_wchar_p),
                        ("hkeyClass", ctypes.c_void_p),
                        ("dwHotKey", ctypes.c_uint32),
                        ("hIcon", ctypes.c_void_p),
                        ("hProcess", ctypes.c_void_p)
                    ]

                shell_info = SHELLEXECUTEINFO()
                shell_info.cbSize = ctypes.sizeof(shell_info)
                shell_info.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NOASYNC
                shell_info.lpVerb = "open"
                shell_info.lpFile = game_path
                shell_info.lpDirectory = game_dir
                shell_info.nShow = 1  # SW_SHOWNORMAL
                
                shell32 = ctypes.WinDLL('shell32.dll')
                result = shell32.ShellExecuteExW(ctypes.byref(shell_info))
                
                if not result:
                    # 如果ShellExecuteEx失败，回退到使用subprocess
                    self.logger.warning("ShellExecuteEx启动失败，尝试使用subprocess作为备选方案")
                    subprocess.Popen(
                        game_path,
                        cwd=game_dir,
                        env=env,
                        shell=False,
                        startupinfo=startupinfo
                    )
                else:
                    self.logger.info(f"成功使用ShellExecuteEx启动游戏: {game_path}")
            except Exception as e:
                self.logger.exception(f"ShellExecuteEx启动失败: {str(e)}")
                # 回退到原始方法
                subprocess.Popen(
                    game_path,
                    cwd=game_dir,
                    env=env,
                    shell=False,
                    startupinfo=startupinfo
                )
        else:
            pass

    def get_root_path(self) -> str:
        """获取游戏根目录"""
        if not self.path:
            return ""
        return os.path.dirname(self.path)
    
    def _normalize_distribution_ids(self, distributions: List) -> List[int]:
        result = []
        for dist in distributions:
            dist_id = None
            if isinstance(dist, dict):
                dist_id = dist.get("distribution_id")
                if dist_id is None:
                    dist_id = dist.get("app_id")
            else:
                dist_id = dist
            if dist_id is None:
                continue
            try:
                result.append(int(dist_id))
            except (TypeError, ValueError):
                continue
        return result

    def get_distributions(self) -> List[int]:
        """获取游戏可用的分发ID列表"""
        cloud_res = CloudRes()
        short_game_id = getShortGameId(self.game_id)
        distributions = cloud_res.get_download_distributions(short_game_id)
        return self._normalize_distribution_ids(distributions)
        
    def get_launcher_data_for_distribution(self, distribution_id: int) -> Optional[dict]:
        """获取指定分发ID的启动器数据"""
        cloud_res = CloudRes()
        short_game_id = getShortGameId(self.game_id)
        distributions = cloud_res.get_download_distributions(short_game_id)
        distribution_ids = self._normalize_distribution_ids(distributions)
        if distribution_ids and distribution_id not in distribution_ids:
            return None
        import requests
        try:
            url=f"https://loadingbaycn.webapp.163.com/app/v1/game_library/app?force=1&app_id={distribution_id}"
            headers={
                "User-Agent": "",
            }
            response=requests.get(url,headers=headers,timeout=10)
            if response.status_code!=200 or response.json().get("code")!=200:
                self.logger.error(f"请求启动器信息失败，状态码: {response.status_code}")
                return None
            return response.json().get("data", {})
        except Exception as e:
            self.logger.exception(f"请求启动器信息失败: {str(e)}")
        return None
    
    def get_file_distribution_info(self, distribution_id: int) -> Optional[dict]:
        """获取指定分发ID的文件分发信息"""
        try:
            #https://loadingbaycn.webapp.163.com/app/v1/file_distribution/download_app?app_id=
            import requests
            url=f"https://loadingbaycn.webapp.163.com/app/v1/file_distribution/download_app?app_id={distribution_id}"
            headers={
                "User-Agent": "",
            }
            response=requests.get(url,headers=headers,timeout=10)
            if response.status_code!=200 or response.json().get("code")!=200:
                return None
            return response.json().get("data", {}).get("main_content", {})
        except Exception as e:
            self.logger.exception(f"请求文件分发信息失败: {str(e)}")
            return None
            
    def try_update(self, distribution_id: int, max_concurrent_files: int) -> bool:
        """尝试将游戏更新到指定分发ID的版本"""
        self.last_update_async = False
        download_root = self.get_root_path()
        if not download_root or not os.path.exists(download_root):
            self.logger.error(f"游戏路径无效或不存在: {self.path if self else '未设置'}")
            return False
        file_distribution_info = self.get_file_distribution_info(distribution_id)
        if not file_distribution_info:
            self.logger.error(f"未找到分发ID {distribution_id} 的文件分发信息")
            return False
        files = file_distribution_info.get("files", [])
        directories = file_distribution_info.get("directories", [])
        check_result, to_update = self.version_check(files)
        if check_result:
            self.logger.info(f"游戏已是最新版本，无需更新")
            return True
        if not to_update:
            self.version = file_distribution_info.get("version_code", self.version)
            return True
        

        task_data = {
            "download_root": download_root,
            "concurrent_files": max_concurrent_files,
            "directories": directories,
            "files": to_update,
            "version_code": file_distribution_info.get("version_code", self.version),
            "game_id": self.game_id,
            "distribution_id": distribution_id,
            "content_id":file_distribution_info.get("app_content_id"),
            "convert_to_normal": self.can_convert_to_normal()
        }
        task_file_path = self._create_download_task_file(task_data)
        if not task_file_path:
            self.logger.error("创建下载任务文件失败")
            return False
        if not self._spawn_download_process(task_file_path):
            self.logger.error("启动下载子进程失败")
            return False
        self.last_update_async = True
        return True

    def _create_download_task_file(self, task_data: dict) -> Optional[str]:
        try:
            workdir = genv.get("FP_WORKDIR", os.getcwd())
            os.makedirs(workdir, exist_ok=True)
            token = base64.urlsafe_b64encode(os.urandom(6)).decode("utf-8").rstrip("=")
            filename = f"download_task_{self.game_id}_{int(time.time())}_{token}.json"
            task_file_path = os.path.join(workdir, filename)
            with open(task_file_path, "w", encoding="utf-8") as f:
                json.dump(task_data, f, ensure_ascii=False)
            return task_file_path
        except Exception as e:
            self.logger.exception(f"创建下载任务文件失败: {e}")
            return None

    def _spawn_download_process(self, task_file_path: str) -> bool:
        try:
            if getattr(sys, 'frozen', False):
                # 如果是PyInstaller打包的exe文件，使用sys.argv[0]
                executable = sys.argv[0]
            else:
                # 如果是Python脚本，使用sys.executable
                executable = sys.executable
            if getattr(sys, 'frozen', False):
                # exe文件：只传递从argv[1]开始的参数
                args = sys.argv[1:] if len(sys.argv) > 1 else []
                argvs = [f'"{arg}"' for arg in args]
            else:
                # Python脚本：需要传递完整的argv
                args = sys.argv
                argvs = [f'"{i}"' for i in sys.argv]
            args.append("--download")
            args.append(task_file_path)
            argvs = [f'"{arg}"' for arg in args]
            script_dir = genv.get("SCRIPT_DIR", os.path.dirname(os.path.abspath(__file__)))
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", executable, " ".join(argvs), script_dir, 1
            )
            return True
        except Exception as e:
            self.logger.exception(f"启动下载子进程失败: {e}")
            return False
    def need_update(self, distribution_id: int) -> bool:
        """检查游戏是否需要更新到指定分发ID的版本"""
        if not self.path or not os.path.exists(self.path):
            return False
        if not CloudRes().is_downloadable(getShortGameId(self.game_id)):
            return False
        file_distribution_info = self.get_file_distribution_info(distribution_id)
        if not file_distribution_info:
            self.logger.error(f"未找到分发ID {distribution_id} 的文件分发信息")
            return False
        files = file_distribution_info.get("files", [])
        check_result, to_update = self.version_check(files)
        return not check_result
    

    def version_check(self,files: List[dict]) -> Tuple[bool, List[dict]]:
        """检查游戏版本是否匹配, 返回需要更新的文件列表"""
        if not self.get_root_path() or not os.path.exists(self.get_root_path()):
            return False, files
        to_update = []
        for file_info in files:
            #file_info中的是相对路径
            if file_info.get("op",1)!=1:
                continue
            file_path = os.path.join(self.get_root_path(), file_info.get("path", ""))
            if not os.path.exists(file_path):
                to_update.append(file_info)
                continue
            #计算xxh64值
            local_xxh64 = calculate_xxh64(file_path)
            if local_xxh64 != file_info.get("xxh", ""):
                to_update.append(file_info)
        return len(to_update) == 0, to_update

    def _extract_file_size(self, file_info: dict) -> int:
        for key in ["size", "file_size", "filesize", "length", "fileSize"]:
            value = file_info.get(key)
            if isinstance(value, (int, float)) and value >= 0:
                return int(value)
            if isinstance(value, str):
                try:
                    return int(value)
                except ValueError:
                    continue
        return 0

    def get_update_stats(self, distribution_id: int) -> Optional[dict]:
        download_root = self.get_root_path()
        if not download_root or not os.path.exists(download_root):
            return None
        file_distribution_info = self.get_file_distribution_info(distribution_id)
        if not file_distribution_info:
            return None
        files = file_distribution_info.get("files", [])
        check_result, to_update = self.version_check(files)
        to_update = [item for item in to_update if item.get("url", "") != ""]
        download_bytes = sum(self._extract_file_size(item) for item in to_update)
        usage = shutil.disk_usage(download_root)
        return {
            "needs_update": not check_result,
            "download_bytes": download_bytes,
            "file_count": len(to_update),
            "disk_free_bytes": usage.free,
            "disk_total_bytes": usage.total,
            "target_version": file_distribution_info.get("version_code", "")
        }

    def convert_to_normal(self) -> bool:
        """将Fever版本转换为普通版本"""
        cloud_res = CloudRes()
        short_game_id = getShortGameId(self.game_id)
        if not cloud_res.is_convert_to_normal(short_game_id):
            self.logger.info(f"游戏 {self.game_id} 不需要转换")
            return False
        #检查游戏exe同目录下的pack_config.xml文件，将其更名为pack_config.xml.bak
        if not self.path or not os.path.exists(self.path):
            self.logger.error(f"游戏路径无效或不存在: {self.path if self else '未设置'}")
            return False
        game_dir=os.path.dirname(self.path)
        pack_config_path=os.path.join(game_dir,"pack_config.xml")
        if os.path.exists(pack_config_path):
            bak_path=pack_config_path+".bak"
            if os.path.exists(bak_path):
                try:
                    os.remove(bak_path)
                except Exception as e:
                    self.logger.exception(f"删除备份文件失败: {str(e)}")
                    return False
            try:
                os.rename(pack_config_path,bak_path)
                self.logger.info(f"成功将 {pack_config_path} 重命名为 {bak_path}")
                return True
            except Exception as e:
                self.logger.exception(f"重命名文件失败: {str(e)}")
                return False
        else:
            self.logger.error(f"未找到需要转换的文件: {pack_config_path}")
            return False
        
    def is_downloadable_fever(self) -> bool:
        """检查游戏是否有Fever版本可供下载"""
        cloud_res = CloudRes()
        short_game_id = getShortGameId(self.game_id)
        return cloud_res.is_downloadable(short_game_id)
    
    def get_distribution_options(self) -> List[dict]:
        """获取游戏的分发选项"""
        cloud_res = CloudRes()
        short_game_id = getShortGameId(self.game_id)
        return cloud_res.get_download_distributions(short_game_id)
    
    def get_default_distribution(self) -> int:
        """获取游戏的默认分发ID"""
        return self.default_distribution
    def set_default_distribution(self, distribution_id: int=-1) -> None:
        """设置游戏的默认分发ID"""
        if distribution_id==-1:
            distributions = self.get_distributions()
            if distributions:
                self.default_distribution = distributions[0]
            else:
                self.default_distribution = -1
        else:
            self.default_distribution = distribution_id
    
    def get_version(self) -> str:
        """获取游戏版本号"""
        return self.version
    
    def is_fever(self)-> bool:
        """检查游戏是否为Fever版本"""
        if not self.path or not os.path.exists(self.path):
            self.logger.error(f"游戏路径无效或不存在: {self.path if self else '未设置'}")
            return False
        game_dir=os.path.dirname(self.path)
        pack_config_path=os.path.join(game_dir,"pack_config.xml")
        return os.path.exists(pack_config_path)
    
    def can_convert_to_normal(self) -> bool:
        """检查游戏是否可以转换为普通版本"""
        cloud_res = CloudRes()
        short_game_id = getShortGameId(self.game_id)
        print(f"检查游戏 {self.game_id} 是否可以转换为普通版本: {cloud_res.is_convert_to_normal(short_game_id)}")
        return cloud_res.is_convert_to_normal(short_game_id) and self.is_fever()
    

class GameManager:
    GAMES_CACHE_KEY = "game_settings"
    
    def __init__(self):
        self.logger = setup_logger()
        self.games: Dict[str, Game] = {}
        self._load_games()

    def _load_games(self):
        """从缓存中加载游戏设置"""
        try:
            game_settings = genv.get(self.GAMES_CACHE_KEY, {})
            if game_settings and isinstance(game_settings, dict):
                for game_id, game_data in game_settings.items():
                    self.games[game_id] = Game.from_dict(game_data)
        except Exception as e:
            self.logger.exception(f"加载游戏设置失败: {str(e)}")
            # 初始化空数据以恢复
            genv.set(self.GAMES_CACHE_KEY, {}, cached=True)

    def _save_games(self):
        """保存游戏设置到缓存"""
        try:
            game_settings = {game_id: game.to_dict() for game_id, game in self.games.items()}
            genv.set(self.GAMES_CACHE_KEY, game_settings, cached=True)
        except Exception as e:
            self.logger.exception(f"保存游戏设置失败: {str(e)}")

    def get_game(self, game_id: str) -> Optional[Game]:
        """获取指定游戏ID的游戏信息"""
        if not game_id:
            return None
        #检查后缀的三个字符是否匹配
        if game_id not in self.games:
            for key in self.games.keys():
                common_len = 0
                for a, b in zip(reversed(game_id), reversed(key)):
                    if a == b:
                        common_len += 1
                    else:
                        break
                if common_len >= 3:
                    return self.games.get(key)
        # 如果游戏ID不存在，则创建一个新的游戏记录
        if game_id not in self.games:
            self.games[game_id] = Game(game_id=game_id)
            self._save_games()
            
        return self.games.get(game_id)

    def get_existing_game(self, game_id: str) -> Optional[Game]:
        if not game_id:
            return None
        if game_id in self.games:
            return self.games.get(game_id)
        for key in self.games.keys():
            common_len = 0
            for a, b in zip(reversed(game_id), reversed(key)):
                if a == b:
                    common_len += 1
                else:
                    break
            if common_len >= 3:
                return self.games.get(key)
        return None

    def get_game_or_temp(self, game_id: str) -> Optional[Game]:
        game = self.get_existing_game(game_id)
        if game:
            return game
        return Game(game_id=game_id)

    def list_games(self) -> List[dict]:
        """列出所有已保存的游戏信息"""
        return sorted(
            [game.get_non_sensitive_data() for game in self.games.values()],
            key=lambda x: x["last_used_time"],
            reverse=True
        )

    def set_game_path(self, game_id: str, path: str) -> bool:
        """设置游戏路径"""
        if not game_id:
            return False
            
        game = self.get_game(game_id)
        if game:
            game.path = path
            game.last_used_time = int(time.time())
            self._save_games()
            return True
        return False

    def set_game_auto_start(self, game_id: str, should_auto_start: bool) -> bool:
        """设置是否自动启动游戏"""
        if not game_id:
            return False
            
        game = self.get_game(game_id)
        if game:
            game.should_auto_start = should_auto_start
            game.last_used_time = int(time.time())
            self._save_games()
            return True
        return False

    def get_game_auto_start(self, game_id: str) -> dict:
        """获取游戏自动启动设置"""
        game = self.get_game(game_id)
        if game:
            return {
                "enabled": game.should_auto_start,
                "path": game.path
            }
        return {"enabled": False, "path": ""}

    def start_game(self, game_id: str) -> bool:
        """启动游戏"""
        game = self.get_game(game_id)
        if not game or not game.path or not os.path.exists(game.path):
            self.logger.error(f"游戏路径无效或不存在: {game.path if game else '未设置'}")
            return False
            
        try:
            subprocess.Popen(game.path, shell=True)
            game.last_used_time = int(time.time())
            self._save_games()
            self.logger.info(f"游戏 {game_id} 启动成功")
            return True
        except Exception as e:
            self.logger.exception(f"启动游戏失败: {str(e)}")
            return False

    def rename_game(self, game_id: str, new_name: str) -> bool:
        """重命名游戏"""
        if not game_id or not new_name:
            return False
            
        game = self.get_game(game_id)
        if game:
            game.name = new_name
            game.last_used_time = int(time.time())
            self._save_games()
            return True
        return False

    def set_game_default_distribution(self, game_id: str, distribution_id: int) -> bool:
        if not game_id:
            return False
        game = self.get_game(game_id)
        if game:
            game.set_default_distribution(distribution_id)
            game.last_used_time = int(time.time())
            self._save_games()
            return True
        return False

    def set_auto_close_setting(self, game_id: str, auto_close: bool) -> bool:
        """设置登录后是否自动关闭工具"""
        if not game_id:
            return False
            
        game = self.get_game(game_id)
        if game:
            game.auto_close_after_login = auto_close
            game.last_used_time = int(time.time())
            self._save_games()
            return True
        return False
    
    def get_auto_close_setting(self, game_id: str) -> bool:
        """获取登录后是否自动关闭工具的设置"""
        game = self.get_game(game_id)
        if game:
            return game.auto_close_after_login
        return False

    def list_auto_start_games(self) -> List[Game]:
        """列出所有设置为自动启动的游戏"""
        return [game for game in self.games.values() if game.should_auto_start]
    
    def set_login_delay(self, game_id: str, delay: int) -> bool:
        """设置自动登录延迟时间"""
        if not game_id:
            return False
            
        game = self.get_game(game_id)
        if game:
            game.login_delay = delay
            game.last_used_time = int(time.time())
            self._save_games()
            return True
        return False
    
    def get_login_delay(self, game_id: str) -> int:
        """获取自动关闭延迟时间"""
        game = self.get_game(game_id)
        if game:
            return game.login_delay
        return 6

    def get_game_default_launcher_data(self, game_id: str) -> int:
        """获取游戏的默认启动器分发ID"""
        game = self.get_game(game_id)
        if game and game.default_distribution != -1:
            return game.get_launcher_data_for_distribution(game.default_distribution)
        return None
    
    def get_game_version(self, game_id: str) -> str:
        """获取游戏版本号"""
        game = self.get_game(game_id)
        if game:
            return game.get_version()
        return ""
    
    def get_game_distribution_options(self, game_id: str) -> List[dict]:
        """获取游戏的分发选项"""
        game = self.get_game(game_id)
        if game:
            return game.get_distribution_options()
        return []
    
    def get_game_launcher_data_for_distribution(self, game_id: str, distribution_id: int) -> Optional[dict]:
        """获取指定分发ID的启动器数据"""
        game = self.get_game(game_id)
        if game:
            return game.get_launcher_data_for_distribution(distribution_id)
        return None
    

    def list_fever_games(self) -> List[dict]:
        if sys.platform != "win32":
            return []
        result = []
        try:
            base_path = r"Software\FeverGames\FeverGamesInstaller\game"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base_path) as key:
                index = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, index)
                        subkey_path = f"{base_path}\\{subkey_name}"
                        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey_path) as subkey:
                            game_info_value = None
                            last_install_path = None
                            running_process_name = None
                            try:
                                game_info_value, _ = winreg.QueryValueEx(subkey, "GameInfo")
                            except FileNotFoundError:
                                pass
                            try:
                                last_install_path, _ = winreg.QueryValueEx(subkey, "LastInstallPath")
                            except FileNotFoundError:
                                pass
                            try:
                                running_process_name, _ = winreg.QueryValueEx(subkey, "RunningProcessName")
                            except FileNotFoundError:
                                pass
                            if not all([game_info_value, last_install_path, running_process_name]):
                                index += 1
                                continue
                            game_info_value = str(game_info_value)
                            if game_info_value.startswith("@ByteArray(") and game_info_value.endswith(")"):
                                game_info_value = game_info_value[11:-1]
                            decoded_bytes = base64.b64decode(game_info_value)
                            decoded_str = decoded_bytes.decode('utf-8')
                            game_info_json = json.loads(decoded_str)
                            game_id = game_info_json.get('game_id')
                            display_name = game_info_json.get('display_name')
                            if not game_id:
                                index += 1
                                continue
                            executable_path = os.path.join(last_install_path, running_process_name)
                            result.append({
                                "game_id": game_id,
                                "display_name": display_name,
                                "path": executable_path,
                                "distribution_id": int(subkey_name)
                            })
                            index += 1
                    except OSError:
                        break
        except Exception:
            self.logger.exception("读取Fever游戏列表失败")
        return result

    def import_fever_game(self, game_id: str) -> bool:
        if not game_id:
            return False
        fever_games = self.list_fever_games()
        target = None
        for item in fever_games:
            if item.get("game_id") == game_id:
                target = item
                break
        if not target:
            return False
        executable_path = target.get("path", "")
        if not executable_path:
            return False
        game = self.games.get(game_id)
        display_name = target.get("display_name")
        distribution_id = target.get("distribution_id", -1)
        if game:
            if display_name:
                game.name = display_name
            game.path = executable_path
            if distribution_id != -1:
                game.default_distribution = distribution_id
        else:
            game = Game(
                game_id=game_id,
                name=display_name if display_name else game_id,
                path=executable_path
            )
            if distribution_id != -1:
                game.default_distribution = distribution_id
            self.games[game_id] = game
        self._save_games()
        return True

    def import_from_fever(self):
        if sys.platform != "win32":
            return
        try:
            fever_games = self.list_fever_games()
            for item in fever_games:
                game_id = item.get("game_id")
                if not game_id:
                    continue
                executable_path = item.get("path", "")
                display_name = item.get("display_name")
                distribution_id = item.get("distribution_id", -1)
                game = self.games.get(game_id)
                if game:
                    if display_name:
                        game.name = display_name
                    game.path = executable_path
                    if distribution_id != -1:
                        game.default_distribution = distribution_id
                else:
                    game = Game(
                        game_id=game_id,
                        name=display_name if display_name else game_id,
                        path=executable_path
                    )
                    if distribution_id != -1:
                        game.default_distribution = distribution_id
                    self.games[game_id] = game
            self._save_games()
        except Exception:
            self.logger.exception("导入Fever游戏失败")
if __name__ == "__main__":
    game_mgr = GameManager()
    game_mgr.import_from_fever()
    game_mgr._save_games()
    g=game_mgr.get_game("h55")
    g.try_update(g.default_distribution,max_concurrent_files=1)
    

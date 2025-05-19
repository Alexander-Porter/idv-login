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

import os
import json
import subprocess
import sys
import time
from typing import Dict, List, Optional

from envmgr import genv
from logutil import setup_logger

class Game:
    def __init__(
        self,
        game_id: str,
        name: str = "",
        path: str = "",
        should_auto_start: bool = False,
        auto_close_after_login: bool = False,
        login_delay: int = 6,
        last_used_time: int = 0
    ) -> None:
        self.game_id = game_id
        self.name = name if name else game_id
        self.path = path
        self.should_auto_start = should_auto_start
        self.auto_close_after_login = auto_close_after_login
        self.login_delay = login_delay
        self.last_used_time = last_used_time or int(time.time())
        self.logger = setup_logger()

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            game_id=data.get("game_id", ""),
            name=data.get("name", ""),
            path=data.get("path", ""),
            should_auto_start=data.get("should_auto_start", False),
            auto_close_after_login=data.get("auto_close_after_login", True),
            last_used_time=data.get("last_used_time", int(time.time())),
            login_delay=data.get("login_delay", 6)
        )

    def to_dict(self) -> dict:
        return {
            "game_id": self.game_id,
            "name": self.name,
            "path": self.path,
            "should_auto_start": self.should_auto_start,
            "auto_close_after_login": self.auto_close_after_login,
            "last_used_time": self.last_used_time,
            "login_delay": self.login_delay
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
            
        # 如果游戏ID不存在，则创建一个新的游戏记录
        if game_id not in self.games:
            self.games[game_id] = Game(game_id=game_id)
            self._save_games()
            
        return self.games.get(game_id)

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
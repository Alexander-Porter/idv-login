# coding=UTF-8
"""
Copyright (c) 2026 Alexander-Porter

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


class LoginStackManager:
    _instance = None

    def __init__(self) -> None:
        self._cached_qrcode_data_stack = {}
        self._pending_login_info_stack = {}

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def reset(self):
        self._cached_qrcode_data_stack = {}
        self._pending_login_info_stack = {}

    def ensure_pending_stack(self, game_id):
        self._pending_login_info_stack.setdefault(game_id, [])

    def push_pending_login_info(self, game_id, process_id, login_info):
        stack = self._pending_login_info_stack.get(game_id, [])
        if process_id:
            stack = [item for item in stack if item.get("process_id") != process_id]
        stack.append({
            "process_id": process_id,
            "login_info": login_info,
        })
        self._pending_login_info_stack[game_id] = stack

    def pop_pending_login_info(self, game_id, process_id=None):
        stack = self._pending_login_info_stack.get(game_id, [])
        item = None
        if process_id:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i].get("process_id") == process_id:
                    item = stack.pop(i)
                    break
        elif stack:
            item = stack.pop()
        self._pending_login_info_stack[game_id] = stack
        return item["login_info"] if item else None

    def push_cached_qrcode_data(self, game_id, process_id, data):
        stack = self._cached_qrcode_data_stack.get(game_id, [])
        if process_id:
            stack = [item for item in stack if item.get("process_id") != process_id]
        stack.append({
            "process_id": process_id,
            "data": data,
        })
        self._cached_qrcode_data_stack[game_id] = stack

    def pop_cached_qrcode_data(self, game_id, process_id=None):
        stack = self._cached_qrcode_data_stack.get(game_id, [])
        item = None
        if process_id:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i].get("process_id") == process_id:
                    item = stack.pop(i)
                    break
        elif stack:
            item = stack.pop()
        self._cached_qrcode_data_stack[game_id] = stack
        return item["data"] if item else None

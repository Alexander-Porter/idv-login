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

import os
import sys
import time

from flask import request, jsonify, Response
from channelHandler.channelUtils import getShortGameId
from envmgr import genv
import const


def register_common_idv_routes(app, *, game_helper, logger):
    def _get_cached_qrcode_stacks():
        stacks = genv.get("cached_qrcode_data_stack", {})
        return stacks if isinstance(stacks, dict) else {}

    def _set_cached_qrcode_stacks(stacks):
        genv.set("cached_qrcode_data_stack", stacks)

    def _pop_cached_qrcode_data(game_id, process_id=None):
        stacks = _get_cached_qrcode_stacks()
        stack = stacks.get(game_id, [])
        item = None
        if process_id:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i].get("process_id") == process_id:
                    item = stack.pop(i)
                    break
        elif stack:
            item = stack.pop()
        stacks[game_id] = stack
        _set_cached_qrcode_stacks(stacks)
        return item["data"] if item else None
    @app.route("/_idv-login/manualChannels", methods=["GET"])
    def _manual_list():
        try:
            game_id = request.args["game_id"]
            if game_id:
                data = genv.get("CLOUD_RES").get_all_by_game_id(getShortGameId(game_id))
                return jsonify(data)
            else:
                return jsonify(const.manual_login_channels)
        finally:
            return jsonify(const.manual_login_channels)

    @app.route("/_idv-login/list", methods=["GET"])
    def _list_channels():
        try:
            body = genv.get("CHANNELS_HELPER").list_channels(request.args["game_id"])
        except Exception as e:
            body = {
                "error": str(e)
            }
        return jsonify(body)

    @app.route("/_idv-login/switch", methods=["GET"])
    def _switch_channel():
        genv.set("CHANNEL_ACCOUNT_SELECTED", request.args["uuid"])
        game_id = request.args.get("game_id", "")
        data = _pop_cached_qrcode_data(game_id) if game_id else None
        if data:
            genv.get("CHANNELS_HELPER").simulate_scan(request.args["uuid"], data["uuid"], data["game_id"])
        # debug only
        else:
            genv.get("CHANNELS_HELPER").simulate_scan(request.args["uuid"], "Kinich", "aecfrt3rmaaaaajl-g-g37")
        return {"current": genv.get("CHANNEL_ACCOUNT_SELECTED")}

    @app.route("/_idv-login/del", methods=["GET"])
    def _del_channel():
        resp = {
            "success": genv.get("CHANNELS_HELPER").delete(request.args["uuid"])
        }
        return jsonify(resp)

    @app.route("/_idv-login/rename", methods=["GET"])
    def _rename_channel():
        resp = {
            "success": genv.get("CHANNELS_HELPER").rename(request.args["uuid"], request.args["new_name"])
        }
        return jsonify(resp)

    @app.route("/_idv-login/import", methods=["GET"])
    def _import_channel():
        resp = {
            "success": genv.get("CHANNELS_HELPER").manual_import(request.args["channel"], request.args["game_id"])
        }
        return jsonify(resp)

    @app.route("/_idv-login/setDefault", methods=["GET"])
    def _set_default_channel():
        try:
            genv.set(f"auto-{request.args['game_id']}", request.args["uuid"], True)
            resp = {
                "success": True,
            }
        except Exception:
            logger.exception("设置默认账号失败")
            resp = {
                "success": False,
            }
        return jsonify(resp)

    @app.route("/_idv-login/clearDefault", methods=["GET"])
    def _clear_default_channel():
        try:
            genv.set(f"auto-{request.args['game_id']}", "", True)
            resp = {
                "success": True,
            }
        except Exception:
            resp = {
                "success": False,
            }
        return jsonify(resp)

    @app.route("/_idv-login/get-auto-close-state", methods=["GET"])
    def _get_auto_close_state():
        """查询指定游戏的自动关闭状态"""
        try:
            game_id = request.args["game_id"]
            current_state = game_helper.get_auto_close_setting(game_id)
            return jsonify({
                "success": True,
                "state": current_state,
                "game_id": game_id
            })
        except Exception as e:
            logger.exception(f"查询游戏 {game_id} 的自动关闭状态失败")
            return jsonify({
                "success": False,
                "error": str(e)
            })

    @app.route("/_idv-login/switch-auto-close-state", methods=["GET"])
    def _switch_auto_close_state():
        """切换指定游戏的自动关闭状态"""
        try:
            game_id = request.args["game_id"]
            current_state = game_helper.get_auto_close_setting(game_id)
            new_state = not current_state
            game_helper.set_auto_close_setting(game_id, new_state)
            return jsonify({
                "success": True,
                "state": new_state,
                "game_id": game_id
            })
        except Exception as e:
            logger.exception(f"切换游戏 {game_id} 的自动关闭状态失败")
            return jsonify({
                "success": False,
                "error": str(e)
            })

    @app.route("/_idv-login/get-game-auto-start", methods=["GET"])
    def _get_game_auto_start():
        """查询指定游戏的自动启动状态和路径"""
        try:
            game_id = request.args["game_id"]
            auto_start_info = game_helper.get_game_auto_start(game_id)
            return jsonify({
                "success": True,
                "enabled": auto_start_info["enabled"],
                "path": auto_start_info["path"],
                "game_id": game_id
            })
        except Exception as e:
            logger.exception(f"查询游戏 {game_id} 的自动启动状态失败")
            return jsonify({
                "success": False,
                "error": str(e)
            })

    @app.route("/_idv-login/set-game-auto-start", methods=["GET"])
    def _set_game_auto_start():
        """设置指定游戏的自动启动状态和路径"""
        try:
            game_id = request.args["game_id"]
            enabled = request.args.get("enabled") == 'true'

            game_path = ""

            if enabled:
                # 使用Qt代替tkinter
                from PyQt5.QtWidgets import QApplication, QFileDialog

                # 创建一个临时的QApplication实例
                app_inst = QApplication.instance()
                if app_inst is None:
                    app_inst = QApplication(sys.argv)

                # 导入Qt命名空间
                from PyQt5.QtCore import Qt

                # 显示文件选择对话框
                desktop_path = os.path.join(os.path.expanduser('~'), 'Desktop')
                file_dialog = QFileDialog()
                file_dialog.setFileMode(QFileDialog.ExistingFile)
                file_dialog.setNameFilter("可执行文件 (*.exe);;快捷方式 (*.lnk);;所有文件 (*.*)")
                file_dialog.setWindowTitle("选择游戏启动程序或快捷方式")
                file_dialog.setDirectory(desktop_path)
                file_dialog.setWindowFlags(file_dialog.windowFlags() | Qt.WindowStaysOnTopHint)
                file_dialog.setWindowModality(Qt.ApplicationModal)
                file_dialog.setWindowState(Qt.WindowActive)
                file_dialog.setWindowFlag(Qt.WindowStaysOnTopHint)
                if file_dialog.exec_():
                    selected_files = file_dialog.selectedFiles()
                    if selected_files:
                        game_path = selected_files[0]

                # 如果用户没有选择任何文件，则返回错误
                if not game_path:
                    return jsonify({
                        "success": False,
                        "error": "用户取消选择游戏路径"
                    })
                # 获取纯文件名，不含路径和后缀
                name = os.path.splitext(os.path.basename(game_path))[0]

                # 如果是快捷方式，解析目标路径
                if game_path.lower().endswith(".lnk"):
                    import win32com.client
                    shell = win32com.client.Dispatch("WScript.Shell")
                    shortcut = shell.CreateShortcut(game_path)
                    game_path = shortcut.Targetpath
            else:
                if game_helper.get_game(game_id):
                    name = game_helper.get_game(game_id).name
                else:
                    name = ""
            game_helper.set_game_auto_start(game_id, enabled)
            game_helper.set_game_path(game_id, game_path)
            game_helper.rename_game(game_id, name)
            return jsonify({
                "success": True,
                "enabled": enabled,
                "path": game_path,
                "game_id": game_id
            })
        except Exception as e:
            logger.exception(f"设置游戏 {game_id} 的自动启动状态失败")
            return jsonify({
                "success": False,
                "error": str(e)
            })

    @app.route("/_idv-login/start-game", methods=["GET"])
    def _start_game():
        """启动指定游戏"""
        try:
            game_id = request.args["game_id"]

            game_path = game_helper.get_game_auto_start(game_id)["path"]

            if not game_path:
                return jsonify({
                    "success": False,
                    "error": "游戏路径未设置"
                })

            game = game_helper.get_game(game_id)
            if game:
                game.start()
                game.last_used_time = int(time.time())
                game_helper._save_games()

            return jsonify({
                "success": True,
                "game_id": game_id
            })
        except Exception as e:
            logger.exception(f"启动游戏 {game_id} 失败")
            return jsonify({
                "success": False,
                "error": str(e)
            })

    @app.route("/_idv-login/list-games", methods=["GET"])
    def _list_games():
        """列出所有游戏"""
        try:
            games = game_helper.list_games()
            return jsonify({
                "success": True,
                "games": games
            })
        except Exception as e:
            logger.exception("列出游戏失败")
            return jsonify({
                "success": False,
                "error": str(e)
            })

    @app.route("/_idv-login/defaultChannel", methods=["GET"])
    def get_default():
        uuid = genv.get(f"auto-{request.args['game_id']}", "")
        if uuid == "":
            return jsonify({"uuid": ""})
        elif genv.get("CHANNELS_HELPER").query_channel(uuid) == None:
            genv.set(f"auto-{request.args['game_id']}", "", True)
            return jsonify({"uuid": ""})
        else:
            return jsonify({"uuid": uuid})

    @app.route("/_idv-login/get-login-delay", methods=["GET"])
    def get_login_delay():
        return jsonify({
            "delay": game_helper.get_login_delay(request.args["game_id"])
        })

    @app.route("/_idv-login/set-login-delay", methods=["GET"])
    def set_login_delay():
        try:
            game_helper.set_login_delay(request.args["game_id"], int(request.args["delay"]))
            return jsonify({
                "success": True
            })
        except Exception as e:
            logger.exception(f"设置游戏 {request.args['game_id']} 的登录延迟失败")
            return jsonify({
                "success": False,
                "error": str(e)
            })

    @app.route("/_idv-login/index", methods=['GET'])
    def _handle_switch_page():
        try:
            cloudRes = genv.get("CLOUD_RES")
            if cloudRes.get_login_page() == "":
                return Response(const.html)
            return Response(cloudRes.get_login_page())
        except Exception:
            return Response(const.html)

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
from cloudRes import CloudRes
from envmgr import genv
import const
from login_stack_mgr import LoginStackManager


def register_common_idv_routes(app, *, game_helper, logger):
    stack_mgr = LoginStackManager.get_instance()
    def _pick_launcher_fields(launcher_data):
        if not launcher_data:
            return {}
        keys = [
            "app_id",
            "app_name",
            "display_name",
            "logo",
            "icon",
            "main_image",
            "developer",
            "publisher",
            "version_code",
            "startup_path",
            "startup_params",
        ]
        return {key: launcher_data.get(key) for key in keys}

    @app.route("/_idv-login/manualChannels", methods=["GET"])
    def _manual_list():
        try:
            game_id = request.args["game_id"]
            if game_id:
                data = CloudRes().get_all_by_game_id(getShortGameId(game_id))
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
        data = stack_mgr.pop_cached_qrcode_data(game_id) if game_id else None
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
                from PyQt5.QtWidgets import QApplication, QFileDialog, QWidget

                # 创建一个临时的QApplication实例
                app_inst = QApplication.instance()
                if app_inst is None:
                    app_inst = QApplication(sys.argv)

                # 导入Qt命名空间
                from PyQt5.QtCore import Qt

                # 显示文件选择对话框
                dummy_parent = QWidget()
                dummy_parent.setWindowFlags(Qt.Tool)   # 不出现在任务栏
                dummy_parent.show()                    # 必须 show，OS 才承认它是窗口
                dummy_parent.hide()                    # 再藏起来给用户看不见

                desktop_path = os.path.join(os.path.expanduser('~'), 'Desktop')

                file_dialog = QFileDialog(dummy_parent)
                file_dialog.setFileMode(QFileDialog.ExistingFile)
                file_dialog.setNameFilter("可执行文件 (*.exe);;快捷方式 (*.lnk);;所有文件 (*.*)")
                file_dialog.setWindowTitle("选择游戏启动程序或快捷方式")
                file_dialog.setDirectory(desktop_path)

                file_dialog.show()
                file_dialog.raise_()
                file_dialog.activateWindow()

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

    @app.route("/_idv-login/launcher-status", methods=["GET"])
    def _launcher_status():
        try:
            game_id = request.args["game_id"]
            short_game_id = getShortGameId(game_id)
            game = game_helper.get_existing_game(game_id)
            game_for_remote = game_helper.get_game_or_temp(game_id)
            distribution_ids = game_for_remote.get_distributions()
            installed = bool(game and game.path and os.path.exists(game.path))
            can_convert = CloudRes().is_convert_to_normal(short_game_id)
            current_version = game.get_version() if game else ""
            default_distribution = game.get_default_distribution() if game else -1
            fever_info = None
            for item in game_helper.list_fever_games():
                if item.get("game_id") == getShortGameId(game_id):
                    fever_info = item
                    break
            can_import_fever = bool(fever_info) and (not game or not game.path or (fever_info.get("path") and fever_info.get("path") != game.path))
            distributions = []
            for dist_id in distribution_ids:
                launcher_data = game_for_remote.get_launcher_data_for_distribution(dist_id)
                file_info = game_for_remote.get_file_distribution_info(dist_id)
                target_version = file_info.get("version_code", "") if file_info else ""
                can_download = CloudRes().is_downloadable(short_game_id) and file_info is not None
                can_update = bool(installed)
                distributions.append({
                    "distribution_id": dist_id,
                    "launcher": _pick_launcher_fields(launcher_data),
                    "target_version": target_version,
                    "can_download": can_download,
                    "can_update": can_update
                })
            return jsonify({
                "success": True,
                "game_id": game_id,
                "game": {
                    "installed": installed,
                    "path": game.path if game else "",
                    "version": current_version,
                    "can_convert": can_convert,
                    "default_distribution": default_distribution
                },
                "distributions": distributions,
                "can_import_fever": can_import_fever,
                "fever": fever_info or {}
            })
        except Exception as e:
            logger.exception("获取启动器状态失败")
            return jsonify({
                "success": False,
                "error": str(e)
            })

    @app.route("/_idv-login/launcher-install", methods=["GET"])
    def _launcher_install():
        try:
            if sys.platform != "win32":
                return jsonify({"success": False, "error": "当前平台不支持安装"}), 400
            game_id = request.args["game_id"]
            distribution_id = int(request.args["distribution_id"])
            game = game_helper.get_game(game_id)
            launcher_data = game.get_launcher_data_for_distribution(distribution_id)
            if not launcher_data:
                return jsonify({"success": False, "error": "未找到启动器信息"}), 404
            startup_path = launcher_data.get("startup_path", "")
            if not startup_path:
                return jsonify({"success": False, "error": "启动器缺少启动路径"}), 400
            from PyQt5.QtWidgets import QApplication, QFileDialog, QWidget
            from PyQt5.QtCore import Qt


            app_inst = QApplication.instance()
            if app_inst is None:
                app_inst = QApplication(sys.argv)

            # 隐形父窗口
            dummy_parent = QWidget()
            dummy_parent.setWindowFlags(Qt.Tool)
            dummy_parent.show()
            dummy_parent.hide()

            desktop_path = os.path.join(os.path.expanduser('~'), 'Desktop')

            target_dir = QFileDialog.getExistingDirectory(
                dummy_parent,  # 关键点：不再是 None
                "选择安装目录",
                desktop_path,
                QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
            )

            if not target_dir:
                return jsonify({"success": False, "error": "用户取消选择安装目录"}), 400
            os.makedirs(target_dir, exist_ok=True)
            game_path = os.path.join(target_dir, startup_path)
            display_name = launcher_data.get("display_name") or launcher_data.get("app_name") or game_id
            game_helper.rename_game(game_id, display_name)
            game_helper.set_game_path(game_id, game_path)
            game_helper.set_game_default_distribution(game_id, distribution_id)
            max_concurrent = int(request.args.get("concurrent", "4"))
            updated = game.try_update(distribution_id, max_concurrent)
            if updated:
                short_game_id = getShortGameId(game_id)
                if CloudRes().is_convert_to_normal(short_game_id):
                    start_args = CloudRes().get_start_argument(short_game_id)
                    game.create_launch_shortcut(start_args,bypass_path_check=True)
            game_helper._save_games()
            return jsonify({
                "success": updated,
                "path": game_path,
                "version": game.get_version()
            })
        except Exception as e:
            logger.exception("安装启动器失败")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/_idv-login/launcher-update", methods=["GET"])
    def _launcher_update():
        try:
            game_id = request.args["game_id"]
            distribution_id = int(request.args["distribution_id"])
            game = game_helper.get_existing_game(game_id)
            if not game or not game.path or not os.path.exists(game.path):
                return jsonify({"success": False, "error": "未找到已安装的游戏"}), 404
            max_concurrent = int(request.args.get("concurrent", "4"))
            updated = game.try_update(distribution_id, max_concurrent)
            try:
                short_game_id = getShortGameId(game_id)
                if CloudRes().is_convert_to_normal(short_game_id):
                    start_args = CloudRes().get_start_argument(short_game_id)
                    game.create_launch_shortcut(start_args)
            except Exception:
                logger.exception("更新后创建快捷方式失败")
            game_helper._save_games()
            return jsonify({
                "success": updated,
                "version": game.get_version()
            })
        except Exception as e:
            logger.exception("更新启动器失败")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/_idv-login/launcher-update-info", methods=["GET"])
    def _launcher_update_info():
        try:
            game_id = request.args["game_id"]
            distribution_id = int(request.args["distribution_id"])
            game = game_helper.get_existing_game(game_id)
            if not game or not game.path or not os.path.exists(game.path):
                return jsonify({"success": False, "error": "未找到已安装的游戏"}), 404
            stats = game.get_update_stats(distribution_id)
            if not stats:
                return jsonify({"success": False, "error": "未找到更新信息"}), 404
            return jsonify({
                "success": True,
                "game_id": game_id,
                "distribution_id": distribution_id,
                **stats
            })
        except Exception as e:
            logger.exception("获取更新信息失败")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/_idv-login/launcher-import-fever", methods=["GET"])
    def _launcher_import_fever():
        try:
            game_id = request.args["game_id"]
            imported_game_id = game_helper.import_fever_game(game_id)
            if not imported_game_id:
                return jsonify({"success": False, "error": "未找到可导入的Fever游戏记录"}), 404
            return jsonify({"success": True, "game_id": imported_game_id})
        except Exception as e:
            logger.exception("导入Fever游戏失败")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/_idv-login/fever-games", methods=["GET"])
    def _list_fever_games():
        try:
            fever_games = game_helper.list_fever_games()
            result = []
            for item in fever_games:
                short_id = item.get("game_id")
                matched_game_id = game_helper.find_matching_game_id(short_id)
                result.append({
                    "game_id": short_id,
                    "display_name": item.get("display_name"),
                    "path": item.get("path"),
                    "distribution_id": item.get("distribution_id", -1),
                    "matched_game_id": matched_game_id
                })
            return jsonify({"success": True, "games": result})
        except Exception as e:
            logger.exception("获取Fever游戏列表失败")
            return jsonify({"success": False, "error": str(e)}), 500

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
            cloudRes = CloudRes()
            if cloudRes.get_login_page() == "":
                return Response(const.html)
            return Response(cloudRes.get_login_page())
        except Exception:
            return Response(const.html)

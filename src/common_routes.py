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
import json
import gevent

from flask import request, jsonify, Response, send_file
from channelHandler.channelUtils import getShortGameId
from cloudRes import CloudRes
from envmgr import genv
import const
from login_stack_mgr import LoginStackManager
from cloudSync import CloudSyncManager


def register_common_idv_routes(app, *, game_helper, logger):
    stack_mgr = LoginStackManager.get_instance()
    cloud_sync_mgr = CloudSyncManager(logger)
    auto_push_generation = {"value": 0}

    def _default_cloud_sync_settings():
        return {
            "consent_ack": False,
            "remember_level": "none",
            "saved_master_key": "",
            "auto_sync": False,
            "sync_direction": "bidirectional",
            "scope_type": "all",
            "scope_game_id": "",
            "scope_uuids": [],
            "expire_time": 259200,
        }

    def _get_cloud_sync_settings():
        settings = genv.get("CLOUD_SYNC_SETTINGS", {})
        if not isinstance(settings, dict):
            settings = {}
        merged = _default_cloud_sync_settings()
        merged.update(settings)
        return merged

    def _save_cloud_sync_settings(settings):
        genv.set("CLOUD_SYNC_SETTINGS", settings, True)

    def _resolve_cloud_sync_master_key(payload):
        settings = _get_cloud_sync_settings()
        master_key = payload.get("master_key", "")
        if master_key:
            return master_key
        return settings.get("saved_master_key", "")

    def _resolve_scope(payload):
        settings = _get_cloud_sync_settings()
        scope_type = payload.get("scope_type", settings.get("scope_type", "all"))
        scope_game_id = payload.get("scope_game_id", settings.get("scope_game_id", ""))
        scope_uuids = payload.get("scope_uuids", settings.get("scope_uuids", []))
        if not isinstance(scope_uuids, list):
            scope_uuids = []
        return {
            "type": scope_type,
            "game_id": scope_game_id,
            "uuids": scope_uuids,
        }

    def _refresh_channels_helper_after_pull():
        try:
            from channelmgr import ChannelManager
            genv.set("CHANNELS_HELPER", ChannelManager())
        except Exception:
            logger.exception("云同步拉取后刷新账号管理器失败")

    def _try_resolve_auto_sync_runtime():
        settings = _get_cloud_sync_settings()
        if not settings.get("auto_sync", False):
            return None, None, None, None
        if not settings.get("consent_ack", False):
            return None, None, None, None
        master_key = str(settings.get("saved_master_key", "") or "")
        if not master_key:
            return None, None, None, None
        strength = cloud_sync_mgr.evaluate_master_key_strength(master_key)
        if not strength.get("valid", False):
            return None, None, None, None
        scope = {
            "type": str(settings.get("scope_type", "all") or "all"),
            "game_id": str(settings.get("scope_game_id", "") or ""),
            "uuids": settings.get("scope_uuids", []) if isinstance(settings.get("scope_uuids", []), list) else [],
        }
        expire_time = int(settings.get("expire_time", 259200) or 259200)
        direction = str(settings.get("sync_direction", "bidirectional") or "bidirectional")
        return master_key, scope, expire_time, direction

    def _schedule_auto_push(reason: str):
        master_key, scope, expire_time, _ = _try_resolve_auto_sync_runtime()
        if not master_key:
            return

        auto_push_generation["value"] += 1
        current_generation = auto_push_generation["value"]

        def _delayed_push():
            logger.info(f"检测到账号记录更新，准备在5秒后自动上传云同步（原因: {reason}）")
            #print(f"[CloudSync] 检测到账号记录更新，准备在5秒后自动上传（原因: {reason}）")
            gevent.sleep(5)
            if current_generation != auto_push_generation["value"]:
                logger.info("自动上传任务已被新的更新事件覆盖，跳过本次上传")
                return
            try:
                result = cloud_sync_mgr.push(master_key, scope, expire_time)
                logger.info(f"自动上传完成：{result.get('action', 'push')}")
            except Exception:
                #清空本地同步记录，避免重复上传失败的记录
                
                logger.exception("自动上传云同步失败")

        gevent.spawn(_delayed_push)

    def _spawn_auto_pull_on_startup():
        master_key, _, _, direction = _try_resolve_auto_sync_runtime()
        if not master_key:
            return

        def _run_pull():
            try:
                if direction in ["pull", "bidirectional"]:
                    #logger.info("启动时自动同步：后台拉取云端账号中")
                    #print("[CloudSync] 启动时自动同步：后台拉取云端账号")
                    cloud_sync_mgr.pull(master_key)
                    _refresh_channels_helper_after_pull()
                    logger.debug("启动时自动同步：云端拉取完成")
            except Exception:
                logger.debug("启动时自动拉取云同步失败")

        gevent.spawn(_run_pull)

    def _pick_wechat_qrcode(game_id):
        cache = genv.get("WECHAT_QRCODE_CACHE", {})
        if not isinstance(cache, dict) or not cache:
            return None
        if game_id and game_id in cache:
            return cache.get(game_id)
        if game_id:
            for key, value in cache.items():
                common_len = 0
                for a, b in zip(reversed(game_id), reversed(key)):
                    if a == b:
                        common_len += 1
                    else:
                        break
                if common_len >= 3:
                    return value
        return cache.get("_default")
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

    @app.route("/_idv-login/qrcode", methods=["GET"])
    def _wechat_qrcode():
        game_id = request.args.get("game_id", "")
        data = _pick_wechat_qrcode(game_id)
        if not data:
            return jsonify({
                "success": False,
                "status": "idle",
                "qrcode_base64": "",
            })
        return jsonify({
            "success": True,
            "status": data.get("status", "idle"),
            "qrcode_base64": data.get("qrcode_base64", ""),
            "uuid": data.get("uuid", ""),
            "timestamp": data.get("timestamp", 0),
        })

    genv.set("CHANNELS_UPDATED_CALLBACK", _schedule_auto_push)

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
        success = genv.get("CHANNELS_HELPER").delete(request.args["uuid"])
        resp = {"success": success}
        return jsonify(resp)

    @app.route("/_idv-login/rename", methods=["GET"])
    def _rename_channel():
        success = genv.get("CHANNELS_HELPER").rename(request.args["uuid"], request.args["new_name"])
        resp = {"success": success}
        return jsonify(resp)

    @app.route("/_idv-login/import", methods=["GET"])
    def _import_channel():
        success = genv.get("CHANNELS_HELPER").manual_import(request.args["channel"], request.args["game_id"])
        resp = {"success": success}
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
                from PyQt6.QtWidgets import QApplication, QFileDialog, QWidget

                # 创建一个临时的QApplication实例
                app_inst = QApplication.instance()
                if app_inst is None:
                    app_inst = QApplication(sys.argv)

                # 导入Qt命名空间
                from PyQt6.QtCore import Qt

                # 显示文件选择对话框
                dummy_parent = QWidget()
                dummy_parent.setWindowFlags(Qt.WindowType.Tool)   # 不出现在任务栏
                dummy_parent.show()                    # 必须 show，OS 才承认它是窗口
                dummy_parent.hide()                    # 再藏起来给用户看不见

                desktop_path = os.path.join(os.path.expanduser('~'), 'Desktop')

                file_dialog = QFileDialog(dummy_parent)
                file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
                file_dialog.setNameFilter("可执行文件 (*.exe);;快捷方式 (*.lnk);;所有文件 (*.*)")
                file_dialog.setWindowTitle("选择游戏启动程序或快捷方式")
                file_dialog.setDirectory(desktop_path)

                file_dialog.show()
                file_dialog.raise_()
                file_dialog.activateWindow()

                if file_dialog.exec():
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
            from PyQt6.QtWidgets import QApplication, QFileDialog, QWidget
            from PyQt6.QtCore import Qt


            app_inst = QApplication.instance()
            if app_inst is None:
                app_inst = QApplication(sys.argv)

            # 隐形父窗口
            dummy_parent = QWidget()
            dummy_parent.setWindowFlags(Qt.WindowType.Tool)
            dummy_parent.show()
            dummy_parent.hide()

            desktop_path = os.path.join(os.path.expanduser('~'), 'Desktop')

            target_dir = QFileDialog.getExistingDirectory(
                dummy_parent,  # 关键点：不再是 None
                "选择安装目录",
                desktop_path,
                QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks
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

    @app.route("/_idv-login/cloud-sync/policy", methods=["GET"])
    def _cloud_sync_policy():
        return jsonify({
            "success": True,
            "policy": {
                "storage": "云端仅保存密文，不保存主密钥。系统使用主密钥+不同盐值派生 note_id、note密码、AES密钥。",
                "credential_levels": {
                    "none": "不记住主密钥；每次同步手动输入。",
                    "master_key": "记住主密钥；可用于自动同步。"
                },
                "permissions": {
                    "master_key": "主密钥是唯一凭证，可访问/修改/删除记录，并解密云端密文。"
                }
            }
        })

    @app.route("/_idv-login/cloud-sync/generate-master-key", methods=["POST"])
    def _cloud_sync_generate_master_key():
        try:
            payload = request.get_json(silent=True) or {}
            length = int(payload.get("length", 16) or 16)
            master_key = cloud_sync_mgr.generate_master_key(length)
            result = {
                "success": True,
                "master_key": master_key,
                "strength": cloud_sync_mgr.evaluate_master_key_strength(master_key),
            }
            return jsonify(result)
        except Exception as e:
            logger.exception("生成主密钥失败")
            return jsonify({"success": False, "error": str(e)})

    @app.route("/_idv-login/cloud-sync/settings", methods=["GET", "POST"])
    def _cloud_sync_settings():
        if request.method == "GET":
            settings = _get_cloud_sync_settings()
            return jsonify({"success": True, "settings": settings})

        try:
            payload = request.get_json(silent=True) or {}
            settings = _get_cloud_sync_settings()

            consent_ack = bool(payload.get("consent_ack", False))
            remember_level = str(payload.get("remember_level", "none"))
            if remember_level not in ["none", "master_key"]:
                return jsonify({"success": False, "error": "记住密码级别无效"})

            auto_sync = bool(payload.get("auto_sync", False))

            settings["consent_ack"] = consent_ack
            if auto_sync and not consent_ack:
                return jsonify({"success": False, "error": "启用自动同步前请先同意存储与权限说明"})
            settings["remember_level"] = remember_level
            settings["auto_sync"] = auto_sync
            settings["sync_direction"] = str(payload.get("sync_direction", "bidirectional"))
            settings["scope_type"] = str(payload.get("scope_type", "all"))
            settings["scope_game_id"] = str(payload.get("scope_game_id", ""))
            settings["scope_uuids"] = payload.get("scope_uuids", []) if isinstance(payload.get("scope_uuids", []), list) else []
            settings["expire_time"] = int(payload.get("expire_time", 259200) or 259200)

            master_key = str(payload.get("master_key", ""))

            if master_key:
                strength = cloud_sync_mgr.evaluate_master_key_strength(master_key)
                if not strength.get("valid", False):
                    return jsonify({"success": False, "error": "主密钥强度不足：至少12位且包含3类字符"})

            if remember_level == "master_key" and not master_key:
                return jsonify({"success": False, "error": "选择记住主密钥时，必须提供主密钥"})

            settings["saved_master_key"] = master_key if remember_level == "master_key" else ""

            _save_cloud_sync_settings(settings)
            return jsonify({"success": True, "settings": settings})
        except Exception as e:
            logger.exception("保存云同步设置失败")
            return jsonify({"success": False, "error": str(e)})

    @app.route("/_idv-login/cloud-sync/accounts", methods=["GET"])
    def _cloud_sync_accounts():
        try:
            channels_path = genv.get("FP_CHANNEL_RECORD", "")
            channels = []
            if channels_path and os.path.exists(channels_path):
                with open(channels_path, "r", encoding="utf-8") as file:
                    raw = json.load(file)
                    if isinstance(raw, list):
                        for item in raw:
                            channels.append({
                                "uuid": item.get("uuid", ""),
                                "name": item.get("name", ""),
                                "game_id": item.get("game_id", ""),
                                "channel": (item.get("login_info", {}) or {}).get("login_channel", ""),
                            })
            return jsonify({"success": True, "accounts": channels})
        except Exception as e:
            logger.exception("读取云同步账号范围失败")
            return jsonify({"success": False, "error": str(e)})

    @app.route("/_idv-login/cloud-sync/probe", methods=["POST"])
    def _cloud_sync_probe():
        try:
            payload = request.get_json(silent=True) or {}
            master_key = str(payload.get("master_key", ""))
            if not master_key:
                return jsonify({"success": False, "error": "主密钥不能为空"})
            result = cloud_sync_mgr.probe_remote(master_key)
            return jsonify(result)
        except Exception as e:
            logger.exception("探测云端同步信息失败")
            return jsonify({"success": False, "error": str(e)})

    @app.route("/_idv-login/cloud-sync/run", methods=["POST"])
    def _cloud_sync_run():
        try:
            payload = request.get_json(silent=True) or {}
            settings = _get_cloud_sync_settings()

            if not settings.get("consent_ack", False) and not bool(payload.get("consent_ack", False)):
                return jsonify({"success": False, "error": "请先同意云同步存储与权限说明"})

            action = str(payload.get("action", "sync"))
            if action == "auto" and not settings.get("auto_sync", False):
                return jsonify({"success": True, "skipped": True, "reason": "auto_sync_disabled"})

            master_key = _resolve_cloud_sync_master_key(payload)
            if not master_key:
                return jsonify({"success": False, "error": "主密钥不能为空"})
            strength = cloud_sync_mgr.evaluate_master_key_strength(master_key)
            if not strength.get("valid", False):
                return jsonify({"success": False, "error": "主密钥强度不足：至少12位且包含3类字符"})

            scope = _resolve_scope(payload)
            expire_time = int(payload.get("expire_time", settings.get("expire_time", 259200)) or 259200)

            if action == "push":
                result = cloud_sync_mgr.push(master_key, scope, expire_time)
                return jsonify(result)

            if action == "pull":
                result = cloud_sync_mgr.pull(master_key)
                _refresh_channels_helper_after_pull()
                return jsonify(result)

            direction = str(payload.get("sync_direction", settings.get("sync_direction", "bidirectional")))
            if direction not in ["push", "pull", "bidirectional"]:
                return jsonify({"success": False, "error": "同步方向无效"})

            steps = []
            if direction in ["pull", "bidirectional"]:
                try:
                    pull_result = cloud_sync_mgr.pull(master_key)
                    _refresh_channels_helper_after_pull()
                    steps.append(pull_result)
                except Exception as e:
                    logger.debug("云同步拉取失败，继续执行后续步骤", exc_info=e)
            if direction in ["push", "bidirectional"]:
                try:
                    push_result = cloud_sync_mgr.push(master_key, scope, expire_time)
                    steps.append(push_result)
                except Exception as e:
                    logger.debug("云同步推送失败，继续执行后续步骤", exc_info=e)

            return jsonify({"success": True, "action": "sync", "direction": direction, "steps": steps})
        except Exception as e:
            logger.exception("执行云同步失败")
            return jsonify({"success": False, "error": str(e)})

    @app.route("/_idv-login/cloud-sync/delete", methods=["POST"])
    def _cloud_sync_delete():
        try:
            payload = request.get_json(silent=True) or {}
            master_key = _resolve_cloud_sync_master_key(payload)
            if not master_key:
                return jsonify({"success": False, "error": "删除云同步需要主密钥"})
            result = cloud_sync_mgr.delete_remote(master_key)
            #同步禁止自动上传，直到用户重新启用
            settings = _get_cloud_sync_settings()
            settings["auto_sync"] = False
            settings["saved_master_key"] = ""
            settings["remember_level"] = "none"
            settings["consent_ack"] = False
            _save_cloud_sync_settings(settings)
            return jsonify(result)
        except Exception as e:
            logger.exception("删除云同步失败")
            return jsonify({"success": False, "error": str(e)})

    @app.route("/_idv-login/cloud-sync/access-logs", methods=["POST"])
    def _cloud_sync_access_logs():
        try:
            payload = request.get_json(silent=True) or {}
            master_key = _resolve_cloud_sync_master_key(payload)
            if not master_key:
                return jsonify({"success": False, "error": "查看访问日志需要主密钥"})
            logs = cloud_sync_mgr.fetch_access_logs(master_key)
            return jsonify({"success": True, "logs": logs})
        except Exception as e:
            logger.exception("获取云同步访问日志失败")
            return jsonify({"success": False, "error": str(e)})

    @app.route("/_idv-login/index", methods=['GET'])
    def _handle_switch_page():
        try:
            version = genv.get("VERSION", "")
            if not version:
                local_index_path = os.path.normpath(
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "index.html")
                )
                if os.path.exists(local_index_path):
                    return send_file(local_index_path, mimetype="text/html")
            cloudRes = CloudRes()
            if cloudRes.get_login_page() == "":
                return Response(const.html)
            return Response(cloudRes.get_login_page())
        except Exception:
            return Response(const.html)

    _spawn_auto_pull_on_startup()

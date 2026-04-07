# coding=UTF-8
"""
Copyright (c) 2026 KKeygen

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

import json
import os
import sys
import time
import threading
from typing import Tuple
from urllib.parse import parse_qs, urlparse

from envmgr import genv
import app_state
import const
from login_stack_mgr import LoginStackManager
from cloudSync import CloudSyncManager
from cloudRes import CloudRes
from channelHandler.channelUtils import getShortGameId


class LocalRequestHandler:
    """Handles /_idv-login/* API requests locally.

    Used by both the mitmproxy addon (for game WebView requests)
    and the QtWebEngine URL scheme handler (for the standalone Qt window).

    Each call to ``handle()`` is stateless w.r.t. the handler itself;
    all persistent state lives in ``genv`` / managers.
    """

    _cloud_sync_mgr = None
    _cloud_sync_lock = threading.Lock()
    _auto_push_generation = {"value": 0}
    _pending_imports = {}  # {task_id: {"status": "pending"|"done", "success": bool}}

    def __init__(self, *, game_helper, logger):
        self.game_helper = game_helper
        self.logger = logger
        self.stack_mgr = LoginStackManager.get_instance()

        with self._cloud_sync_lock:
            if LocalRequestHandler._cloud_sync_mgr is None:
                LocalRequestHandler._cloud_sync_mgr = CloudSyncManager(logger)
        self.cloud_sync_mgr = LocalRequestHandler._cloud_sync_mgr

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def handle(self, request) -> Tuple[int, dict, bytes]:
        """Dispatch a request and return (status_code, headers, body_bytes).

        ``request`` can be a ``mitmproxy.http.Request`` or any object
        exposing ``.path``, ``.method``, ``.query`` (dict-like), and
        ``.content`` (bytes).
        """
        path_raw = getattr(request, "path", "/")
        parsed = urlparse(path_raw)
        path = parsed.path
        method = getattr(request, "method", "GET").upper()

        # Parse query parameters
        if hasattr(request, "query") and hasattr(request.query, "items"):
            args = {k: v for k, v in request.query.items()}
        else:
            qs = parsed.query
            parsed_qs = parse_qs(qs, keep_blank_values=True)
            args = {k: v[0] if len(v) == 1 else v for k, v in parsed_qs.items()}

        # Parse JSON body for POST requests
        json_body = None
        if method == "POST":
            try:
                raw = getattr(request, "content", b"")
                if isinstance(raw, memoryview):
                    raw = bytes(raw)
                json_body = json.loads(raw) if raw else {}
            except Exception:
                json_body = {}

        return self._route(path, method, args, json_body)

    # For the Qt scheme handler which uses a simpler interface
    def handle_simple(self, path: str, method: str = "GET",
                      args: dict = None, json_body: dict = None) -> Tuple[int, dict, bytes]:
        return self._route(path, method, args or {}, json_body)

    # ------------------------------------------------------------------
    # Router
    # ------------------------------------------------------------------

    def _route(self, path: str, method: str, args: dict,
               json_body: dict = None) -> Tuple[int, dict, bytes]:
        route_map = {
            "/_idv-login/manualChannels": self._manual_channels,
            "/_idv-login/list": self._list_channels,
            "/_idv-login/qrcode": self._wechat_qrcode,
            "/_idv-login/switch": self._switch_channel,
            "/_idv-login/switch-status": self._switch_status,
            "/_idv-login/del": self._del_channel,
            "/_idv-login/rename": self._rename_channel,
            "/_idv-login/import": self._import_channel,
            "/_idv-login/import-status": self._import_status,
            "/_idv-login/setDefault": self._set_default,
            "/_idv-login/clearDefault": self._clear_default,
            "/_idv-login/get-auto-close-state": self._get_auto_close_state,
            "/_idv-login/switch-auto-close-state": self._switch_auto_close_state,
            "/_idv-login/get-game-auto-start": self._get_game_auto_start,
            "/_idv-login/set-game-auto-start": self._set_game_auto_start,
            "/_idv-login/start-game": self._start_game,
            "/_idv-login/list-games": self._list_games,
            "/_idv-login/launcher-status": self._launcher_status,
            "/_idv-login/launcher-install": self._launcher_install,
            "/_idv-login/launcher-update": self._launcher_update,
            "/_idv-login/launcher-update-info": self._launcher_update_info,
            "/_idv-login/launcher-import-fever": self._launcher_import_fever,
            "/_idv-login/fever-games": self._list_fever_games,
            "/_idv-login/defaultChannel": self._get_default_channel,
            "/_idv-login/get-login-delay": self._get_login_delay,
            "/_idv-login/set-login-delay": self._set_login_delay,
            "/_idv-login/cloud-sync/policy": self._cloud_sync_policy,
            "/_idv-login/cloud-sync/generate-master-key": self._cloud_sync_generate_key,
            "/_idv-login/cloud-sync/settings": self._cloud_sync_settings,
            "/_idv-login/cloud-sync/accounts": self._cloud_sync_accounts,
            "/_idv-login/cloud-sync/probe": self._cloud_sync_probe,
            "/_idv-login/cloud-sync/run": self._cloud_sync_run,
            "/_idv-login/cloud-sync/delete": self._cloud_sync_delete,
            "/_idv-login/cloud-sync/access-logs": self._cloud_sync_access_logs,
            "/_idv-login/index": self._serve_index,
            "/_idv-login/export-logs": self._export_logs,
            "/_idv-login/open-external-url": self._open_external_url,
            "/_idv-login/proxy-mode": self._get_proxy_mode,
            "/_idv-login/set-proxy-mode": self._set_proxy_mode,
            "/_idv-login/create-game-shortcut": self._create_game_shortcut,

        }

        handler = route_map.get(path)
        if handler:
            try:
                return handler(args, json_body, method)
            except Exception as e:
                self.logger.exception(f"处理请求 {path} 时出错")
                return self._json_response(500, {"success": False, "error": str(e)})

        return self._json_response(404, {"error": "Not found"})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _json_response(status: int, data) -> Tuple[int, dict, bytes]:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json; charset=utf-8"}
        return status, headers, body

    @staticmethod
    def _html_response(status: int, html: str) -> Tuple[int, dict, bytes]:
        body = html.encode("utf-8") if isinstance(html, str) else html
        headers = {"Content-Type": "text/html; charset=utf-8"}
        return status, headers, body

    # -- Cloud sync helpers (ported from common_routes.py) ──

    def _default_cloud_sync_settings(self):
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

    def _get_cloud_sync_settings(self):
        settings = genv.get("CLOUD_SYNC_SETTINGS", {})
        if not isinstance(settings, dict):
            settings = {}
        merged = self._default_cloud_sync_settings()
        merged.update(settings)
        return merged

    def _save_cloud_sync_settings(self, settings):
        genv.set("CLOUD_SYNC_SETTINGS", settings, True)

    def _resolve_master_key(self, payload):
        settings = self._get_cloud_sync_settings()
        mk = payload.get("master_key", "")
        return mk if mk else settings.get("saved_master_key", "")

    def _resolve_scope(self, payload):
        settings = self._get_cloud_sync_settings()
        return {
            "type": payload.get("scope_type", settings.get("scope_type", "all")),
            "game_id": payload.get("scope_game_id", settings.get("scope_game_id", "")),
            "uuids": (
                payload.get("scope_uuids", settings.get("scope_uuids", []))
                if isinstance(payload.get("scope_uuids", settings.get("scope_uuids", [])), list)
                else []
            ),
        }

    def _schedule_auto_push(self, reason: str):
        settings = self._get_cloud_sync_settings()
        if not settings.get("auto_sync", False) or not settings.get("consent_ack", False):
            return
        master_key = str(settings.get("saved_master_key", "") or "")
        if not master_key:
            return
        strength = self.cloud_sync_mgr.evaluate_master_key_strength(master_key)
        if not strength.get("valid", False):
            return
        scope = {
            "type": str(settings.get("scope_type", "all") or "all"),
            "game_id": str(settings.get("scope_game_id", "") or ""),
            "uuids": settings.get("scope_uuids", []) if isinstance(settings.get("scope_uuids", []), list) else [],
        }
        expire_time = int(settings.get("expire_time", 259200) or 259200)

        self._auto_push_generation["value"] += 1
        gen = self._auto_push_generation["value"]

        def _push():
            self.logger.info(f"检测到账号记录更新，准备在5秒后自动上传云同步（原因: {reason}）")
            time.sleep(5)
            if gen != self._auto_push_generation["value"]:
                return
            try:
                self.cloud_sync_mgr.push(master_key, scope, expire_time)
            except Exception:
                self.logger.exception("自动上传云同步失败")

        threading.Thread(target=_push, daemon=True).start()

    def _pick_wechat_qrcode(self, game_id):
        cache = genv.get("WECHAT_QRCODE_CACHE", {})
        if not isinstance(cache, dict) or not cache:
            return None
        if game_id and game_id in cache:
            return cache.get(game_id)
        if game_id:
            for key in cache:
                common_len = sum(
                    1 for a, b in zip(reversed(game_id), reversed(key)) if a == b
                )
                if common_len >= 3:
                    return cache[key]
        return cache.get("_default")

    @staticmethod
    def _pick_launcher_fields(launcher_data):
        if not launcher_data:
            return {}
        keys = [
            "app_id", "app_name", "display_name", "logo", "icon",
            "main_image", "developer", "publisher", "version_code",
            "startup_path", "startup_params",
        ]
        return {k: launcher_data.get(k) for k in keys}

    # ------------------------------------------------------------------
    # Route implementations
    # ------------------------------------------------------------------

    def _manual_channels(self, args, body, method):
        try:
            game_id = args.get("game_id", "")
            if game_id:
                data = CloudRes().get_all_by_game_id(getShortGameId(game_id))
                return self._json_response(200, data)
        except Exception:
            pass
        return self._json_response(200, const.manual_login_channels)

    def _list_channels(self, args, body, method):
        try:
            result = app_state.channels_helper.list_channels(args.get("game_id", ""))
        except Exception as e:
            result = {"error": str(e)}
        return self._json_response(200, result)

    def _wechat_qrcode(self, args, body, method):
        game_id = args.get("game_id", "")
        data = self._pick_wechat_qrcode(game_id)
        if not data:
            return self._json_response(200, {
                "success": False, "status": "idle", "qrcode_base64": "",
            })
        return self._json_response(200, {
            "success": True,
            "status": data.get("status", "idle"),
            "qrcode_base64": data.get("qrcode_base64", ""),
            "uuid": data.get("uuid", ""),
            "timestamp": data.get("timestamp", 0),
        })

    _pending_switch = {}  # {task_id: {"status": "pending"|"done", "result": any}}

    def _switch_channel(self, args, body, method):
        uuid = args.get("uuid", "")
        game_id = args.get("game_id", "")
        genv.set("CHANNEL_ACCOUNT_SELECTED", uuid)
        data = self.stack_mgr.pop_cached_qrcode_data(game_id) if game_id else None

        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
        except Exception:
            app = None

        scanner_uuid = data["uuid"] if data else "Kinich"
        scan_game_id = data["game_id"] if data else "aecfrt3rmaaaaajl-g-g37"

        if app and app.property("_main_loop_running"):
            # 异步模式
            import uuid as uuid_mod
            from PyQt6.QtCore import QTimer
            task_id = str(uuid_mod.uuid4())
            LocalRequestHandler._pending_switch[task_id] = {"status": "pending"}

            def do_switch():
                def on_done(result):
                    LocalRequestHandler._pending_switch[task_id] = {
                        "status": "done", "result": result
                    }

                try:
                    app_state.channels_helper.simulate_scan(
                        uuid, scanner_uuid, scan_game_id, on_complete=on_done
                    )
                except Exception:
                    self.logger.exception("异步切换渠道失败")
                    LocalRequestHandler._pending_switch[task_id] = {
                        "status": "done", "result": False
                    }

            QTimer.singleShot(0, do_switch)
            return self._json_response(200, {"status": "pending", "task_id": task_id})
        else:
            # 同步模式
            if data:
                app_state.channels_helper.simulate_scan(uuid, data["uuid"], data["game_id"])
            else:
                app_state.channels_helper.simulate_scan(uuid, "Kinich", "aecfrt3rmaaaaajl-g-g37")
            return self._json_response(200, {"current": genv.get("CHANNEL_ACCOUNT_SELECTED")})

    def _switch_status(self, args, body, method):
        """检查异步切换渠道的状态"""
        task_id = args.get("task_id", "")
        task = LocalRequestHandler._pending_switch.get(task_id)
        if task is None:
            return self._json_response(404, {"error": "Unknown task_id"})
        result = dict(task)
        if task["status"] == "done":
            del LocalRequestHandler._pending_switch[task_id]
        return self._json_response(200, result)

    def _del_channel(self, args, body, method):
        success = app_state.channels_helper.delete(args.get("uuid", ""))
        return self._json_response(200, {"success": success})

    def _rename_channel(self, args, body, method):
        success = app_state.channels_helper.rename(
            args.get("uuid", ""), args.get("new_name", "")
        )
        return self._json_response(200, {"success": success})

    def _import_channel(self, args, body, method):
        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
        except Exception:
            app = None

        if app and app.property("_main_loop_running"):
            # 异步模式：不阻塞 scheme handler，立即返回 pending
            import uuid as uuid_mod
            from PyQt6.QtCore import QTimer
            task_id = str(uuid_mod.uuid4())
            LocalRequestHandler._pending_imports[task_id] = {"status": "pending"}

            channel = args.get("channel", "")
            game_id = args.get("game_id", "")

            def do_import():
                def on_done(success):
                    LocalRequestHandler._pending_imports[task_id] = {
                        "status": "done", "success": success
                    }

                try:
                    app_state.channels_helper.manual_import(
                        channel, game_id, on_complete=on_done
                    )
                except Exception:
                    self.logger.exception("异步导入失败")
                    LocalRequestHandler._pending_imports[task_id] = {
                        "status": "done", "success": False
                    }

            QTimer.singleShot(0, do_import)
            return self._json_response(200, {"status": "pending", "task_id": task_id})
        else:
            # 同步模式（旧 HTTP 路径）
            success = app_state.channels_helper.manual_import(
                args.get("channel", ""), args.get("game_id", "")
            )
            return self._json_response(200, {"success": success})

    def _import_status(self, args, body, method):
        task_id = args.get("task_id", "")
        task = LocalRequestHandler._pending_imports.get(task_id)
        if task is None:
            return self._json_response(404, {"error": "Unknown task_id"})
        result = dict(task)
        if task["status"] == "done":
            del LocalRequestHandler._pending_imports[task_id]
        return self._json_response(200, result)

    def _set_default(self, args, body, method):
        try:
            genv.set(f"auto-{args['game_id']}", args["uuid"], True)
            return self._json_response(200, {"success": True})
        except Exception:
            self.logger.exception("设置默认账号失败")
            return self._json_response(200, {"success": False})

    def _clear_default(self, args, body, method):
        try:
            genv.set(f"auto-{args['game_id']}", "", True)
            return self._json_response(200, {"success": True})
        except Exception:
            return self._json_response(200, {"success": False})

    def _get_auto_close_state(self, args, body, method):
        try:
            gid = args["game_id"]
            return self._json_response(200, {
                "success": True, "state": self.game_helper.get_auto_close_setting(gid), "game_id": gid
            })
        except Exception as e:
            return self._json_response(200, {"success": False, "error": str(e)})

    def _switch_auto_close_state(self, args, body, method):
        try:
            gid = args["game_id"]
            new_state = not self.game_helper.get_auto_close_setting(gid)
            self.game_helper.set_auto_close_setting(gid, new_state)
            return self._json_response(200, {"success": True, "state": new_state, "game_id": gid})
        except Exception as e:
            return self._json_response(200, {"success": False, "error": str(e)})

    def _get_game_auto_start(self, args, body, method):
        try:
            gid = args["game_id"]
            info = self.game_helper.get_game_auto_start(gid)
            return self._json_response(200, {
                "success": True, "enabled": info["enabled"], "path": info["path"], "game_id": gid
            })
        except Exception as e:
            return self._json_response(200, {"success": False, "error": str(e)})

    def _set_game_auto_start(self, args, body, method):
        try:
            gid = args["game_id"]
            enabled = args.get("enabled") == "true"
            game_path = ""

            if enabled:
                from PyQt6.QtWidgets import QApplication, QFileDialog, QWidget
                from PyQt6.QtCore import Qt

                app_inst = QApplication.instance()
                if app_inst is None:
                    app_inst = QApplication(sys.argv)

                dummy_parent = QWidget()
                dummy_parent.setWindowFlags(Qt.WindowType.Tool)
                dummy_parent.show()
                dummy_parent.hide()

                desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")

                file_dialog = QFileDialog(dummy_parent)
                file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
                file_dialog.setNameFilter("可执行文件 (*.exe);;快捷方式 (*.lnk);;所有文件 (*.*)")
                file_dialog.setWindowTitle("选择游戏启动程序或快捷方式")
                file_dialog.setDirectory(desktop_path)
                file_dialog.show()
                file_dialog.raise_()
                file_dialog.activateWindow()

                if file_dialog.exec():
                    selected = file_dialog.selectedFiles()
                    if selected:
                        game_path = selected[0]

                if not game_path:
                    return self._json_response(200, {"success": False, "error": "用户取消选择游戏路径"})

                name = os.path.splitext(os.path.basename(game_path))[0]

                if game_path.lower().endswith(".lnk") and sys.platform == "win32":
                    import win32com.client
                    shell = win32com.client.Dispatch("WScript.Shell")
                    shortcut = shell.CreateShortcut(game_path)
                    game_path = shortcut.Targetpath
            else:
                game = self.game_helper.get_game(gid)
                name = game.name if game else ""

            self.game_helper.set_game_auto_start(gid, enabled)
            self.game_helper.set_game_path(gid, game_path)
            self.game_helper.rename_game(gid, name)
            return self._json_response(200, {
                "success": True, "enabled": enabled, "path": game_path, "game_id": gid
            })
        except Exception as e:
            self.logger.exception(f"设置游戏 {args.get('game_id', '')} 的自动启动状态失败")
            return self._json_response(200, {"success": False, "error": str(e)})

    def _start_game(self, args, body, method):
        try:
            gid = args["game_id"]
            path = self.game_helper.get_game_auto_start(gid)["path"]
            if not path:
                return self._json_response(200, {"success": False, "error": "游戏路径未设置"})
            game = self.game_helper.get_game(gid)
            if game:
                game.start()
                game.last_used_time = int(time.time())
                self.game_helper._save_games()
            return self._json_response(200, {"success": True, "game_id": gid})
        except Exception as e:
            return self._json_response(200, {"success": False, "error": str(e)})

    def _list_games(self, args, body, method):
        try:
            return self._json_response(200, {"success": True, "games": self.game_helper.list_games()})
        except Exception as e:
            return self._json_response(200, {"success": False, "error": str(e)})

    def _launcher_status(self, args, body, method):
        try:
            gid = args["game_id"]
            short_gid = getShortGameId(gid)
            game = self.game_helper.get_existing_game(gid)
            game_for_remote = self.game_helper.get_game_or_temp(gid)
            distribution_ids = game_for_remote.get_distributions()
            installed = bool(game and game.path and os.path.exists(game.path))
            can_convert = CloudRes().is_convert_to_normal(short_gid)
            current_version = game.get_version() if game else ""
            default_dist = game.get_default_distribution() if game else -1
            fever_info = None
            for item in self.game_helper.list_fever_games():
                if item.get("game_id") == short_gid:
                    fever_info = item
                    break
            can_import_fever = bool(fever_info) and (
                not game or not game.path or (
                    fever_info.get("path") and fever_info.get("path") != game.path
                )
            )
            distributions = []
            for dist_id in distribution_ids:
                launcher_data = game_for_remote.get_launcher_data_for_distribution(dist_id)
                file_info = game_for_remote.get_file_distribution_info(dist_id)
                target_ver = file_info.get("version_code", "") if file_info else ""
                can_download = CloudRes().is_downloadable(short_gid) and file_info is not None
                distributions.append({
                    "distribution_id": dist_id,
                    "launcher": self._pick_launcher_fields(launcher_data),
                    "target_version": target_ver,
                    "can_download": can_download,
                    "can_update": bool(installed),
                })
            return self._json_response(200, {
                "success": True, "game_id": gid,
                "game": {
                    "installed": installed, "path": game.path if game else "",
                    "version": current_version, "can_convert": can_convert,
                    "default_distribution": default_dist,
                },
                "distributions": distributions,
                "can_import_fever": can_import_fever,
                "fever": fever_info or {},
            })
        except Exception as e:
            self.logger.exception("获取启动器状态失败")
            return self._json_response(200, {"success": False, "error": str(e)})

    def _launcher_install(self, args, body, method):
        try:
            if sys.platform != "win32":
                return self._json_response(400, {"success": False, "error": "当前平台不支持安装"})
            gid = args["game_id"]
            dist_id = int(args["distribution_id"])
            game = self.game_helper.get_game(gid)
            launcher_data = game.get_launcher_data_for_distribution(dist_id)
            if not launcher_data:
                return self._json_response(404, {"success": False, "error": "未找到启动器信息"})
            startup_path = launcher_data.get("startup_path", "")
            if not startup_path:
                return self._json_response(400, {"success": False, "error": "启动器缺少启动路径"})

            from PyQt6.QtWidgets import QApplication, QFileDialog, QWidget
            from PyQt6.QtCore import Qt
            app_inst = QApplication.instance()
            if app_inst is None:
                app_inst = QApplication(sys.argv)
            dummy = QWidget()
            dummy.setWindowFlags(Qt.WindowType.Tool)
            dummy.show()
            dummy.hide()
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            target_dir = QFileDialog.getExistingDirectory(
                dummy, "选择安装目录", desktop,
                QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks,
            )
            if not target_dir:
                return self._json_response(400, {"success": False, "error": "用户取消选择安装目录"})
            os.makedirs(target_dir, exist_ok=True)
            game_path = os.path.join(target_dir, startup_path)
            display_name = launcher_data.get("display_name") or launcher_data.get("app_name") or gid
            self.game_helper.rename_game(gid, display_name)
            self.game_helper.set_game_path(gid, game_path)
            self.game_helper.set_game_default_distribution(gid, dist_id)
            max_conc = int(args.get("concurrent", "4"))
            updated = game.try_update(dist_id, max_conc)
            if updated:
                sgid = getShortGameId(gid)
                if CloudRes().is_convert_to_normal(sgid):
                    sa = CloudRes().get_start_argument(sgid)
                    game.create_tool_launch_shortcut(game.path or "")
            self.game_helper._save_games()
            return self._json_response(200, {"success": updated, "path": game_path, "version": game.get_version()})
        except Exception as e:
            self.logger.exception("安装启动器失败")
            return self._json_response(500, {"success": False, "error": str(e)})

    def _launcher_update(self, args, body, method):
        try:
            gid = args["game_id"]
            dist_id = int(args["distribution_id"])
            game = self.game_helper.get_existing_game(gid)
            if not game or not game.path or not os.path.exists(game.path):
                return self._json_response(404, {"success": False, "error": "未找到已安装的游戏"})
            max_conc = int(args.get("concurrent", "4"))
            updated = game.try_update(dist_id, max_conc)
            try:
                sgid = getShortGameId(gid)
                if CloudRes().is_convert_to_normal(sgid):
                    sa = CloudRes().get_start_argument(sgid)
                    game.create_tool_launch_shortcut(game.path or "")
            except Exception:
                self.logger.exception("更新后创建快捷方式失败")
            self.game_helper._save_games()
            return self._json_response(200, {"success": updated, "version": game.get_version()})
        except Exception as e:
            self.logger.exception("更新启动器失败")
            return self._json_response(500, {"success": False, "error": str(e)})

    def _launcher_update_info(self, args, body, method):
        try:
            gid = args["game_id"]
            dist_id = int(args["distribution_id"])
            game = self.game_helper.get_existing_game(gid)
            if not game or not game.path or not os.path.exists(game.path):
                return self._json_response(404, {"success": False, "error": "未找到已安装的游戏"})
            stats = game.get_update_stats(dist_id)
            if not stats:
                return self._json_response(404, {"success": False, "error": "未找到更新信息"})
            return self._json_response(200, {"success": True, "game_id": gid, "distribution_id": dist_id, **stats})
        except Exception as e:
            self.logger.exception("获取更新信息失败")
            return self._json_response(500, {"success": False, "error": str(e)})

    def _launcher_import_fever(self, args, body, method):
        try:
            imported = self.game_helper.import_fever_game(args["game_id"])
            if not imported:
                return self._json_response(404, {"success": False, "error": "未找到可导入的Fever游戏记录"})
            return self._json_response(200, {"success": True, "game_id": imported})
        except Exception as e:
            self.logger.exception("导入Fever游戏失败")
            return self._json_response(500, {"success": False, "error": str(e)})

    def _list_fever_games(self, args, body, method):
        try:
            result = []
            for item in self.game_helper.list_fever_games():
                short_id = item.get("game_id")
                matched = self.game_helper.find_matching_game_id(short_id)
                result.append({
                    "game_id": short_id,
                    "display_name": item.get("display_name"),
                    "path": item.get("path"),
                    "distribution_id": item.get("distribution_id", -1),
                    "matched_game_id": matched,
                })
            return self._json_response(200, {"success": True, "games": result})
        except Exception as e:
            return self._json_response(500, {"success": False, "error": str(e)})

    def _get_default_channel(self, args, body, method):
        uuid = genv.get(f"auto-{args.get('game_id', '')}", "")
        if uuid and app_state.channels_helper.query_channel(uuid) is None:
            genv.set(f"auto-{args.get('game_id', '')}", "", True)
            uuid = ""
        return self._json_response(200, {"uuid": uuid})

    def _get_login_delay(self, args, body, method):
        return self._json_response(200, {
            "delay": self.game_helper.get_login_delay(args.get("game_id", ""))
        })

    def _set_login_delay(self, args, body, method):
        try:
            self.game_helper.set_login_delay(args["game_id"], int(args["delay"]))
            return self._json_response(200, {"success": True})
        except Exception as e:
            return self._json_response(200, {"success": False, "error": str(e)})

    # -- Cloud sync routes ──

    def _cloud_sync_policy(self, args, body, method):
        return self._json_response(200, {
            "success": True,
            "policy": {
                "storage": "云端仅保存密文，不保存主密钥。系统使用主密钥+不同盐值派生 note_id、note密码、AES密钥。",
                "credential_levels": {
                    "none": "不记住主密钥；每次同步手动输入。",
                    "master_key": "记住主密钥；可用于自动同步。",
                },
                "permissions": {
                    "master_key": "主密钥是唯一凭证，可访问/修改/删除记录，并解密云端密文。",
                },
            },
        })

    def _cloud_sync_generate_key(self, args, body, method):
        try:
            payload = body or {}
            length = int(payload.get("length", 16) or 16)
            mk = self.cloud_sync_mgr.generate_master_key(length)
            return self._json_response(200, {
                "success": True, "master_key": mk,
                "strength": self.cloud_sync_mgr.evaluate_master_key_strength(mk),
            })
        except Exception as e:
            return self._json_response(200, {"success": False, "error": str(e)})

    def _cloud_sync_settings(self, args, body, method):
        if method == "GET":
            return self._json_response(200, {"success": True, "settings": self._get_cloud_sync_settings()})
        try:
            payload = body or {}
            settings = self._get_cloud_sync_settings()
            consent_ack = bool(payload.get("consent_ack", False))
            remember_level = str(payload.get("remember_level", "none"))
            if remember_level not in ("none", "master_key"):
                return self._json_response(200, {"success": False, "error": "记住密码级别无效"})
            auto_sync = bool(payload.get("auto_sync", False))
            settings["consent_ack"] = consent_ack
            if auto_sync and not consent_ack:
                return self._json_response(200, {"success": False, "error": "启用自动同步前请先同意存储与权限说明"})
            settings["remember_level"] = remember_level
            settings["auto_sync"] = auto_sync
            settings["sync_direction"] = str(payload.get("sync_direction", "bidirectional"))
            settings["scope_type"] = str(payload.get("scope_type", "all"))
            settings["scope_game_id"] = str(payload.get("scope_game_id", ""))
            settings["scope_uuids"] = (
                payload.get("scope_uuids", []) if isinstance(payload.get("scope_uuids", []), list) else []
            )
            settings["expire_time"] = int(payload.get("expire_time", 259200) or 259200)
            mk = str(payload.get("master_key", ""))
            if mk:
                strength = self.cloud_sync_mgr.evaluate_master_key_strength(mk)
                if not strength.get("valid", False):
                    return self._json_response(200, {"success": False, "error": "主密钥强度不足：至少12位且包含3类字符"})
            if remember_level == "master_key" and not mk:
                return self._json_response(200, {"success": False, "error": "选择记住主密钥时，必须提供主密钥"})
            settings["saved_master_key"] = mk if remember_level == "master_key" else ""
            self._save_cloud_sync_settings(settings)
            return self._json_response(200, {"success": True, "settings": settings})
        except Exception as e:
            return self._json_response(200, {"success": False, "error": str(e)})

    def _cloud_sync_accounts(self, args, body, method):
        try:
            channels_path = genv.get("FP_CHANNEL_RECORD", "")
            channels = []
            if channels_path and os.path.exists(channels_path):
                with open(channels_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    if isinstance(raw, list):
                        for item in raw:
                            channels.append({
                                "uuid": item.get("uuid", ""),
                                "name": item.get("name", ""),
                                "game_id": item.get("game_id", ""),
                                "channel": (item.get("login_info", {}) or {}).get("login_channel", ""),
                            })
            return self._json_response(200, {"success": True, "accounts": channels})
        except Exception as e:
            return self._json_response(200, {"success": False, "error": str(e)})

    def _cloud_sync_probe(self, args, body, method):
        try:
            payload = body or {}
            mk = str(payload.get("master_key", ""))
            if not mk:
                return self._json_response(200, {"success": False, "error": "主密钥不能为空"})
            return self._json_response(200, self.cloud_sync_mgr.probe_remote(mk))
        except Exception as e:
            return self._json_response(200, {"success": False, "error": str(e)})

    def _cloud_sync_run(self, args, body, method):
        try:
            payload = body or {}
            settings = self._get_cloud_sync_settings()
            if not settings.get("consent_ack", False) and not bool(payload.get("consent_ack", False)):
                return self._json_response(200, {"success": False, "error": "请先同意云同步存储与权限说明"})
            action = str(payload.get("action", "sync"))
            if action == "auto" and not settings.get("auto_sync", False):
                return self._json_response(200, {"success": True, "skipped": True, "reason": "auto_sync_disabled"})
            mk = self._resolve_master_key(payload)
            if not mk:
                return self._json_response(200, {"success": False, "error": "主密钥不能为空"})
            strength = self.cloud_sync_mgr.evaluate_master_key_strength(mk)
            if not strength.get("valid", False):
                return self._json_response(200, {"success": False, "error": "主密钥强度不足：至少12位且包含3类字符"})
            scope = self._resolve_scope(payload)
            expire_time = int(payload.get("expire_time", settings.get("expire_time", 259200)) or 259200)
            if action == "push":
                return self._json_response(200, self.cloud_sync_mgr.push(mk, scope, expire_time))
            if action == "pull":
                result = self.cloud_sync_mgr.pull(mk)
                self._refresh_channels_helper()
                return self._json_response(200, result)
            direction = str(payload.get("sync_direction", settings.get("sync_direction", "bidirectional")))
            if direction not in ("push", "pull", "bidirectional"):
                return self._json_response(200, {"success": False, "error": "同步方向无效"})
            steps = []
            if direction in ("pull", "bidirectional"):
                try:
                    steps.append(self.cloud_sync_mgr.pull(mk))
                    self._refresh_channels_helper()
                except Exception as e:
                    self.logger.debug("云同步拉取失败", exc_info=e)
            if direction in ("push", "bidirectional"):
                try:
                    steps.append(self.cloud_sync_mgr.push(mk, scope, expire_time))
                except Exception as e:
                    self.logger.debug("云同步推送失败", exc_info=e)
            return self._json_response(200, {"success": True, "action": "sync", "direction": direction, "steps": steps})
        except Exception as e:
            return self._json_response(200, {"success": False, "error": str(e)})

    def _cloud_sync_delete(self, args, body, method):
        try:
            payload = body or {}
            mk = self._resolve_master_key(payload)
            if not mk:
                return self._json_response(200, {"success": False, "error": "删除云同步需要主密钥"})
            result = self.cloud_sync_mgr.delete_remote(mk)
            settings = self._get_cloud_sync_settings()
            settings["auto_sync"] = False
            settings["saved_master_key"] = ""
            settings["remember_level"] = "none"
            settings["consent_ack"] = False
            self._save_cloud_sync_settings(settings)
            return self._json_response(200, result)
        except Exception as e:
            return self._json_response(200, {"success": False, "error": str(e)})

    def _cloud_sync_access_logs(self, args, body, method):
        try:
            payload = body or {}
            mk = self._resolve_master_key(payload)
            if not mk:
                return self._json_response(200, {"success": False, "error": "查看访问日志需要主密钥"})
            logs = self.cloud_sync_mgr.fetch_access_logs(mk)
            return self._json_response(200, {"success": True, "logs": logs})
        except Exception as e:
            return self._json_response(200, {"success": False, "error": str(e)})

    def _refresh_channels_helper(self):
        try:
            from channelmgr import ChannelManager
            app_state.channels_helper = ChannelManager()
        except Exception:
            self.logger.exception("云同步拉取后刷新账号管理器失败")

    # -- Utility routes ──

    def _serve_index(self, args, body, method):
        try:
            version = genv.get("VERSION", "")
            if not version:
                local_path = os.path.normpath(
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "index.html")
                )
                if os.path.exists(local_path):
                    with open(local_path, "r", encoding="utf-8") as f:
                        return self._html_response(200, f.read())
            cloud_page = CloudRes().get_login_page()
            if cloud_page:
                return self._html_response(200, cloud_page)
            return self._html_response(200, const.html)
        except Exception:
            return self._html_response(200, const.html)

    def _export_logs(self, args, body, method):
        """Export diagnostic logs: save to file and open containing folder."""
        try:
            from debugmgr import DebugMgr
            data = DebugMgr.export_debug_info_json() if DebugMgr.is_windows() else {}
            log_dir = genv.get("FP_WORKDIR")
            log_path = os.path.join(log_dir, "log.txt")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("\n\n" + json.dumps(data, ensure_ascii=False, indent=2))
            if os.path.exists(log_path):
                import subprocess
                subprocess.Popen(["explorer", "/select,", log_path])
                return self._json_response(200, {"success": True, "path": log_path})
            return self._json_response(404, {"success": False, "error": "日志文件不存在"})
        except Exception as e:
            return self._json_response(500, {"success": False, "error": str(e)})

    def _open_external_url(self, args, body, method):
        """使用系统默认浏览器打开外部 URL。"""
        url = args.get("url", "")
        if url and url.startswith(("http://", "https://")):
            import webbrowser
            webbrowser.open(url)
            return self._json_response(200, {"success": True})
        return self._json_response(400, {"success": False, "error": "invalid url"})

    def _get_proxy_mode(self, args, body, method):
        """获取当前代理模式 (global/process)。"""
        mode = genv.get("proxy_mode", "global")
        return self._json_response(200, {"success": True, "mode": mode})

    def _set_proxy_mode(self, args, body, method):
        """设置代理模式 (global/process)。"""
        mode = body.get("mode", "") if body else ""
        if mode not in ("global", "process"):
            return self._json_response(400, {"success": False, "error": "无效的模式，应为 global 或 process"})
        genv.set("proxy_mode", mode, True)
        self.logger.info(f"代理模式已切换为: {mode}")
        return self._json_response(200, {"success": True, "mode": mode})

    def _create_game_shortcut(self, args, body, method):
        """为指定游戏创建桌面快捷方式（通过工具启动）。"""
        game_id = body.get("game_id", "") if body else args.get("game_id", "")
        if not game_id:
            return self._json_response(400, {"success": False, "error": "缺少 game_id 参数"})
        
        game = self.game_helper.get_existing_game(game_id)
        if not game:
            return self._json_response(404, {"success": False, "error": f"未找到游戏: {game_id}"})
        
        # 尝试使用游戏路径作为图标来源
        icon_source = game.path if game.path and os.path.exists(game.path) else ""
        
        success = game.create_tool_launch_shortcut(icon_source)
        if success:
            return self._json_response(200, {"success": True, "message": "快捷方式创建成功"})
        else:
            return self._json_response(500, {"success": False, "error": "快捷方式创建失败"})

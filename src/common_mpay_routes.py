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

import json
import sys

import gevent
from flask import request, jsonify, Response
from envmgr import genv
from login_stack_mgr import LoginStackManager


LOGIN_METHODS = [
    {
        "name": "手机账号",
        "icon_url": "",
        "text_color": "",
        "hot": True,
        "type": 7,
        "icon_url_large": "",
    },
    {
        "name": "快速游戏",
        "icon_url": "",
        "text_color": "",
        "hot": True,
        "type": 2,
        "icon_url_large": "",
    },
    {
        "login_url": "",
        "name": "网易邮箱",
        "icon_url": "",
        "text_color": "",
        "hot": True,
        "type": 1,
        "icon_url_large": "",
    },
    {
        "login_url": "",
        "name": "扫码登录",
        "icon_url": "",
        "text_color": "",
        "hot": True,
        "type": 17,
        "icon_url_large": "",
    },
]

PC_INFO = {
    "extra_unisdk_data": "",
    "from_game_id": "h55",
    "src_app_channel": "netease",
    "src_client_ip": "",
    "src_client_type": 1,
    "src_jf_game_id": "h55",
    "src_pay_channel": "netease",
    "src_sdk_version": "3.15.0",
    "src_udid": "",
}


def register_mpay_routes(
    app,
    *,
    requestGetAsCv,
    requestPostAsCv,
    proxy,
    cv,
    login_style,
    game_helper,
    logger,
    app_channel_default="netease.wyzymnqsd_cps_dev",
    qrcode_app_channel_provider=None,
    create_login_query_hook=None,
    use_login_mapping_always=False,
    exchange_token_request=None,
):
    stack_mgr = LoginStackManager.get_instance()
    @app.route("/mpay/games/<game_id>/login_methods", methods=["GET"])
    def handle_login_methods(game_id):
        try:
            resp: Response = requestGetAsCv(request, cv)
            new_login_methods = resp.get_json()
            new_login_methods["entrance"] = [(LOGIN_METHODS)]
            new_login_methods["select_platform"] = True
            new_login_methods["qrcode_select_platform"] = True
            for i in new_login_methods["config"]:
                new_login_methods["config"][i]["select_platforms"] = [0, 1, 2, 3, 4]
            resp.set_data(json.dumps(new_login_methods))
            return resp
        except Exception:
            return proxy(request)

    @app.route("/mpay/api/users/login/mobile/finish", methods=["POST"])
    @app.route("/mpay/api/users/login/mobile/get_sms", methods=["POST"])
    @app.route("/mpay/api/users/login/mobile/verify_sms", methods=["POST"])
    @app.route("/mpay/games/<game_id>/devices/<device_id>/users", methods=["POST"])
    def handle_first_login(game_id=None, device_id=None):
        try:
            return requestPostAsCv(request, cv)
        except Exception:
            return proxy(request)

    @app.route("/mpay/games/<game_id>/devices/<device_id>/users/<user_id>", methods=["GET"])
    def handle_login(game_id, device_id, user_id):
        try:
            mapping = {
                "opt_fields": "nickname,avatar,realname_status,mobile_bind_status,exit_popup_info,mask_related_mobile,related_login_status,detect_is_new_user",
                "verify_status": "1",
                "login_for": "1",
                "gv": "251881013",
                "gvn": "2025.0707.1013",
                "sv": "35",
                "app_type": "games",
                "app_mode": "2",
                "app_channel": app_channel_default,
                "_cloud_extra_base64": "e30=",
                "sc": "1",
            }

            use_mapping = use_login_mapping_always
            if qrcode_app_channel_provider:
                qrcode_channel = qrcode_app_channel_provider(game_id)
                if qrcode_channel:
                    mapping["app_channel"] = qrcode_channel
                    use_mapping = True

            if use_mapping:
                resp: Response = requestGetAsCv(request, cv, mapping)
            else:
                resp: Response = requestGetAsCv(request, cv)

            new_devices = resp.get_json()
            new_devices["user"]["pc_ext_info"] = PC_INFO
            resp.set_data(json.dumps(new_devices))
            return resp
        except Exception:
            return proxy(request)

    @app.route("/mpay/api/qrcode/image", methods=["GET"])
    def handle_qrcode_image():
        try:
            resp = proxy(request)
            if genv.get("CLOUD_RES").get_risk_wm() != "":
                from riskWmUtils import wm
                resp.set_data(wm(resp.get_data(), genv.get("CLOUD_RES").get_risk_wm()))
                return resp
            return resp
        except Exception:
            return proxy(request)

    @app.route("/mpay/games/pc_config", methods=["GET"])
    def handle_pc_config():
        try:
            resp: Response = requestGetAsCv(request, cv)
            new_config = resp.get_json()
            new_config["game"]["config"]["cv_review_status"] = 1
            new_config["game"]["config"]["web_token_persist"] = True
            new_config["game"]["config"]["mobile_related_login"]["guide_related_mobile"] = True
            new_config["game"]["config"]["mobile_related_login"]["force_related_login"] = True
            new_config["game"]["config"]["login"]["login_style"] = login_style
            resp.set_data(json.dumps(new_config))
            return resp
        except Exception:
            return proxy(request)

    @app.route("/mpay/api/qrcode/create_login", methods=["GET"])
    def handle_create_login():
        try:
            query = request.args.to_dict()
            game_id = query["game_id"]
            process_id = query.get("process_id", "")
            if create_login_query_hook:
                create_login_query_hook(query, game_id)
            resp: Response = proxy(request, query)
            genv.set("CHANNEL_ACCOUNT_SELECTED", "")
            data = {
                "uuid": resp.get_json()["uuid"],
                "game_id": request.args["game_id"],
            }
            stack_mgr.push_cached_qrcode_data(game_id, process_id, data)
            stack_mgr.ensure_pending_stack(game_id)
            # auto login start
            if genv.get(f"auto-{request.args['game_id']}", "") != "":
                delay = game_helper.get_login_delay(request.args["game_id"])
                logger.info(f"即将自动登录，{delay}秒后开始扫码")
                uuid = genv.get(f"auto-{request.args['game_id']}")
                genv.set("CHANNEL_ACCOUNT_SELECTED", uuid)
                gevent.spawn_later(
                    delay,
                    genv.get("CHANNELS_HELPER").simulate_scan,
                    uuid,
                    data["uuid"],
                    data["game_id"],
                )
            new_config = resp.get_json()
            new_config["qrcode_scanners"][0]["url"] = "https://localhost/_idv-login/index?game_id=" + request.args["game_id"]
            return jsonify(new_config)
        except Exception:
            return proxy(request)

    @app.route("/mpay/api/qrcode/query", methods=["GET"])
    def handle_qrcode_query():
        if genv.get("CHANNEL_ACCOUNT_SELECTED"):
            return proxy(request)
        else:
            resp: Response = proxy(request)
            resp_json = resp.get_json()
            game_id = request.args.get("game_id", "")
            process_id = request.args.get("process_id", "")
            print(resp_json)
            if resp_json.get("code", -1) != -1:
                #1345
                stack_mgr.pop_cached_qrcode_data(game_id, process_id)
                logger.error(f"扫码登录失败，错误码：{resp_json.get('code', -1)}，信息：{resp_json.get('reason', '')}")
                pass
            qrCodeStatus = resp_json["qrcode"]["status"]
            if qrCodeStatus == 2 and genv.get("CHANNEL_ACCOUNT_SELECTED") == "":
                game_id = request.args.get("game_id", "")
                process_id = request.args.get("process_id", "")
                stack_mgr.push_pending_login_info(game_id, process_id, resp_json["login_info"])
            return resp

    @app.route("/mpay/api/users/login/qrcode/exchange_token", methods=['POST'])
    def handle_token_exchange():
        is_selected = bool(genv.get("CHANNEL_ACCOUNT_SELECTED"))
        form_data = {}
        try:
            # 尝试读取 form 数据
            form_data = request.form.to_dict()
            logger.debug(f"数据上传内容: {form_data}")
        except Exception as e:
            logger.error(f"解析上传数据失败: {e}")

        game_id = request.args.get("game_id", "") or form_data.get("game_id", "")
        process_id = request.args.get("process_id", "")

        if exchange_token_request:
            resp = exchange_token_request(is_selected, game_id, form_data)
        else:
            resp = proxy(request)

        if is_selected:
            if resp.status_code == 200 and game_helper.get_auto_close_setting(game_id):
                logger.info("检测到登录已完成请求，即将自动关闭程序...")
                # 使用 gevent 延迟退出，确保响应能够正常返回
                gevent.spawn_later(3, sys.exit, 0)
        else:
            if resp.status_code == 200:
                pending_login_info = stack_mgr.pop_pending_login_info(game_id, process_id)
                if pending_login_info:
                    genv.get("CHANNELS_HELPER").import_from_scan(
                        pending_login_info, resp.get_json()
                    )
        return resp

    @app.route("/mpay/api/qrcode/<path>", methods=["POST"])
    @app.route("/mpay/api/reverify/<path>")
    @app.route("/mpay/api/qrcode/<path>", methods=["GET"])
    def handle_qrcode(path):
        return proxy(request)

    @app.route("/mpay/api/data/upload", methods=["POST"])
    def handle_data_upload():
        """处理数据上传请求"""
        # 先正常转发请求
        resp = proxy(request)
        try:
            # 尝试读取 form 数据
            form_data = request.form.to_dict()
            logger.debug(f"数据上传内容: {form_data}")
        except Exception as e:
            logger.error(f"解析上传数据失败: {e}")
            return resp
        # 请求完成后检查是否需要自动关闭
        game_id = form_data.get("game_id", "")
        if game_helper.get_auto_close_setting(game_id):
            logger.info("检测到登录已完成请求，即将自动关闭程序...")
            # 使用 gevent 延迟退出，确保响应能够正常返回
            gevent.spawn_later(3, sys.exit, 0)

        return resp

    @app.route("/<path:path>", methods=["GET", "POST"])
    def globalProxy(path):
        if request.method == "GET":
            return requestGetAsCv(request, cv)
        else:
            return requestPostAsCv(request, cv)

    @app.route("/api/games/pc/config", methods=["GET"])
    def handle_oversea_config():
        resp = proxy(request)
        new_config = resp.get_json()
        for i in new_config["game_config"]["account_type"].values():
            i["disable_login"] = False
            i["enable"] = True
        new_config["game_config"]["platform_cross"] = True
        new_config["game_config"]["quick_login"]["show_role"] = True
        new_config["game_config"]["quick_login"]["enable"] = True
        resp.set_data(json.dumps(new_config))
        return resp

    def pop_pending_login_info(game_id, process_id=None):
        return stack_mgr.pop_pending_login_info(game_id, process_id)

    return pop_pending_login_info


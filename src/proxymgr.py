# coding=UTF-8
"""
 Copyright (c) 2024 Alexander-Porter & fwilliamhe

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


from flask import Flask, request, Response, jsonify
from gevent import pywsgi
from envmgr import genv
from logutil import setup_logger

import socket
import requests
import json
import os
import psutil
import const
import subprocess


app = Flask(__name__)
logger=setup_logger(__name__)


loginMethod = [
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
pcInfo = {
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

g_req = requests.session()
g_req.trust_env = False


def requestGetAsCv(request, cv):
    query = request.args.copy()
    if cv:
        query["cv"] = cv
    resp = g_req.request(
        method=request.method,
        url=genv.get("URI_REMOTEIP") + request.path,
        params=query,
        headers=request.headers,
        cookies=request.cookies,
        allow_redirects=False,
        verify=False,
    )
    excluded_headers = [
        "content-encoding",
        "content-length",
        "transfer-encoding",
        "connection",
    ]
    headers = [
        (name, value)
        for (name, value) in resp.raw.headers.items()
        if name.lower() not in excluded_headers
    ]
    return Response(resp.text, resp.status_code, headers)


def proxy(request):
    query = request.args.copy()
    new_body = request.get_data(as_text=True)
    # 向目标服务发送代理请求
    resp = requests.request(
        method=request.method,
        url=genv.get("URI_REMOTEIP") + request.path,
        params=query,
        headers=request.headers,
        data=new_body,
        cookies=request.cookies,
        allow_redirects=False,
        verify=False,
    )
    app.logger.info(resp.url)
    # 构造代理响应
    excluded_headers = [
        "content-encoding",
        "content-length",
        "transfer-encoding",
        "connection",
    ]
    headers = [
        (name, value)
        for (name, value) in resp.raw.headers.items()
        if name.lower() not in excluded_headers
    ]

    response = Response(resp.content, resp.status_code, headers)
    return response


def requestPostAsCv(request, cv):
    query = request.args.copy()
    if cv:
        query["cv"] = cv
    try:
        new_body = request.get_json()
        new_body["cv"] = cv
        new_body.pop("arch", None)
    except:
        new_body = dict(x.split("=") for x in request.get_data(as_text=True).split("&"))
        new_body["cv"] = cv
        new_body.pop("arch", None)
        new_body = "&".join([f"{k}={v}" for k, v in new_body.items()])

    app.logger.info(new_body)
    resp = g_req.request(
        method=request.method,
        url=genv.get("URI_REMOTEIP") + request.path,
        params=query,
        data=new_body,
        headers=request.headers,
        cookies=request.cookies,
        allow_redirects=False,
        verify=False,
    )
    excluded_headers = [
        "content-encoding",
        "content-length",
        "transfer-encoding",
        "connection",
    ]
    headers = [
        (name, value)
        for (name, value) in resp.raw.headers.items()
        if name.lower() not in excluded_headers
    ]
    return Response(resp.text, resp.status_code, headers)


@app.route("/mpay/games/<game_id>/login_methods", methods=["GET"])
def handle_login_methods(game_id):
    try:
        resp: Response = requestGetAsCv(request, "i4.7.0")
        new_login_methods = resp.get_json()
        new_login_methods["entrance"] = [(loginMethod)]
        new_login_methods["select_platform"] = True
        new_login_methods["qrcode_select_platform"] = True
        for i in new_login_methods["config"]:
            new_login_methods["config"][i]["select_platforms"] = [0, 1, 2, 3, 4]
        resp.set_data(json.dumps(new_login_methods))
        return resp
    except:
        return proxy(request)


@app.route("/mpay/api/users/login/mobile/finish", methods=["POST"])
@app.route("/mpay/api/users/login/mobile/get_sms", methods=["POST"])
@app.route("/mpay/api/users/login/mobile/verify_sms", methods=["POST"])
@app.route("/mpay/games/<game_id>/devices/<device_id>/users", methods=["POST"])
def handle_first_login(game_id=None, device_id=None):
    try:
        return requestPostAsCv(request, "i4.7.0")
    except:
        return proxy(request)


@app.route("/mpay/games/<game_id>/devices/<device_id>/users/<user_id>", methods=["GET"])
def handle_login(game_id, device_id, user_id):
    try:
        resp: Response = requestGetAsCv(request, "i4.7.0")
        new_devices = resp.get_json()
        new_devices["user"]["pc_ext_info"] = pcInfo
        resp.set_data(json.dumps(new_devices))
        return resp
    except:
        return proxy(request)


@app.route("/mpay/games/pc_config", methods=["GET"])
def handle_pc_config():
    try:
        resp: Response = requestGetAsCv(request, "i4.7.0")
        new_config = resp.get_json()
        new_config["game"]["config"]["cv_review_status"] = 1
        resp.set_data(json.dumps(new_config))
        return resp
    except:
        return proxy(request)


@app.route("/mpay/api/qrcode/create_login", methods=["GET"])
def handle_create_login():
    try:
        resp: Response = proxy(request)
        genv.set("CHANNEL_ACCOUNT_SELECTED", "")
        data={
            "uuid":resp.get_json()["uuid"],
            "game_id":request.args["game_id"]
        }
        genv.set("CACHED_QRCODE_DATA",data)
        genv.set("pending_login_info",None)
        #auto login start
        if genv.get(f"auto-{request.args['game_id']}","")!="":
            genv.get("CHANNELS_HELPER").simulate_scan(genv.get(f"auto-{request.args['game_id']}"),data["uuid"],data["game_id"])
        new_config = resp.get_json()
        new_config["qrcode_scanners"][0]["url"] = "https://localhost/_idv-login/index?game_id="+request.args["game_id"]
        return jsonify(new_config)
    except:
        return proxy(request)

@app.route("/_idv-login/manualChannels",methods=["GET"])
def _manual_list():
    return jsonify(const.manual_login_channels)

@app.route("/_idv-login/list", methods=["GET"])
def _list_channels():
    try:
        body=genv.get("CHANNELS_HELPER").list_channels(request.args["game_id"])
    except Exception as e:
        body = {
            "error": str(e)
        }
    return jsonify(body)

@app.route("/_idv-login/switch", methods=["GET"])
def _switch_channel():
    genv.set("CHANNEL_ACCOUNT_SELECTED",request.args["uuid"])
    if genv.get("CACHED_QRCODE_DATA"):
         data=genv.get("CACHED_QRCODE_DATA")
         genv.get("CHANNELS_HELPER").simulate_scan(request.args["uuid"],data["uuid"],data["game_id"])
    #debug only
    else:
        genv.get("CHANNELS_HELPER").simulate_scan(request.args["uuid"],"Kinich","aecfrt3rmaaaaajl-g-h55")
    return {"current":genv.get("CHANNEL_ACCOUNT_SELECTED")}

@app.route("/_idv-login/del", methods=["GET"])
def _del_channel():
    resp={
        "success":genv.get("CHANNELS_HELPER").delete(request.args["uuid"])
    }
    return jsonify(resp)

@app.route("/_idv-login/rename", methods=["GET"])
def _rename_channel():
    resp={
        "success":genv.get("CHANNELS_HELPER").rename(request.args["uuid"],request.args["new_name"])
    }
    return jsonify(resp)

@app.route("/_idv-login/import", methods=["GET"])
def _import_channel():
    resp={
        "success":genv.get("CHANNELS_HELPER").manual_import(request.args["channel"],request.args["game_id"])
    }
    return jsonify(resp)

@app.route("/_idv-login/setDefault", methods=["GET"])
def _set_default_channel():
    try:
        genv.set(f"auto-{request.args['game_id']}",request.args["uuid"],True)
        resp={
            "success":True,
        }
    except:
        logger.error("设置默认账号失败",exc_info=True,stack_info=True)
        resp={
            "success":False,
        }
    return jsonify(resp)

@app.route("/_idv-login/clearDefault", methods=["GET"])
def _clear_default_channel():
    try:
        genv.set(f"auto-{request.args['game_id']}","",True)
        resp={
            "success":True,
        }
    except:
        resp={
            "success":False,
        }
    return jsonify(resp)


@app.route("/_idv-login/defaultChannel", methods=["GET"])
def get_default():
    uuid=genv.get(f"auto-{request.args['game_id']}","")
    if uuid=="":
        return jsonify({"uuid":""})
    elif genv.get("CHANNELS_HELPER").query_channel(uuid)==None:
        genv.set(f"auto-{request.args['game_id']}","",True)
        return jsonify({"uuid":""})
    else:
        return jsonify({"uuid":uuid})


@app.route("/_idv-login/index",methods=['GET'])
def _handle_switch_page():
    return Response(const.html)

@app.route("/mpay/api/qrcode/query", methods=["GET"])
def handle_qrcode_query():
    if genv.get("CHANNEL_ACCOUNT_SELECTED"):
        return proxy(request)
    else:
        resp: Response = proxy(request)
        qrCodeStatus = resp.get_json()["qrcode"]["status"]
        if qrCodeStatus == 2 and genv.get("CHANNEL_ACCOUNT_SELECTED") == "":
            genv.set("pending_login_info", resp.get_json()["login_info"])
        return resp

@app.route("/mpay/api/users/login/qrcode/exchange_token", methods=['POST'])
def handle_token_exchange():
    if genv.get("CHANNEL_ACCOUNT_SELECTED"):
        logger.info(f"尝试登录{genv.get('CHANNEL_ACCOUNT_SELECTED')}")
        return  proxy(request)
    else:
        logger.info(f"捕获到渠道服登录Token.")
        resp: Response = proxy(request)
        if resp.status_code == 200:
            if genv.get("pending_login_info"):
                genv.get("CHANNELS_HELPER").import_from_scan(
                    genv.get("pending_login_info"), resp.get_json()
                )
        return resp

@app.route("/mpay/api/qrcode/<path>", methods=["POST"])
@app.route("/mpay/api/reverify/<path>")
@app.route("/mpay/api/qrcode/<path>", methods=["GET"])
def handle_qrcode(path):
    logger.info(f"UNCHANGED {request.url}")
    return proxy(request)


@app.route("/<path:path>", methods=["GET", "POST"])
def globalProxy(path):
    if request.method == "GET":
        return requestGetAsCv(request, "i4.7.0")
    else:
        return requestPostAsCv(request, "i4.7.0")

@app.before_request
def before_request_func():
    if request.method == "POST":
        logger.debug(f"请求 {request.method} {request.path} {request.args} {request.get_data(as_text=True)}")
    else:
        logger.debug(f"请求 {request.method} {request.path} {request.args}")
@app.after_request
def after_request_func(response):
    if request.content_type == "application/json":
        logger.debug(f"发送 {response.status} {response.headers} {response.get_json()}")
    return response

class proxymgr:
    def __init__(self) -> None:
        genv.set("CHANNEL_ACCOUNT_SELECTED", "")
        genv.set("CACHED_QRCODE_DATA",{})
        genv.set("pending_login_info",None)
        

    def check_port(self):
        with os.popen('netstat -ano | findstr ":443"') as r:
            r = r.read().split("\n")
        for cur in r:
            info = [i for i in cur.split(" ") if i != ""]
            if len(info) > 4:
                if info[1].find(":443") != -1:
                    t_pid = info[4]
                    try:
                        readable_exe_name=psutil.Process(int(t_pid)).exe()
                    except:
                        readable_exe_name="未知程序"
                        logger.warning(f"读取进程{t_pid}的可执行文件名失败！原始输出为{r}")
                    logger.warning(f"警告 : {readable_exe_name} (pid={t_pid}) 已经占用了443端口，是否强行终止该程序？ 按回车继续。")
                    input()
                    if t_pid=='4':
                        subprocess.check_call(
                            ['net','stop','http','/y'],
                            shell=True
                            )
                    else:
                        subprocess.check_call(
                            ["taskkill", "/f", "/im", t_pid],
                            shell=True
                        )

                    break

    def run(self):
        from dnsmgr import DNSResolver

        resolver = DNSResolver()
        target = resolver.gethostbyname(genv.get("DOMAIN_TARGET"))
        logger.info(target)
        
        # result check
        try:
            if (
                target == None
                or g_req.get(f"https://{target}", verify=False).status_code != 200
            ):
                logger.warning(
                    "警告 : DNS解析失败，将使用硬编码的IP地址！（如果你是海外/加速器/VPN用户，出现这条消息是正常的，您不必太在意）"
                )
                target = "42.186.193.21"
        except:
            logger.warning(
                "警告 : DNS解析失败，将使用硬编码的IP地址！（如果你是海外/加速器/VPN用户，出现这条消息是正常的，您不必太在意）"
            )
            target = "42.186.193.21"

        genv.set("URI_REMOTEIP", f"https://{target}")
        self.check_port()
        server = pywsgi.WSGIServer(
                listener=("127.0.0.1", 443),
                certfile=genv.get("FP_WEBCERT"),
                keyfile=genv.get("FP_WEBKEY"),
                application=app,
            )
        if socket.gethostbyname(genv.get("DOMAIN_TARGET")) == "127.0.0.1":
            logger.info("拦截成功! 您现在可以打开游戏了")
            logger.warn("如果您在之前已经打开了游戏，请关闭游戏后重新打开，否则工具不会生效！")
            logger.info("登入账号且已经··进入游戏··后，您可以关闭本工具。")

            server.serve_forever()
            return True
        else:
            logger.error("检测拦截目标域名失败！依旧打开服务器，请打开游戏确认拦截是否生效！")
            server.serve_forever()
            return False

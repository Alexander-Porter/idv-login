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


from collections import deque
import hypercorn
import logging
import hypercorn.run
from quart import Quart, Request, request, Response, jsonify

from envmgr import genv
from logutil import setup_logger
import socket
import json
import os
import psutil
import const
import subprocess
import aiohttp
from aiohttp import ClientSession
import asyncio
from hypercorn.asyncio import serve
from hypercorn.config import Config

app = Quart(__name__)
logger = setup_logger()
import logging

# 设置日志格式
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 配置 aiohttp.client 日志
client_log = logging.getLogger("aiohttp.client")
client_log.setLevel(logging.DEBUG)  # 只捕获 ClientSession 的日志

# 控制台输出日志
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
client_log.addHandler(console_handler)

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

g_session: ClientSession = None


async def requestGetAsCv(request, cv):
    query = request.args.copy()
    if cv:
        query["cv"] = cv

    async with g_session.request(
        method=request.method,
        url=genv.get("URI_REMOTEIP") + request.path,
        params=query,
        headers=dict(request.headers),
        cookies=dict(request.cookies),
        ssl=False,
    ) as resp:
        excluded_headers = [
            "content-encoding",
            "content-length",
            "transfer-encoding",
            "connection",
        ]
        headers = [
            (name, value)
            for (name, value) in resp.headers.items()
            if name.lower() not in excluded_headers
        ]
        content = await resp.read()
        return Response(content, resp.status, headers)


async def requestPostAsCv(request, cv):
    query = request.args.copy()
    content_type="application/x-www-form-urlencoded"
    if cv:
        query["cv"] = cv
    try:
        new_body = await request.get_json()
        new_body["cv"] = cv
        new_body.pop("arch", None)
        content_type="application/json"
    except Exception as e:
        req_data = await request.get_data(as_text=True)
        new_body = dict(x.split("=") for x in req_data.split("&"))
        new_body["cv"] = cv
        new_body.pop("arch", None)
        new_body = "&".join([f"{k}={v}" for k, v in new_body.items()])
        logger.info(f"Request body after modification: {new_body}")
        logger.error(f"Failed to parse request body: {e}")
    logger.info("What!"+new_body)
    req_headers=dict(request.headers)
    req_headers["Content-Type"]=content_type
    resp = None
    try:
        async with g_session.request(
            method=request.method,
            url=genv.get("URI_REMOTEIP") + request.path,
            params=query,
            data=new_body,
            headers=req_headers,
            cookies=dict(request.cookies),
            ssl=False
        ) as resp:
            excluded_headers = [
                "content-encoding",
                "content-length",
                "transfer-encoding",
                "connection",
            ]
            headers = [
                (name, value)
                for (name, value) in resp.headers.items()
                if name.lower() not in excluded_headers
            ]
            content = await resp.text()
            logger.info(content)
            logger.info(headers)
            return Response(content, resp.status, headers)
    except Exception as e:
        logger.exception(e)
        if resp:
            return Response("111", resp.status, headers)
        else:
            return Response("111", 500)

async def proxy(request: Request) -> Response:
    query = request.args.copy()
    new_body = await request.get_data(as_text=True)

    async with g_session.request(
        method=request.method,
        url=genv.get("URI_REMOTEIP") + request.path,
        params=query,
        headers=dict(request.headers),
        data=new_body,
        cookies=dict(request.cookies),
        ssl=False,
    ) as resp:
        excluded_headers = [
            "content-encoding",
            "content-length",
            "transfer-encoding",
            "connection",
        ]
        headers = [
            (name, value)
            for (name, value) in resp.headers.items()
            if name.lower() not in excluded_headers
        ]
        content = await resp.read()
        return Response(content, resp.status, headers)


@app.route("/mpay/games/<game_id>/login_methods", methods=["GET"])
async def handle_login_methods(game_id):
    try:
        resp: Response = await requestGetAsCv(request, "i4.7.0")
        new_login_methods = await resp.get_json()
        new_login_methods["entrance"] = [(loginMethod)]
        new_login_methods["select_platform"] = True
        new_login_methods["qrcode_select_platform"] = True
        for i in new_login_methods["config"]:
            new_login_methods["config"][i]["select_platforms"] = [0, 1, 2, 3, 4]
        resp.set_data(json.dumps(new_login_methods))
        logger.info("Oh my login!")
        return resp
    except:
        return await proxy(request)


@app.route("/mpay/api/users/login/mobile/finish", methods=["POST"])
@app.route("/mpay/api/users/login/mobile/get_sms", methods=["POST"])
@app.route("/mpay/api/users/login/mobile/verify_sms", methods=["POST"])
@app.route("/mpay/games/<game_id>/devices/<device_id>/users", methods=["POST"])
async def handle_first_login(game_id=None, device_id=None):
    try:
        logger.info("In!")
        return await requestPostAsCv(request, "i4.7.0")
    except Exception as e:
        logger.exception(e)
        return await proxy(request)


@app.route("/mpay/games/<game_id>/devices/<device_id>/users/<user_id>", methods=["GET"])
async def handle_login(game_id, device_id, user_id):
    try:
        resp: Response = await requestGetAsCv(request, "i4.7.0")
        new_devices = await resp.get_json()
        new_devices["user"]["pc_ext_info"] = pcInfo
        resp.set_data(json.dumps(new_devices))
        return resp
    except:
        return await proxy(request)


@app.route("/mpay/games/pc_config", methods=["GET"])
async def handle_pc_config():
    try:
        resp: Response = await requestGetAsCv(request, "i4.7.0")
        new_config = await resp.get_json()
        new_config["game"]["config"]["cv_review_status"] = 1
        resp.set_data(json.dumps(new_config))
        logger.info("Oh my login")
        return resp
    except:
        return await proxy(request)


@app.route("/mpay/api/qrcode/create_login", methods=["GET"])
async def handle_create_login():
    try:
        resp: Response = await proxy(request)
        genv.set("CHANNEL_ACCOUNT_SELECTED", "")
        data = {
            "uuid": (await resp.get_json())["uuid"],
            "game_id": request.args["game_id"],
        }
        logger.debug(await resp.get_json())
        cached_qrcode_data_queue = genv.get("CACHED_QRCODE_DATA_QUEUE")
        cached_qrcode_data_queue.append(data)
        genv.set("pending_login_info", None)
        # auto login start
        if genv.get(f"auto-{request.args['game_id']}", "") != "":
            uuid = genv.get(f"auto-{request.args['game_id']}")
            genv.set("CHANNEL_ACCOUNT_SELECTED", uuid)
            import asyncio

            asyncio.create_task(
                genv.get("CHANNELS_HELPER").simulate_scan(
                    uuid, data["uuid"], data["game_id"]
                )
            )

        new_config = await resp.get_json()
        new_config["qrcode_scanners"][0]["url"] = (
            "https://localhost/_idv-login/index?game_id=" + request.args["game_id"]
        )
        return jsonify(new_config)
    except:
        return await proxy(request)


@app.route("/_idv-login/manualChannels", methods=["GET"])
def _manual_list():
    return jsonify(const.manual_login_channels)


@app.route("/_idv-login/list", methods=["GET"])
def _list_channels():
    try:
        body = genv.get("CHANNELS_HELPER").list_channels(request.args["game_id"])
    except Exception as e:
        body = {"error": str(e)}
    return jsonify(body)


@app.route("/_idv-login/switch", methods=["GET"])
def _switch_channel():
    genv.set("CHANNEL_ACCOUNT_SELECTED", request.args["uuid"])
    if genv.get("CACHED_QRCODE_DATA_QUEUE"):
        cached_qrcode_data_queue: deque = genv.get("CACHED_QRCODE_DATA_QUEUE")
        data = cached_qrcode_data_queue.popleft()
        if not genv.get("CHANNELS_HELPER").simulate_scan(
            request.args["uuid"], data["uuid"], data["game_id"]
        ):
            logger("二维码登录失败，二维码信息已放入队列")
            cached_qrcode_data_queue.appendleft(data)
    # debug only
    else:
        genv.get("CHANNELS_HELPER").simulate_scan(
            request.args["uuid"], "Kinich", "aecfrt3rmaaaaajl-g-g37"
        )
    return {"current": genv.get("CHANNEL_ACCOUNT_SELECTED")}


@app.route("/_idv-login/del", methods=["GET"])
def _del_channel():
    resp = {"success": genv.get("CHANNELS_HELPER").delete(request.args["uuid"])}
    return jsonify(resp)


@app.route("/_idv-login/rename", methods=["GET"])
def _rename_channel():
    resp = {
        "success": genv.get("CHANNELS_HELPER").rename(
            request.args["uuid"], request.args["new_name"]
        )
    }
    return jsonify(resp)


@app.route("/_idv-login/import", methods=["GET"])
def _import_channel():
    import asyncio

    asyncio.run(
        genv.get("CHANNELS_HELPER").manual_import(
            request.args["channel"], request.args["game_id"]
        )
    )
    return jsonify({"success": True})


@app.route("/_idv-login/setDefault", methods=["GET"])
def _set_default_channel():
    try:
        genv.set(f"auto-{request.args['game_id']}", request.args["uuid"], True)
        resp = {
            "success": True,
        }
    except:
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
    except:
        resp = {
            "success": False,
        }
    return jsonify(resp)


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


@app.route("/_idv-login/index", methods=["GET"])
def _handle_switch_page():
    return Response(const.html)


@app.route("/mpay/api/qrcode/query", methods=["GET"])
async def handle_qrcode_query():
    if genv.get("CHANNEL_ACCOUNT_SELECTED"):
        return await proxy(request)
    else:
        resp: Response = await proxy(request)
        qrCodeStatus = (await resp.get_json())["qrcode"]["status"]
        if qrCodeStatus == 2 and genv.get("CHANNEL_ACCOUNT_SELECTED") == "":
            genv.set("pending_login_info", (await resp.get_json())["login_info"])
        return resp


@app.route("/mpay/api/users/login/qrcode/exchange_token", methods=["POST"])
async def handle_token_exchange():
    if genv.get("CHANNEL_ACCOUNT_SELECTED"):
        logger.info(f"尝试登录{genv.get('CHANNEL_ACCOUNT_SELECTED')}")
        return await proxy(request)
    else:
        logger.info(f"捕获到渠道服登录Token.")
        resp: Response = await proxy(request)
        if resp.status_code == 200:
            if genv.get("pending_login_info"):
                genv.get("CHANNELS_HELPER").import_from_scan(
                    genv.get("pending_login_info"), resp.get_json()
                )
        return resp


@app.route("/mpay/api/qrcode/<path>", methods=["POST"])
@app.route("/mpay/api/reverify/<path>")
@app.route("/mpay/api/qrcode/<path>", methods=["GET"])
async def handle_qrcode(path):
    return await proxy(request)


@app.before_request
async def before_request_func():
    # 读取hosts，如果是某个特定域名，则直接返回
    if request.host == genv.get("MI_DOMAIN"):
        logger.info(f"请求 {request.url} {request.headers}")
        query = request.args.copy()
        new_body = await request.get_data(as_text=True)
        # 向目标服务发送代理请求
        async with g_session.request(
            method=request.method,
            url=genv.get("MI_IP") + request.path,
            params=query,
            headers=dict(request.headers),
            data=new_body,
            cookies=dict(request.cookies),
            ssl=False,
        ) as resp:
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
                for (name, value) in resp.headers.items()
                if name.lower() not in excluded_headers
            ]

            content = await resp.read()
            return Response(content, resp.status, headers)
    else:
        return None


@app.before_serving
async def before_serving():
    global g_session
    g_session = aiohttp.ClientSession()


@app.after_serving
async def after_serving():
    if g_session:
        await g_session.close()


@app.after_request
async def after_request_func(response: Response):
    # 只log出现错误的请求
    if (
        response.status_code != 200
        and response.status_code != 302
        and response.status_code != 301
        and response.status_code != 304
    ):
        if response.status_code == 404:
            if ".ico" in request.url:
                return response
        logger.error(f"请求 {request.url} {request.headers} {(await request.get_data()).decode()}")
        logger.error(f"发送 {response.status} {response.headers} {(await response.get_data()).decode()}")
    else:
        logger.debug(f"请求 {request.url} {response.status}")
    return response

@app.route("/<path:path>", methods=["GET", "POST"])
async def globalProxy(path):
    if request.method == "GET":
        return await requestGetAsCv(request, "i4.7.0")
    else:
        return await requestPostAsCv(request, "i4.7.0")

class proxymgr:
    def __init__(self) -> None:
        genv.set("CHANNEL_ACCOUNT_SELECTED", "")
        if not genv.get("CACHED_QRCODE_DATA_QUEUE"):
            genv.set("CACHED_QRCODE_DATA_QUEUE", deque())
        genv.set("pending_login_info", None)

    def check_port(self):
        def is_port_in_use(port, host="127.0.0.1"):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind((host, port))
                    return False  # 端口未被占用
                except socket.error:
                    return True  # 端口被占用

        if is_port_in_use(443):
            with os.popen('netstat -ano | findstr ":443"') as netstat_output:
                netstat_output = netstat_output.read().split("\n")
            for cur in netstat_output:
                info = [i for i in cur.split(" ") if i != ""]
                if len(info) > 4:
                    if info[1].find(":443") != -1:
                        t_pid = info[4]
                        try:
                            readable_exe_name = psutil.Process(int(t_pid)).exe()
                        except psutil.AccessDenied:
                            readable_exe_name = "权限不足"
                            logger.warning(
                                f"读取进程{t_pid}的可执行文件名失败！权限不足。"
                            )
                            return
                        logger.warning(
                            f"警告 : {readable_exe_name} (pid={t_pid}) 已经占用了443端口，是否强行终止该程序？ 按回车继续。"
                        )
                        input()
                        if t_pid == "4":
                            subprocess.check_call(
                                ["net", "stop", "http", "/y"], shell=True
                            )
                        else:
                            subprocess.check_call(
                                ["taskkill", "/f", "/pid", t_pid], shell=True
                            )
                        break

    def run(self):
        from dnsmgr import DNSResolver

        resolver = DNSResolver()

        async def check_target(domain, target):
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(
                        f"https://{target}", ssl=False, headers={"Host": domain}
                    ) as resp:
                        return resp.status == 200
                except:
                    return False

        def resolve_target(domain, default_address):
            target = resolver.gethostbyname(domain)
            logger.info(target)

            # result check
            import asyncio

            if target is None or not asyncio.run(check_target(domain, target)):
                logger.warning(
                    "警告 : DNS解析失败，将使用硬编码的IP地址！（如果你是海外/加速器/VPN用户，出现这条消息是正常的，您不必太在意）"
                )
                target = default_address
            return target

        genv.set(
            "URI_REMOTEIP",
            "https://" + resolve_target(genv.get("DOMAIN_TARGET"), "42.186.193.21"),
        )
        genv.set(
            "MI_IP", "https://" + resolve_target(genv.get("MI_DOMAIN"), "39.156.81.45")
        )

        self.check_port()
        # 创建一个空日志
        import logging

        web_logger = logging.getLogger("web")
        web_logger.setLevel(logging.WARN)

        if socket.gethostbyname(genv.get("DOMAIN_TARGET")) == "127.0.0.1":
            logger.info("拦截成功! 您现在可以打开游戏了")
            logger.warning(
                "如果您在之前已经打开了游戏，请关闭游戏后重新打开，否则工具不会生效！"
            )
            logger.info("登入账号且已经··进入游戏··后，您可以关闭本工具。")


            # 配置 Hypercorn
            config = Config()
            config.bind = ["127.0.0.1:443"]
            config.certfile = genv.get("FP_WEBCERT")
            config.keyfile = genv.get("FP_WEBKEY")
            

            asyncio.run(serve(app, config))
            
            return True
        else:
            logger.error("检测拦截目标域名失败！请将程序加入杀毒软件白名单后重试。")
            return False

    async def cleanup(self):
        await g_session.close()

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


import sys
from flask import Flask, request, Response
from gevent import pywsgi
import gevent
from envmgr import genv
from logutil import setup_logger
from gamemgr import GameManager
import socket
import requests
import os
import psutil
import subprocess
from common_routes import register_common_idv_routes
from common_mpay_routes import register_mpay_routes
from login_stack_mgr import LoginStackManager


app = Flask(__name__)
game_helper = GameManager()
logger = setup_logger()


g_req = requests.session()
g_req.trust_env = False


def _get_remote_base(request):
    host = request.host.split(":")[0] if request.host else ""
    if host == genv.get("DOMAIN_TARGET_OVERSEA"):
        return genv.get("URI_REMOTEIP_OVERSEA")
    return genv.get("URI_REMOTEIP")


def requestGetAsCv(request, cv, body_mapping={}):

    query = request.args.copy()
    if cv:
        query["cv"] = cv
    for k, v in body_mapping.items():
        query[k] = v
    remote_base = _get_remote_base(request)
    resp = g_req.request(
        method=request.method,
        url=remote_base + request.path,
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


def proxy(request, query={}):
    if query == {}:
        query = request.args.copy()
    new_body = request.get_data(as_text=True)
    remote_base = _get_remote_base(request)
    # 向目标服务发送代理请求
    resp = requests.request(
        method=request.method,
        url=remote_base + request.path,
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


def requestPostAsCv(request, cv, body_mapping={}):

    query = request.args.copy()
    if cv:
        query["cv"] = cv
    try:
        new_body = request.get_json()
        new_body["cv"] = cv
        new_body.pop("arch", None)
        for k, v in body_mapping.items():
            new_body[k] = v
    except:
        new_body = dict(x.split("=") for x in request.get_data(as_text=True).split("&"))
        new_body["cv"] = cv
        new_body.pop("arch", None)
        for k, v in body_mapping.items():
            new_body[k] = v
        new_body = "&".join([f"{k}={v}" for k, v in new_body.items()])

    app.logger.info(new_body)
    remote_base = _get_remote_base(request)
    resp = g_req.request(
        method=request.method,
        url=remote_base + request.path,
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


def _create_login_query_hook(query, game_id):
    # 设置二维码登录的渠道类型和其他必要参数
    query["qrcode_channel_type"] = "3"
    query["gv"] = "251881013"
    query["gvn"] = "2025.0707.1013"
    query["cv"] = "i4.7.0"
    query["sv"] = "35"
    query["app_type"] = "games"
    query["app_mode"] = "2"
    query["app_channel"] = "netease.wyzymnqsd_cps_dev"
    query["_cloud_extra_base64"] = "e30="
    query["sc"] = "1"


def _exchange_token_request(is_selected, game_id, form_data):
    return proxy(request)


register_common_idv_routes(
    app,
    game_helper=game_helper,
    logger=logger,
)

register_mpay_routes(
    app,
    requestGetAsCv=requestGetAsCv,
    requestPostAsCv=requestPostAsCv,
    proxy=proxy,
    cv="i4.7.0",
    login_style=2,
    game_helper=game_helper,
    logger=logger,
    app_channel_default="netease.wyzymnqsd_cps_dev",
    create_login_query_hook=_create_login_query_hook,
    use_login_mapping_always=True,
    exchange_token_request=_exchange_token_request,
)


@app.after_request
def after_request_func(response: Response):
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
        logger.error(
            f"请求 {request.url} {request.headers} {request.get_data().decode()}"
        )
        logger.error(
            f"发送 {response.status} {response.headers} {response.get_data().decode()}"
        )
    else:
        logger.debug(f"请求 {request.url} {response.status}")
    return response


class macProxyMgr:
    def __init__(self) -> None:
        genv.set("CHANNEL_ACCOUNT_SELECTED", "")
        LoginStackManager.get_instance().reset()

    def check_port(self):
        def is_port_in_use(port, host="127.0.0.1"):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind((host, port))
                    return False  # 端口未被占用
                except socket.error:
                    return True  # 端口被占用

        if is_port_in_use(443):
            # 根据操作系统选择不同的netstat命令
            if sys.platform == "win32":
                # Windows
                with os.popen('netstat -ano | findstr ":443"') as netstat_output:
                    netstat_output = netstat_output.read().split("\n")
            elif sys.platform == "darwin":
                # macOS
                with os.popen("lsof -i :443 -sTCP:LISTEN") as netstat_output:
                    netstat_output = netstat_output.read().split("\n")
            else:
                # Linux
                with os.popen("lsof -i :443 -sTCP:LISTEN") as netstat_output:
                    netstat_output = netstat_output.read().split("\n")

            for cur in netstat_output:
                info = [i for i in cur.split() if i != ""]
                if sys.platform == "win32":
                    # Windows netstat 输出格式
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
                            try:
                                if t_pid == "4":
                                    subprocess.check_call(
                                        ["net", "stop", "http", "/y"], shell=True
                                    )
                                else:
                                    subprocess.check_call(
                                        ["taskkill", "/f", "/pid", t_pid], shell=True
                                    )
                                gevent.sleep(3)
                            except subprocess.CalledProcessError as e:
                                logger.warning(f"终止进程{t_pid}时发生错误: {e}")
                            except Exception as e:
                                logger.warning(f"终止进程{t_pid}时发生未知错误: {e}")
                            break
                else:
                    # macOS 和 Linux lsof 输出格式
                    # lsof格式: COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME
                    # 跳过表头并验证是否包含443端口
                    if len(info) > 1 and info[0] != "COMMAND":
                        # 验证这一行确实是关于443端口的
                        if ":443" in cur or "*:443" in cur:
                            try:
                                t_pid = info[1]  # 第二列是PID
                                readable_exe_name = psutil.Process(int(t_pid)).exe()
                            except (psutil.AccessDenied, ValueError, IndexError):
                                readable_exe_name = "权限不足"
                                logger.warning(
                                    f"读取进程{t_pid}的可执行文件名失败！权限不足。"
                                )
                                return
                            logger.warning(
                                f"警告 : {readable_exe_name} (pid={t_pid}) 已经占用了443端口，是否强行终止该程序？ 按回车继续。"
                            )
                            input()
                            try:
                                # 在 Unix 系统上使用 kill 命令
                                subprocess.check_call(["kill", "-9", t_pid])
                                gevent.sleep(3)
                            except subprocess.CalledProcessError as e:
                                logger.warning(f"终止进程{t_pid}时发生错误: {e}")
                            except Exception as e:
                                logger.warning(f"终止进程{t_pid}时发生未知错误: {e}")
                            break

    def run(self):
        from dnsmgr import DNSResolver

        resolver = DNSResolver()
        target = resolver.gethostbyname(genv.get("DOMAIN_TARGET"))
        target_oversea = resolver.gethostbyname(genv.get("DOMAIN_TARGET_OVERSEA"))
        target_using_hardcoded_ip = False
        target_oversea_using_hardcoded_ip = False
        logger.info(target)

        # result check
        try:
            if (
                target == None
                or g_req.get(f"https://{target}", verify=False).status_code != 200
            ):
                target_using_hardcoded_ip = True
                target = "42.186.193.21"
        except:
            target_using_hardcoded_ip = True
            target = "42.186.193.21"

        genv.set("URI_REMOTEIP", f"https://{target}")

        try:
            if (
                target_oversea == None
                or g_req.get(f"https://{target_oversea}", verify=False).status_code
                != 200
            ):
                target_oversea_using_hardcoded_ip = True
                target_oversea = "8.222.80.103"
        except:
            target_oversea_using_hardcoded_ip = True
            target_oversea = "8.222.80.103"

        genv.set("URI_REMOTEIP_OVERSEA", f"https://{target_oversea}")

        if target_using_hardcoded_ip and target_oversea_using_hardcoded_ip:
            logger.warning(
                "警告: 域名解析结果异常，已使用备用IP，若无法登录游戏请尝试更换网络环境，关闭加速器、VPN、代理软件后重试！"
            )
        elif target_using_hardcoded_ip:
            logger.warning("正在使用备用官服IP")
        elif target_oversea_using_hardcoded_ip:
            logger.warning("正在使用备用国际服IP")

        # 创建一个空日志
        import logging

        web_logger = logging.getLogger("web")
        web_logger.setLevel(logging.WARN)

        server = pywsgi.WSGIServer(
            listener=("127.0.0.1", 443),
            certfile=genv.get("FP_WEBCERT"),
            keyfile=genv.get("FP_WEBKEY"),
            application=app,
            log=web_logger,
        )

        if socket.gethostbyname(genv.get("DOMAIN_TARGET")) == "127.0.0.1" or genv.get(
            "USING_BACKUP_VER", False
        ):

            if game_helper.list_auto_start_games():
                should_start_text = "\n".join(
                    [i.name for i in game_helper.list_auto_start_games()]
                )
                logger.info(f"检测到有游戏设置了自动启动，游戏列表{should_start_text}")
                for i in game_helper.list_auto_start_games():
                    i.start()
            self.check_port()
            logger.info("拦截成功! 您现在可以打开游戏了")
            logger.warning(
                "如果您在之前已经打开了游戏，请关闭游戏后重新打开，否则工具不会生效！"
            )
            logger.info("登入账号且已经··进入游戏··后，您可以关闭本工具。")
            server.serve_forever()
            return True
        else:
            logger.error("检测拦截目标域名失败！请将程序加入杀毒软件白名单后重试。")
            return False

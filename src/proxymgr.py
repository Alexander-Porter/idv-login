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
from flask import Flask, request, Response, jsonify, send_file
from gevent import pywsgi
import gevent
from channelHandler.channelUtils import getShortGameId
from cloudRes import CloudRes
from envmgr import genv
from logutil import setup_logger
from gamemgr import Game, GameManager
import socket
import requests
import json
import os
import psutil
import subprocess
import ssl
import socket
import requests
from channelHandler.channelUtils import getShortGameId
from common_routes import register_common_idv_routes
from common_mpay_routes import register_mpay_routes
from login_stack_mgr import LoginStackManager


def is_ipv4(s):
    # Feel free to improve this: https://stackoverflow.com/questions/11827961/checking-for-ip-addresses
    return ":" not in s


dns_cache = {}


def add_custom_dns(domain, port, ip):
    key = (domain, port)
    # Strange parameters explained at:
    # https://docs.python.org/2/library/socket.html#socket.getaddrinfo
    # Values were taken from the output of `socket.getaddrinfo(...)`
    if is_ipv4(ip):
        value = (
            socket.AddressFamily.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            (ip, port),
        )
    else:  # ipv6
        value = (
            socket.AddressFamily.AF_INET6,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            (ip, port, 0, 0),
        )
    dns_cache[key] = [value]


# Inspired by: https://stackoverflow.com/a/15065711/868533
prv_getaddrinfo = socket.getaddrinfo


def new_getaddrinfo(*args):
    # Uncomment to see what calls to `getaddrinfo` look like.
    # print(args)
    try:
        return dns_cache[args[:2]]  # hostname and port
    except KeyError:
        return prv_getaddrinfo(*args)


socket.getaddrinfo = new_getaddrinfo

app = Flask(__name__)
game_helper = GameManager()
logger = setup_logger()

def _preload_default_launcher_data():
    cache = genv.get("launcher_data_cache", {})
    if not isinstance(cache, dict):
        cache = {}
    for game in list(game_helper.games.values()):
        try:
            dist_id = game.get_default_distribution()
            if not dist_id or dist_id == -1:
                continue
            if str(dist_id) in cache:
                continue
            data = game.get_launcher_data_for_distribution(dist_id)
            if isinstance(data, dict) and data:
                cache[str(dist_id)] = data
        except Exception:
            continue
    genv.set("launcher_data_cache", cache, cached=False)




g_req = requests.session()
g_req.trust_env = False


def requestGetAsCv(request, cv, body_mapping={}):

    query = request.args.copy()
    if cv:
        query["cv"] = cv
    for k, v in body_mapping.items():
        query[k] = v
    url = request.base_url

    resp = g_req.request(
        method=request.method,
        url=url,
        params=query,
        headers=request.headers,
        cookies=request.cookies,
        allow_redirects=False,
        verify=True,
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
    url = request.base_url

    # 向目标服务发送代理请求
    resp = requests.request(
        method=request.method,
        url=url,
        params=query,
        headers=request.headers,
        data=new_body,
        cookies=request.cookies,
        allow_redirects=False,
        verify=True,
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
        # 使用Flask的request.form来处理表单数据
        new_body = request.form.to_dict()
        new_body["cv"] = cv
        new_body.pop("arch", None)
        for k, v in body_mapping.items():
            new_body[k] = v
        # 转换为URL编码的字符串格式
        new_body = "&".join([f"{k}={v}" for k, v in new_body.items()])

    app.logger.info(new_body)
    url = request.base_url

    resp = g_req.request(
        method=request.method,
        url=url,
        params=query,
        data=new_body,
        headers=request.headers,
        cookies=request.cookies,
        allow_redirects=False,
        verify=True,
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


def _qrcode_app_channel_provider(game_id):
    if CloudRes().is_game_in_qrcode_login_list(getShortGameId(game_id)):
        return CloudRes().get_qrcode_app_channel(getShortGameId(game_id))
    return None


def _create_login_query_hook(query, game_id):
    if CloudRes().is_game_in_qrcode_login_list(getShortGameId(game_id)):
        query["app_channel"] = CloudRes().get_qrcode_app_channel(
            getShortGameId(game_id)
        )
        query["qrcode_channel_type"] = "3"
        query["gv"] = "251881013"
        query["gvn"] = "2025.0707.1013"
        query["cv"] = "a5.10.0"
        query["sv"] = "35"
        query["app_type"] = "games"
        query["app_mode"] = "2"
        query["_cloud_extra_base64"] = "e30="
        query["sc"] = "1"


def _exchange_token_request(is_selected, game_id, form_data):
    mapping = {
        "opt_fields": "nickname,avatar,realname_status,mobile_bind_status,exit_popup_info,mask_related_mobile,related_login_status,detect_is_new_user",
        "gv": "251881013",
        "gvn": "2025.0707.1013",
        "sv": "35",
        "app_type": "games",
        "app_mode": "2",
        "app_channel": "netease.wyzymnqsd_cps_dev",
        "_cloud_extra_base64": "e30=",
        "sc": "1",
    }
    if CloudRes().is_game_in_qrcode_login_list(getShortGameId(game_id)):
        mapping["app_channel"] = CloudRes().get_qrcode_app_channel(
            getShortGameId(game_id)
        )
        return requestPostAsCv(request, "a5.10.0", mapping)
    return requestPostAsCv(request, "a5.10.0")


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
    cv="a5.10.0",
    login_style=1,
    game_helper=game_helper,
    logger=logger,
    app_channel_default="netease.wyzymnqsd_cps_dev",
    qrcode_app_channel_provider=_qrcode_app_channel_provider,
    create_login_query_hook=_create_login_query_hook,
    use_login_mapping_always=False,
    exchange_token_request=_exchange_token_request,
)


@app.route("/_idv-login/export-logs", methods=["GET"])
def export_logs():
    """导出日志文件，包含调试信息"""
    try:
        from debugmgr import DebugMgr

        if DebugMgr.is_windows():
            data = DebugMgr.export_debug_info_json()
        else:
            logger.warning("当前系统不是Windows，跳过调试信息导出")
            data = {}

        # 返回日志文件
        log_dir = genv.get("FP_WORKDIR")
        log_file_path = os.path.join(log_dir, "log.txt")
        # 在日志文件结尾写入json格式的data
        with open(log_file_path, "a", encoding="utf-8") as f:
            f.write("\n\n")
            f.write(json.dumps(data, ensure_ascii=False, indent=2))

        if os.path.exists(log_file_path):
            return send_file(
                log_file_path,
                as_attachment=True,
                download_name="log.txt",
                mimetype="text/plain",
            )
        else:
            return jsonify({"success": False, "error": "日志文件不存在"}), 404
    except Exception as e:
        logger.exception("导出日志失败")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/_idv-login/get-httpdns-status", methods=["GET"])
def get_httpdns_status():
    """获取HTTPDNS屏蔽状态"""
    try:
        from httpdnsblocker import HttpDNSBlocker

        blocker = HttpDNSBlocker()
        status = blocker.get_status()

        # 从环境管理器获取全局设置状态
        global_enabled = genv.get("httpdns_blocking_enabled", False)

        return jsonify(
            {
                "success": True,
                "enabled": global_enabled,
                "blocked_count": len(status.get("blocked", [])),
            }
        )
    except Exception as e:
        logger.exception("获取HTTPDNS屏蔽状态失败")
        return jsonify({"success": False, "error": f"获取状态失败：{str(e)}"}), 500


@app.route("/_idv-login/toggle-httpdns-blocking", methods=["POST"])
def toggle_httpdns_blocking():
    """切换HTTPDNS屏蔽功能"""
    try:
        from httpdnsblocker import HttpDNSBlocker

        # 获取当前状态并切换
        current_enabled = genv.get("httpdns_blocking_enabled", False)
        new_enabled = not current_enabled

        blocker = HttpDNSBlocker()

        # 执行切换操作
        result = blocker.toggle_blocking(new_enabled)

        # 更新全局设置状态
        genv.set("httpdns_blocking_enabled", result["enabled"], True)

        # 准备返回数据
        response_data = {
            "success": result["success"],
            "enabled": result["enabled"],
            "message": result["message"],
        }

        # 添加警告信息和解除结果
        if not result["enabled"]:
            response_data["warning"] = (
                "警告：禁用HTTPDNS屏蔽可能导致拦截不生效，游戏可能无法正常登录！"
            )
            if "unblocked_count" in result:
                response_data["unblock_result"] = (
                    f"已解除{result['unblocked_count']}个防火墙规则"
                )

        return jsonify(response_data)

    except Exception as e:
        logger.exception("切换HTTPDNS屏蔽功能失败")
        return jsonify({"success": False, "message": f"操作失败：{str(e)}"}), 500


@app.before_request
def before_request_func():
    if "_idv-login" in request.url:
        return
    #logger.info(f"请求 {request.url} {request.headers} {request.get_data().decode()}")
    return

@app.after_request
def after_request_func(response: Response):
    # 如果是图片响应,直接返回
    if response.mimetype and response.mimetype.startswith("image/"):
        return response

    # 只log出现错误的请求
    if (
        (
            response.status_code != 200
            and response.status_code != 302
            and response.status_code != 301
            and response.status_code != 304
        )
        # debug
        #or "_idv-login" not in request.url
    ):
        logger.info(
            f"请求 {request.url} {request.headers} {request.get_data().decode()}"
        )
        logger.info(
            f"发送 {response.status} {response.headers} {response.get_data().decode()}"
        )
    else:
        logger.debug(f"请求 {request.url} {response.status}")
    return response


class proxymgr:
    def __init__(self) -> None:
        genv.set("CHANNEL_ACCOUNT_SELECTED", "")
        LoginStackManager.get_instance().reset()

    def _is_port_in_use(self, port, host="127.0.0.1"):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return False  # 端口未被占用
            except socket.error:
                return True  # 端口被占用

    def check_port(self):
        if self._is_port_in_use(443):
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
        gevent.spawn_later(0, _preload_default_launcher_data)
        resolver = DNSResolver()
        target = resolver.gethostbyname(genv.get("DOMAIN_TARGET"))
        target_oversea = resolver.gethostbyname(genv.get("DOMAIN_TARGET_OVERSEA"))
        target_using_hardcoded_ip = False
        target_oversea_using_hardcoded_ip = False

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
        # 如果成功创建服务器，跳出重试循环

        if socket.gethostbyname(genv.get("DOMAIN_TARGET")) == "127.0.0.1" or genv.get(
            "USING_BACKUP_VER", False
        ):

            # 劫持dns，使得Hosts文件被忽略
            add_custom_dns(genv.get("DOMAIN_TARGET"), 443, target)
            add_custom_dns(genv.get("DOMAIN_TARGET_OVERSEA"), 443, target_oversea)
            if sys.platform.startswith("linux"):
                if os.path.exists("/etc/arch-release"):
                    logger.info("等待3秒以确保系统DNS缓存已刷新...")
                    gevent.sleep(3)
            if (
                not socket.gethostbyname(genv.get("DOMAIN_TARGET_OVERSEA"))
                == "127.0.0.1"
            ):
                logger.warning("国际服域名未被成功劫持。")
            # 启动自动启动游戏
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

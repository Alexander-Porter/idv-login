# coding=UTF-8
"""
 Copyright (c) 2025 Alexander-Porter & fwilliamhe

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
import time
from typing import Mapping
from dns import query
from flask import Flask, request, Response, jsonify, send_file
from gevent import pywsgi
import gevent
from channelHandler.channelUtils import getShortGameId
from envmgr import genv
from logutil import setup_logger
from gamemgr import Game, GameManager
import socket
import requests
import json
import os
import psutil
import const
import subprocess
import socket
import requests
from channelHandler.channelUtils import getShortGameId

def is_ipv4(s):
    # Feel free to improve this: https://stackoverflow.com/questions/11827961/checking-for-ip-addresses
    return ':' not in s

dns_cache = {}

def add_custom_dns(domain, port, ip):
    key = (domain, port)
    # Strange parameters explained at:
    # https://docs.python.org/2/library/socket.html#socket.getaddrinfo
    # Values were taken from the output of `socket.getaddrinfo(...)`
    if is_ipv4(ip):
        value = (socket.AddressFamily.AF_INET, 0, 0, '', (ip, port))
    else: # ipv6
        value = (socket.AddressFamily.AF_INET6, 0, 0, '', (ip, port, 0, 0))
    dns_cache[key] = [value]

# Inspired by: https://stackoverflow.com/a/15065711/868533
prv_getaddrinfo = socket.getaddrinfo
def new_getaddrinfo(*args):
    # Uncomment to see what calls to `getaddrinfo` look like.
    # print(args)
    try:
        return dns_cache[args[:2]] # hostname and port
    except KeyError:
        return prv_getaddrinfo(*args)

socket.getaddrinfo = new_getaddrinfo

app = Flask(__name__)
game_helper = GameManager()
logger=setup_logger()



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


def requestGetAsCv(request, cv,body_mapping={}):

    query = request.args.copy()
    if cv:
        query["cv"] = cv
    for k,v in body_mapping.items():
        query[k]=v
    url = request.base_url
    if request.host == "localhost":
        url = url.replace("localhost", genv.get("DOMAIN_TARGET"))
    resp = g_req.request(
        method=request.method,
        url=url,
        params=query,
        headers=request.headers,
        cookies=request.cookies,
        allow_redirects=False,
        verify=True
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


def proxy(request,query={}):
    if query=={}:
        query = request.args.copy()
    new_body = request.get_data(as_text=True)
    url = request.base_url
    if request.host == "localhost":
        url = url.replace("localhost", genv.get("DOMAIN_TARGET"))
    # 向目标服务发送代理请求
    resp = requests.request(
        method=request.method,
        url=url,
        params=query,
        headers=request.headers,
        data=new_body,
        cookies=request.cookies,
        allow_redirects=False,
        verify=True
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


def requestPostAsCv(request, cv,body_mapping={}):

    query = request.args.copy()
    if cv:
        query["cv"] = cv
    try:
        new_body = request.get_json()
        new_body["cv"] = cv
        new_body.pop("arch", None)
        for k,v in body_mapping.items():
            new_body[k]=v
    except:
        # 使用Flask的request.form来处理表单数据
        new_body = request.form.to_dict()
        new_body["cv"] = cv
        new_body.pop("arch", None)
        for k,v in body_mapping.items():
            new_body[k]=v
        # 转换为URL编码的字符串格式
        new_body = "&".join([f"{k}={v}" for k, v in new_body.items()])

    app.logger.info(new_body)
    url = request.base_url
    if request.host == "localhost":
        url = url.replace("localhost", genv.get("DOMAIN_TARGET"))
    resp = g_req.request(
        method=request.method,
        url=url,
        params=query,
        data=new_body,
        headers=request.headers,
        cookies=request.cookies,
        allow_redirects=False,
        verify=True
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
        resp: Response = requestGetAsCv(request, "a5.10.0")
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
        return requestPostAsCv(request, "a5.10.0")
    except:
        return proxy(request)


@app.route("/mpay/games/<game_id>/devices/<device_id>/users/<user_id>", methods=["GET"])
def handle_login(game_id, device_id, user_id):
    try:
        mapping={
            "opt_fields": "nickname,avatar,realname_status,mobile_bind_status,exit_popup_info,mask_related_mobile,related_login_status,detect_is_new_user",
            "verify_status": "1",
            "login_for": "1", 
            "gv": "251881013",
            "gvn": "2025.0707.1013",
            "sv": "35",
            "app_type": "games",
            "app_mode": "2",
            "app_channel": "netease.wyzymnqsd_cps_dev",
            "_cloud_extra_base64": "e30=",
            "sc": "1"
        }
        if genv.get("CLOUD_RES").is_game_in_qrcode_login_list(getShortGameId(game_id)):
            mapping["app_channel"] = genv.get("CLOUD_RES").get_qrcode_app_channel(getShortGameId(game_id))
            resp: Response = requestGetAsCv(request, "a5.10.0",mapping)
        else:
            resp: Response = requestGetAsCv(request, "a5.10.0")


        new_devices = resp.get_json()
        new_devices["user"]["pc_ext_info"] = pcInfo
        resp.set_data(json.dumps(new_devices))
        return resp
    except:
        return proxy(request)

@app.route("/mpay/api/qrcode/image", methods=["GET"])
def handle_qrcode_image():
    try:
        resp=proxy(request)
        if genv.get("CLOUD_RES").get_risk_wm()!="":
            from riskWmUtils import wm
            resp.set_data(wm(resp.get_data(),genv.get("CLOUD_RES").get_risk_wm()))
            return resp
        return resp
    except:
        return proxy(request)

@app.route("/mpay/games/pc_config", methods=["GET"])
def handle_pc_config():
    try:
        resp: Response = requestGetAsCv(request, "a5.10.0")
        new_config = resp.get_json()
        new_config["game"]["config"]["cv_review_status"] = 1
        new_config["game"]["config"]["web_token_persist"]=True
        new_config["game"]["config"]["mobile_related_login"]["guide_related_mobile"]=True
        new_config["game"]["config"]["mobile_related_login"]["force_related_login"]=True
        new_config["game"]["config"]["login"]["login_style"]=1
        resp.set_data(json.dumps(new_config))
        return resp
    except:
        return proxy(request)


@app.route("/mpay/api/qrcode/create_login", methods=["GET"])
def handle_create_login():
    try:
        query=request.args.to_dict()
        game_id=query["game_id"]
        if genv.get("CLOUD_RES").is_game_in_qrcode_login_list(getShortGameId(game_id)):
            query["app_channel"] = genv.get("CLOUD_RES").get_qrcode_app_channel(getShortGameId(game_id))

            query["qrcode_channel_type"] = "3"
            query["gv"] = "251881013"
            query["gvn"] = "2025.0707.1013" 
            query["cv"] = "a5.10.0"
            query["sv"] = "35"
            query["app_type"] = "games"
            query["app_mode"] = "2"
            query["_cloud_extra_base64"] = "e30="
            query["sc"] = "1"
        resp: Response = proxy(request,query)
        genv.set("CHANNEL_ACCOUNT_SELECTED", "")
        data={
            "uuid":resp.get_json()["uuid"],
            "game_id":request.args["game_id"]
        }
        genv.set("CACHED_QRCODE_DATA",data)
        genv.set("pending_login_info",None)
        #auto login start
        if genv.get(f"auto-{request.args['game_id']}", "") != "":
                delay=game_helper.get_login_delay(request.args["game_id"])
                logger.info(f"即将自动登录，{delay}秒后开始扫码")
                uuid=genv.get(f"auto-{request.args['game_id']}")
                genv.set("CHANNEL_ACCOUNT_SELECTED",uuid)
                gevent.spawn_later(
                    delay,
                    genv.get("CHANNELS_HELPER").simulate_scan,
                    uuid,
                    data["uuid"],
                    data["game_id"]
                )
        new_config = resp.get_json()
        new_config["qrcode_scanners"][0]["url"] = "https://localhost/_idv-login/index?game_id="+request.args["game_id"]
        return jsonify(new_config)
    except:
        return proxy(request)

@app.route("/_idv-login/manualChannels",methods=["GET"])
def _manual_list():
    try:
        game_id=request.args["game_id"]
        if game_id:
            data=genv.get("CLOUD_RES").get_all_by_game_id(getShortGameId(game_id))
            return jsonify(data)
        else:
            return jsonify(const.manual_login_channels)
    finally:
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
        genv.get("CHANNELS_HELPER").simulate_scan(request.args["uuid"],"Kinich","aecfrt3rmaaaaajl-g-g37")
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
        logger.exception("设置默认账号失败")
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
            import sys
            
            # 创建一个临时的QApplication实例
            app = QApplication.instance()
            if app is None:
                app = QApplication(sys.argv)
            
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
            #获取纯文件名，不含路径和后缀
            name=os.path.splitext(os.path.basename(game_path))[0]
            
            # 如果是快捷方式，解析目标路径
            if game_path.lower().endswith(".lnk"):
                import win32com.client
                shell = win32com.client.Dispatch("WScript.Shell")
                shortcut = shell.CreateShortcut(game_path)
                game_path = shortcut.Targetpath
        else:
            if game_helper.get_game(game_id):
                name=game_helper.get_game(game_id).name
            else:
                name=""
        game_helper.set_game_auto_start(game_id, enabled)
        game_helper.set_game_path(game_id, game_path)
        game_helper.rename_game(game_id,name)
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


        game: Game = game_helper.get_game(game_id)
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
        logger.exception(f"列出游戏失败")
        return jsonify({
            "success": False,
            "error": str(e)
        })

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

@app.route("/_idv-login/export-logs", methods=["GET"])
def export_logs():
    """导出日志文件，包含调试信息"""
    try:
        # 导入DebugMgr并导出调试信息到日志
        from debugmgr import DebugMgr
        if DebugMgr.is_windows():
            logger.info("开始导出调试信息...")
            DebugMgr.export_debug_info()
            logger.info("调试信息导出完成")
        else:
            logger.warning("当前系统不是Windows，跳过调试信息导出")
        
        # 返回日志文件
        log_dir=genv.get('FP_WORKDIR')
        log_file_path = os.path.join(log_dir, "log.txt")
        if os.path.exists(log_file_path):
            return send_file(
                log_file_path,
                as_attachment=True,
                download_name=f"idv-login-debug-{int(time.time())}.txt",
                mimetype='text/plain'
            )
        else:
            return jsonify({
                "success": False,
                "error": "日志文件不存在"
            }), 404
    except Exception as e:
        logger.exception("导出日志失败")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/_idv-login/get-httpdns-status", methods=["GET"])
def get_httpdns_status():
    """获取HTTPDNS屏蔽状态"""
    try:
        from httpdnsblocker import HttpDNSBlocker
        blocker = HttpDNSBlocker()
        status = blocker.get_status()
        
        # 从环境管理器获取全局设置状态
        global_enabled = genv.get("httpdns_blocking_enabled", False)
        
        return jsonify({
            "success": True,
            "enabled": global_enabled,
            "blocked_count": len(status.get("blocked", []))
        })
    except Exception as e:
        logger.exception("获取HTTPDNS屏蔽状态失败")
        return jsonify({
            "success": False,
            "error": f"获取状态失败：{str(e)}"
        }), 500

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
            "message": result["message"]
        }
        
        # 添加警告信息和解除结果
        if not result["enabled"]:
            response_data["warning"] = "警告：禁用HTTPDNS屏蔽可能导致拦截不生效，游戏可能无法正常登录！"
            if "unblocked_count" in result:
                response_data["unblock_result"] = f"已解除{result['unblocked_count']}个防火墙规则"
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.exception("切换HTTPDNS屏蔽功能失败")
        return jsonify({
            "success": False,
            "message": f"操作失败：{str(e)}"
        }), 500

@app.route("/_idv-login/index",methods=['GET'])
def _handle_switch_page():
    try:
        cloudRes = genv.get("CLOUD_RES")
        if cloudRes.get_login_page() == "":
            return Response(const.html)
        return Response(cloudRes.get_login_page())
    except Exception as e:
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
    mapping={
        "opt_fields": "nickname,avatar,realname_status,mobile_bind_status,exit_popup_info,mask_related_mobile,related_login_status,detect_is_new_user",
        "gv": "251881013",
        "gvn": "2025.0707.1013", 
        "sv": "35",
        "app_type": "games",
        "app_mode": "2",
        "app_channel": "netease.wyzymnqsd_cps_dev",
        "_cloud_extra_base64": "e30=",
        "sc": "1"
    }
    try:
        # 尝试读取 form 数据
        form_data = request.form.to_dict()
        logger.debug(f"数据上传内容: {form_data}")
    except Exception as e:
        logger.error(f"解析上传数据失败: {e}")
    game_id = form_data.get("game_id", "")
    if genv.get("CHANNEL_ACCOUNT_SELECTED"):
        logger.info(f"尝试登录{genv.get('CHANNEL_ACCOUNT_SELECTED')}")
        if genv.get("CLOUD_RES").is_game_in_qrcode_login_list(getShortGameId(game_id)):
            mapping["app_channel"] = genv.get("CLOUD_RES").get_qrcode_app_channel(getShortGameId(game_id))
            resp=  requestPostAsCv(request,"a5.10.0",mapping)
        else:
            resp=  requestPostAsCv(request,"a5.10.0")

        if resp.status_code==200 and game_helper.get_auto_close_setting(game_id):
            logger.info("检测到登录已完成请求，即将自动关闭程序...")
            # 使用 gevent 延迟退出，确保响应能够正常返回
            gevent.spawn_later(3, sys.exit, 0)
        return resp
    else:
        logger.info(f"捕获到渠道服登录Token.")
        if genv.get("CLOUD_RES").is_game_in_qrcode_login_list(getShortGameId(game_id)):
            mapping["app_channel"] = genv.get("CLOUD_RES").get_qrcode_app_channel(getShortGameId(game_id))
            resp: Response = requestPostAsCv(request,"a5.10.0",mapping)
        else:
            resp: Response = requestPostAsCv(request,"a5.10.0")


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
        return requestGetAsCv(request, "a5.10.0")
    else:
        return requestPostAsCv(request, "a5.10.0")

@app.after_request
def after_request_func(response:Response):
    # 如果是图片响应,直接返回
    if response.mimetype and response.mimetype.startswith('image/'):
        return response
        
    #只log出现错误的请求
    if response.status_code!=200 and response.status_code!=302 and response.status_code!=301 and response.status_code!=304:
        logger.error(f"请求 {request.url} {request.headers} {request.get_data().decode()}")
        logger.error(f"发送 {response.status} {response.headers} {response.get_data().decode()}")
    else:
        logger.debug(f"请求 {request.url} {response.status}")
    return response

class proxymgr:
    def __init__(self) -> None:
        genv.set("CHANNEL_ACCOUNT_SELECTED", "")
        genv.set("CACHED_QRCODE_DATA",{})
        genv.set("pending_login_info",None)
        

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
                            RealTime_PIDs=psutil.pids()#获取当前最新的所有PID，防止用户手动终止冲突进程
                            if t_pid in RealTime_PIDs:
                                subprocess.check_call(
                                    ["taskkill", "/f", "/pid", t_pid], shell=True
                                )
                            del RealTime_PIDs
                        gevent.sleep(3)
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
        import logging
        web_logger=logging.getLogger("web")
        web_logger.setLevel(logging.WARN)
        server = pywsgi.WSGIServer(
                listener=("127.0.0.1", 443),
                certfile=genv.get("FP_WEBCERT"),
                keyfile=genv.get("FP_WEBKEY"),
                application=app,
                log=web_logger,
            )
        if socket.gethostbyname(genv.get("DOMAIN_TARGET")) == "127.0.0.1" or genv.get("USING_BACKUP_VER", False):
            logger.info("拦截成功! 您现在可以打开游戏了")
            logger.warning("如果您在之前已经打开了游戏，请关闭游戏后重新打开，否则工具不会生效！")
            logger.info("登入账号且已经··进入游戏··后，您可以关闭本工具。")
            #劫持dns，使得Hosts文件被忽略
            add_custom_dns(genv.get("DOMAIN_TARGET"), 443, target)
            if game_helper.list_auto_start_games():
                should_start_text="\n".join([i.name for i in game_helper.list_auto_start_games()])
                logger.info(f"检测到有游戏设置了自动启动，游戏列表{should_start_text}")
                for i in game_helper.list_auto_start_games():
                    i.start()
            server.serve_forever()
            return True
        else:
            logger.error("检测拦截目标域名失败！请将程序加入杀毒软件白名单后重试。")
            return False

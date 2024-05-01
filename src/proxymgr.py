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


from flask import Flask, request, Response
from gevent import pywsgi
import socket
import requests
import json

app = Flask(__name__)

TARGET_URL = ""

loginMethod=[{
                "name": "手机账号",
                "icon_url": "",
                "text_color": "",
                "hot": True,
                "type": 7,
                "icon_url_large": ""
            },
            {
                "name": "快速游戏",
                "icon_url": "",
                "text_color": "",
                "hot": True,
                "type": 2,
                "icon_url_large": ""
            },
            {
                "login_url": "",
                "name": "网易邮箱",
                "icon_url": "",
                "text_color": "",
                "hot": True,
                "type": 1,
                "icon_url_large": ""
            },
            {
                "login_url": "",
                "name": "扫码登录",
                "icon_url": "",
                "text_color": "",
                "hot": True,
                "type": 17,
                "icon_url_large": ""
            }
]
pcInfo={
            "extra_unisdk_data": "",
            "from_game_id": "h55",
            "src_app_channel": "netease",
            "src_client_ip": "",
            "src_client_type": 1,
            "src_jf_game_id": "h55",
            "src_pay_channel": "netease",
            "src_sdk_version": "3.15.0",
            "src_udid": ""
        }


def requestGetAsCv(request,cv):
    global TARGET_URL
    query = request.args.copy()
    if cv:
        query["cv"] =cv
    resp = requests.request(
    method=request.method,
    url=TARGET_URL+request.path,
    params=query,
    headers=request.headers,
    cookies=request.cookies,
    allow_redirects=False,
    verify=False
    )
    excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
    headers = [(name, value) for (name, value) in resp.raw.headers.items()
               if name.lower() not in excluded_headers]
    return Response(resp.text, resp.status_code, headers)


def proxy(request):
    global TARGET_URL
    query = request.args.copy()
    new_body=request.get_data(as_text=True)    
    # 向目标服务发送代理请求
    resp = requests.request(
        method=request.method,
        url=TARGET_URL+request.path,
        params=query,
        headers=request.headers,
        data=new_body,
        cookies=request.cookies,
        allow_redirects=False,
        verify=False
    )
    app.logger.info(resp.url)
    # 构造代理响应
    excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
    headers = [(name, value) for (name, value) in resp.raw.headers.items()
               if name.lower() not in excluded_headers]
    
    response = Response(resp.content, resp.status_code, headers)
    return response
def requestPostAsCv(request,cv):
    query = request.args.copy()
    if cv:
        query["cv"] =cv
    try:
        new_body=request.get_json()
        new_body["cv"] = cv
        new_body.pop("arch", None)
    except:
        new_body = dict(x.split("=") for x in request.get_data(as_text=True).split("&"))
        new_body["cv"] = cv
        new_body.pop("arch", None)
        new_body="&".join([f"{k}={v}" for k,v in new_body.items()])

    app.logger.info(new_body)
    resp = requests.request(
    method=request.method,
    url=TARGET_URL+request.path,
    params=query,
    data=new_body,
    headers=request.headers,
    cookies=request.cookies,
    allow_redirects=False,
    verify=False
    )
    excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
    headers = [(name, value) for (name, value) in resp.raw.headers.items()
               if name.lower() not in excluded_headers]
    return Response(resp.text, resp.status_code, headers)
@app.route('/mpay/games/<game_id>/login_methods', methods=['GET'])
def handle_login_methods(game_id):
    try:
        resp:Response= requestGetAsCv(request,'i4.7.0')
        new_login_methods = resp.get_json()
        new_login_methods["entrance"]=[(loginMethod)]
        new_login_methods["select_platform"] = True
        new_login_methods["qrcode_select_platform"] = True
        for i in new_login_methods["config"]:
            new_login_methods["config"][i]["select_platforms"] = [0, 1, 2, 3, 4]
        resp.set_data(json.dumps(new_login_methods))
        return resp
    except:
        return proxy(request)


@app.route('/mpay/api/users/login/mobile/finish',methods=['POST'])
@app.route('/mpay/api/users/login/mobile/get_sms',methods=['POST'])
@app.route('/mpay/api/users/login/mobile/verify_sms',methods=['POST'])
@app.route('/mpay/games/<game_id>/devices/<device_id>/users',methods=['POST'])
def handle_first_login(game_id=None, device_id=None):
    try:
        return requestPostAsCv(request,"i4.7.0")
    except:
        return proxy(request)

@app.route('/mpay/games/<game_id>/devices/<device_id>/users/<user_id>', methods=['GET'])
def handle_login(game_id, device_id, user_id):
    try:
        resp:Response=requestGetAsCv(request,'i4.7.0')
        new_devices = resp.get_json()
        new_devices["user"]["pc_ext_info"] = pcInfo
        resp.set_data(json.dumps(new_devices))
        return resp
    except:
        return proxy(request)

@app.route('/mpay/games/pc_config', methods=['GET'])
def handle_pc_config():
    try:
        resp:Response=requestGetAsCv(request,'i4.7.0')
        new_config = resp.get_json()
        new_config["game"]["config"]["cv_review_status"] = 1
        resp.set_data(json.dumps(new_config))
        return resp
    except:
        return proxy(request)

@app.route('/mpay/api/qrcode/<path>', methods=['GET'])
def handle_qrcode(path):
        return proxy(request)


@app.route('/<path:path>', methods=['GET', 'POST'])
def globalProxy(path):
    if request.method == 'GET':
        return requestGetAsCv(request,'i4.7.0')
    else:
        return requestPostAsCv(request,'i4.7.0')
    
DOMAIN = 'service.mkey.163.com'

class proxymgr:
    def __init__(self) -> None:
        pass
    def run(self):
        global TARGET_URL
        from dnsmgr import SecureDNS
        resolver = SecureDNS()
        target = resolver.gethostbyname(DOMAIN)
        TARGET_URL = f'https://{target}'

        if socket.gethostbyname(DOMAIN)=='127.0.0.1':
            server = pywsgi.WSGIServer(listener=('127.0.0.1', 443), certfile='domain_cert.pem',keyfile='domain_key.pem', application=app)
            print("[Proxy] proxy server has been started!")
            server.serve_forever()
            return True
        else:
            print("[Proxy] Failed to redirect target to localhost!")
            return False
        

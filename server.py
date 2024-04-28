import subprocess
import sys
from flask import Flask, request, Response
import requests
import json
import urllib3
import ctypes
app = Flask(__name__)
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
# 反向代理的目标域名
HOSTS_FILE = r'C:\Windows\System32\drivers\etc\hosts'
DOMAIN = 'service.mkey.163.com'
BACKUP_HOSTS_FILE = HOSTS_FILE + '.bak'
#DNS查询
#nslookup -qt=mx example.com
result = subprocess.check_output(['nslookup', DOMAIN])

# 解码结果（Windows默认使用cp437编码）
result = result.decode('cp437')
IP=""
# 找到包含'Address'的行，并提取IP地址
for line in result.splitlines():
    if 'Addresses' in line:
        ip_address = line.split()[-1]
        IP=ip_address
        print(f'DNS解析结果: {ip_address}')
        break

TARGET_URL = f'https://{IP}'




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
        new_login_methods["entrance"].append(loginMethod)
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


@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def thisProxy(path):
    return proxy(request)
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






import os


def modify_hosts():
    with open(HOSTS_FILE, 'w') as file:
        file.seek(0, 0)
        file.write('127.0.0.1    ' + DOMAIN + '\n' )



if __name__ == '__main__':

    # 加载SSL证书和私钥
    if ctypes.windll.shell32.IsUserAnAdmin() == 0:
        # We are not running "as Administrator" - so relaunch as administrator
        print("非管理员，按回车尝试以管理员身份重试")
        input("等待回车")
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, __file__, None, 1)
        sys.exit(0)
    if not os.path.exists(BACKUP_HOSTS_FILE):
        os.rename(HOSTS_FILE, BACKUP_HOSTS_FILE)

    modify_hosts()
    #检查证书是否存在
    if os.path.exists('domain_cert.pem') and os.path.exists('domain_key.pem'):
        context = ('domain_cert.pem', 'domain_key.pem')
        app.run(debug=True, host='127.0.0.1', port=443, ssl_context=context)
    else:
        print("证书不存在！请检查目录下是否有domain_cert和domain_key")
        print("如果没有，重新执行serveSetup")
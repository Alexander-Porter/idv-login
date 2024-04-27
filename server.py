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







@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy(path):
    #得到请求参数
    query = request.args.copy()
    if "mpay" in request.url:
        query["cv"] = "i4.7.0"
        if request.method == "POST":
            new_body = dict(x.split("=") for x in request.get_data(as_text=True).split("&"))
            new_body["cv"] = "i4.7.0"
            new_body.pop("arch", None)
        if 'devices' in request.url:
            query["app_mode"] = 2
    # 原始的代理请求处理代码
    global TARGET_URL
    
    # 向目标服务发送代理请求
    resp = requests.request(
        method=request.method,
        url=TARGET_URL+"/"+path,params=query,
        headers={key: value for (key, value) in request.headers if key != 'Host'},
        data=request.get_data(),
        cookies=request.cookies,
        allow_redirects=False,
        verify=False
    )
    app.logger.info(resp.url)
    # 构造代理响应
    excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
    headers = [(name, value) for (name, value) in resp.raw.headers.items()
               if name.lower() not in excluded_headers]
    new_body = resp.content
    if 'login_methods' in request.url:
        app.logger.info('Hit!')
        new_login_methods = resp.json()
        new_login_methods["entrance"].append(loginMethod)
        new_login_methods["select_platform"] = True
        new_login_methods["qrcode_select_platform"] = True
        for i in new_login_methods["config"]:
            new_login_methods["config"][i]["select_platforms"] = [0, 1, 2, 3, 4]
        new_body = json.dumps(new_login_methods)
    elif 'pc_config' in request.url:
        new_pc_config = resp.json()
        new_pc_config["game"]["config"]["cv_review_status"] = 1
        new_body = json.dumps(new_pc_config)
    elif 'devices' in request.url:
        new_devices = resp.json()
        new_devices["user"]["pc_ext_info"] = pcInfo
        new_body = json.dumps(new_devices)
    
    response = Response(new_body, resp.status_code, headers)
    return response
import os
import atexit


def modify_hosts():
    with open(HOSTS_FILE, 'w') as file:
        file.seek(0, 0)
        #备份
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

    context = ('domain_cert.pem', 'domain_key.pem')
    app.run(debug=True, host='127.0.0.1', port=443, ssl_context=context)

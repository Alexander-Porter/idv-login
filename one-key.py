import os
import socket
import subprocess
import ctypes
import sys
from flask import Flask, request, Response
import requests
import json
import ctypes
import shutil

app = Flask(__name__)
loginMethod = [{
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
pcInfo = {
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

HOSTS_FILE = r'C:\Windows\System32\drivers\etc\hosts'
DOMAIN = 'service.mkey.163.com'
BACKUP_HOSTS_FILE = HOSTS_FILE + '.bak'
TRUSTED_DNS = '114.114.114.114'
WORKDIR = os.path.join(os.environ['PROGRAMDATA'], 'idv-login')
#DNS查询
result = subprocess.check_output(['nslookup', DOMAIN, TRUSTED_DNS])
result = result.decode('cp437')
IP = ""
# 找到包含'Address'的行，并提取IP地址
for line in result.splitlines():
    if 'Addresses' in line:
        ip_address = line.split()[-1]
        IP = ip_address
        print(f'DNS解析结果: {ip_address}')
        break
if IP == "":
    print("DNS解析失败，请检查网络环境！")
    input("回车退出。")
    quit()
TARGET_URL = f'https://{IP}'


def requestGetAsCv(request, cv):
    global TARGET_URL
    query = request.args.copy()
    if cv:
        query["cv"] = cv
    resp = requests.request(
        method=request.method,
        url=TARGET_URL + request.path,
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
    new_body = request.get_data(as_text=True)
    # 向目标服务发送代理请求
    resp = requests.request(
        method=request.method,
        url=TARGET_URL + request.path,
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
    resp = requests.request(
        method=request.method,
        url=TARGET_URL + request.path,
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
        resp: Response = requestGetAsCv(request, 'i4.7.0')
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


@app.route('/mpay/api/users/login/mobile/finish', methods=['POST'])
@app.route('/mpay/api/users/login/mobile/get_sms', methods=['POST'])
@app.route('/mpay/api/users/login/mobile/verify_sms', methods=['POST'])
@app.route('/mpay/games/<game_id>/devices/<device_id>/users', methods=['POST'])
def handle_first_login(game_id=None, device_id=None):
    try:
        return requestPostAsCv(request, "i4.7.0")
    except:
        return proxy(request)


@app.route('/mpay/games/<game_id>/devices/<device_id>/users/<user_id>', methods=['GET'])
def handle_login(game_id, device_id, user_id):
    try:
        resp: Response = requestGetAsCv(request, 'i4.7.0')
        new_devices = resp.get_json()
        new_devices["user"]["pc_ext_info"] = pcInfo
        resp.set_data(json.dumps(new_devices))
        return resp
    except:
        return proxy(request)


@app.route('/mpay/games/pc_config', methods=['GET'])
def handle_pc_config():
    try:
        resp: Response = requestGetAsCv(request, 'i4.7.0')
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
        return requestGetAsCv(request, 'i4.7.0')
    else:
        return requestPostAsCv(request, 'i4.7.0')


from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
from datetime import datetime, timedelta


def create_self_signed_cert():
    # 生成密钥对
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # 创建证书主题和颁发者名称
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"CN"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"Beijing"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, u"BeiJing"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"idv-login"),
        x509.NameAttribute(NameOID.COMMON_NAME, u"idv-login"),
    ])

    # 创建证书
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.now()
    ).not_valid_after(
        # 证书有效期为1年
        datetime.now() + timedelta(days=365)
    ).add_extension(
        x509.BasicConstraints(ca=True, path_length=None), critical=True,
    ).sign(key, hashes.SHA256())

    # 证书和密钥写入文件
    with open("root_ca.pem", "wb") as f:
        f.write(cert.public_bytes(Encoding.PEM))

    # 生成域名密钥对
    domain_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # 创建CSR
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, u"CN"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"BeiJing"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, u"BeiJing"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"idv-login"),
            x509.NameAttribute(NameOID.COMMON_NAME, DOMAIN),
        ])
    ).add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName(DOMAIN),
        ]),
        critical=False,
    ).sign(domain_key, hashes.SHA256())

    # 使用根证书签名CSR
    domain_cert = x509.CertificateBuilder().subject_name(
        csr.subject
    ).issuer_name(
        cert.subject
    ).public_key(
        csr.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.now()
    ).not_valid_after(
        # 证书有效期为1年
        datetime.now() + timedelta(days=365)
    ).add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName(DOMAIN),
        ]),
        critical=False,
    ).sign(key, hashes.SHA256())

    # 证书和密钥写入文件
    with open("domain_cert.pem", "wb") as f:
        f.write(domain_cert.public_bytes(Encoding.PEM))
    with open("domain_key.pem", "wb") as f:
        f.write(domain_key.private_bytes(
            Encoding.PEM,
            PrivateFormat.TraditionalOpenSSL,
            NoEncryption()
        ))

    # 安装根证书
    print("安装根证书...")
    subprocess.check_call(["certutil", "-addstore", "-f", "Root", "root_ca.pem"])

    # 修改 Hosts 文件
    print("改写Hosts...")
    if not os.path.exists(BACKUP_HOSTS_FILE):
        os.rename(HOSTS_FILE, BACKUP_HOSTS_FILE)
    with open(HOSTS_FILE, 'w') as file:
        file.seek(0, 0)
        file.write('127.0.0.1    ' + DOMAIN + '\n')


def restore_hosts():
    try:
        if os.path.exists(BACKUP_HOSTS_FILE):
            os.remove(HOSTS_FILE)
            os.rename(BACKUP_HOSTS_FILE, HOSTS_FILE)
            print("已从备份文件恢复 Hosts 文件")
        else:
            print("找不到 Hosts 备份文件")
        if os.path.exists(WORKDIR):
            shutil.rmtree(WORKDIR)
        else:
            print("找不到 证书文件")
            print("可能你尚未运行过本程序，或者已经执行过此命令。")
            input("按任意键继续...")
            sys.exit(0)
    except Exception as e:
        print(f"无法正常访问文件: {e}")
        print("文件可能正在使用中?")
        print("如果你启用了杀毒软件，请关闭后并重新运行。")
        input("按任意键继续...")
        sys.exit(0)


def init(domain):
    if not os.path.exists(WORKDIR):
        os.mkdir(WORKDIR)
    print(f"工作目录：{WORKDIR}")
    os.chdir(os.path.join(WORKDIR))
    if os.path.exists('domain_cert.pem') and os.path.exists('domain_key.pem'):
        if socket.gethostbyname(domain) == '127.0.0.1':
            context = ('domain_cert.pem', 'domain_key.pem')
            app.run(host='127.0.0.1', port=443, ssl_context=context)
        else:
            print("Hosts 状态异常！")
            print("请重新初始化或尝试运行 \"恢复 Hosts 文件 并删除证书\"")
            print("如果你启用了杀毒软件，请关闭后并重新运行。")
            input("按任意键继续...")
            sys.exit(0)
    else:
        create_self_signed_cert()
        init(domain)


def is_admin():
    return ctypes.windll.shell32.IsUserAnAdmin() != 0


if __name__ == '__main__':
    if not is_admin():
        print("您当前不是管理员。")
        print("请以管理员身份运行此脚本。")
        input("按任意键继续...")
        sys.exit(0)

    # 显示菜单并获取用户选择
    print("项目地址: https://github.com/Alexander-Porter/idv-login/tree/one-key")
    print("请选择操作：\n1. 运行程序\n2. 恢复 Hosts 文件并删除证书 (恢复原本状态)")
    choice = input("输入选项: ")

    # 根据用户选择执行相应操作
    if choice == '1':
        init(DOMAIN)
    elif choice == '2':
        restore_hosts()
    else:
        print("无效选项，请输入1或2。")

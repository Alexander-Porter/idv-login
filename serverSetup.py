import os
import subprocess
import ctypes
import sys


script_path = os.path.dirname(os.path.realpath(__file__))
print(f"脚本路径: {script_path}")
os.chdir(script_path)

# Check if we are running as an administrator
if ctypes.windll.shell32.IsUserAnAdmin() == 0:
    # We are not running "as Administrator" - so relaunch as administrator
    print("非管理员，按回车尝试以管理员身份重试")
    input("等待回车")
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, __file__, None, 1)
    sys.exit(0)

#准备环境
#询问用户是否需要换源
if input("是否需要换pip源到清华源？(y/n)") == "y":
#pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
    subprocess.check_call(["pip", "config", "set", "global.index-url", "https://pypi.tuna.tsinghua.edu.cn/simple"])
print("准备环境...")
subprocess.check_call(["pip", "install", "-r", "requirements.txt"])
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
from cryptography.hazmat.primitives.serialization import BestAvailableEncryption
from datetime import datetime, timedelta
DOMAIN = 'service.mkey.163.com'
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
with open("root_ca_key.pem", "wb") as f:
    f.write(key.private_bytes(
        Encoding.PEM,
        PrivateFormat.TraditionalOpenSSL,
        NoEncryption()
    ))

# 生成域名密钥对
domain_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
)

# 创建CSR
csr = x509.CertificateSigningRequestBuilder().subject_name(
    x509.Name([
        # 提供证书的详细信息
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"CN"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"BeiJing"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, u"BeiJing"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"idv-login"),
        x509.NameAttribute(NameOID.COMMON_NAME, DOMAIN),
    ])
).add_extension(
    x509.SubjectAlternativeName([
        # 这里添加域名和子域名
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
#安装根证书
# Install the root certificate
print("安装根证书...")
subprocess.check_call(["certutil", "-addstore", "-f", "Root", "root_ca.pem"])
input("Press Enter to continue...")

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

import subprocess
import sys
import datetime
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption

class certmgr:
    def __init__(self) -> None:
        pass
    def generate_private_key(self, bits : int):
        return rsa.generate_private_key(    
            public_exponent=65537,
            key_size=bits
        )
    def generate_ca(self, privatekey):
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, u"US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"California"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, u"Los Angles"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Netease Login Helper CA"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, u"Netease Login Helper CA"),
            x509.NameAttribute(NameOID.COMMON_NAME, u"Netease Login Helper CA")
        ])
        return x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            privatekey.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.datetime.now(datetime.UTC)
        ).not_valid_after(
            datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=365)
        ).add_extension(
            x509.BasicConstraints(ca=True, path_length=None), critical=True,
        ).sign(privatekey, hashes.SHA256())
    
    def generate_cert(self, hostname, privatekey, ca_cert, ca_key) :
        # generate the CSR
        csr = x509.CertificateSigningRequestBuilder().subject_name(
            x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, u"US"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"California"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, u"Los Angeles"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Netease Login Helper Web"),
                x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, u"Netease Login Helper Web"),
                x509.NameAttribute(NameOID.COMMON_NAME, hostname),
            ])
        ).add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName(hostname),
            ]),
            critical=False,
        ).sign(privatekey, hashes.SHA256())

        # send the csr to CA
        return x509.CertificateBuilder().subject_name(
            csr.subject
        ).issuer_name(
            ca_cert.subject
        ).public_key(
            csr.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.datetime.now(datetime.UTC)
        ).not_valid_after(
            datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=365)
        ).add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName(hostname),
            ]),
            critical=False,
        ).sign(ca_key, hashes.SHA256())
    
    def import_to_root(self, fn) -> bool:
        try :
            subprocess.check_call(["certutil", "-addstore", "-f", "Root", fn], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
        except Exception as e:
            print(str(e))
            print("[certmgr] 导入CA证书失败，您是否拥有足够的权限?")
            return False
        else:
            return True
    def export_key(self, fn, key) :
        try:
            with open(fn, "wb") as f:
                f.write(key.private_bytes(
                    Encoding.PEM,
                    PrivateFormat.TraditionalOpenSSL,
                    NoEncryption()
                ))
        except Exception as e:
            print(str(e))
            print("[certmgr] 导出私钥失败！")
            sys.exit()
    def export_cert(self, fn, cert):
        try:
            with open(fn, "wb") as f:
                f.write(cert.public_bytes(Encoding.PEM))
        except Exception as e:
            print(str(e))
            print("[certmgr] 导出证书失败！")
            sys.exit()

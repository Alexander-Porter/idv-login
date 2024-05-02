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

import os
import sys
import ctypes
import atexit
import signal
import argparse
from envmgr import genv

from certmgr import certmgr
from hostmgr import hostmgr
from proxymgr import proxymgr

WORKDIR=os.path.join(os.environ['PROGRAMDATA'], 'idv-login')

m_certmgr = certmgr()
m_hostmgr = hostmgr()
m_proxy = proxymgr()

def precheck() :
    if ctypes.windll.shell32.IsUserAnAdmin() == 0:
        # relaunch as administrator
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit()

def handle_exit():
    print("[Main] Goodbye!")
    m_hostmgr.remove("service.mkey.163.com")
    os.system("pause")

if __name__ == '__main__':
    precheck()
    print("Welcome to use IdentityV login helper beta version 10.0.0.2")
    print("Project : https://github.com/Alexander-Porter/idv-login/")
    print("This program is free software: you can redistribute it and/or modify")
    print("it under the terms of the GNU General Public License as published by")
    print("the Free Software Foundation, either version 3 of the License, or")
    print("(at your option) any later version.")

    if not os.path.exists(WORKDIR):
        os.mkdir(WORKDIR)

    print(f"[Main] Setting work directory to -> {WORKDIR}")
    os.chdir(os.path.join(WORKDIR))
    
    atexit.register(handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    signal.signal(signal.SIGINT, handle_exit)

    global parser
    parser = argparse.ArgumentParser(
        description="Enter custom parameters to modify the behavior of this script."
        )
    parser.add_argument("-d", "--dns", help="custom the DNS server (Must be DoH)", dest="custom_dns", type=str, default="dns.pub")
    genv.set("custom_dns", parser.parse_args().custom_dns)

    if (os.path.exists('domain_cert.pem') == False) or (os.path.exists('domain_key.pem') == False):
        print("Initializing SSL certificates & keys...")
        
        
        ca_key  = m_certmgr.generate_private_key(bits=2048)
        ca_cert = m_certmgr.generate_ca(privatekey=ca_key)
        m_certmgr.export_cert("root_ca.pem", ca_cert)

        srv_key = m_certmgr.generate_private_key(bits=2048)
        srv_cert = m_certmgr.generate_cert(hostname='service.mkey.163.com', privatekey=srv_key, ca_cert=ca_cert, ca_key=ca_key)

        if (m_certmgr.import_to_root("root_ca.pem") == False) : 
            print("[Main] Failed to import CA to ROOT store!")
            os.system("pause")
            sys.exit(-1)
        
        m_certmgr.export_cert("domain_cert.pem", srv_cert)
        m_certmgr.export_key("domain_key.pem", srv_key)
        print("[Main] Initialized successfully.")

    print("[Main] Redirecting the target to localhost...")

    m_hostmgr.add("service.mkey.163.com", "127.0.0.1")

    print("[Main] Starting the proxy server...")

    if (m_proxy.run() == False) :
        print("[Main] failed to start proxy!")
        sys.exit()
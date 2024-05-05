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

from python_hosts import Hosts, HostsEntry, HostsException
import os

FN_HOSTS = r'C:\Windows\System32\drivers\etc\hosts'

class hostmgr:
    def __init__(self) -> None:
        if (os.path.isfile(FN_HOSTS) == False):
            open(FN_HOSTS, 'w').close()
    def add(self, dnsname, ip) :
        m_host = Hosts()
        m_host.add([HostsEntry(entry_type="ipv4", address=ip, names=[dnsname])])
        try:
            m_host.write()
        except HostsException as e:
            print(e)
            print("[hostmgr] 写hosts文件时出现错误，请检查是否有足够的权限")
            print(f"[hostmgr] 请手动将{dnsname}指向{ip}。即在hosts文件{FN_HOSTS}中添加一行：{ip} {dnsname}")
            input("[hostmgr] 推荐下载火绒安全软件，使用其Hosts文件修改小工具。")
    def remove(self, dnsname) :
        m_host = Hosts()
        m_host.remove_all_matching(name=dnsname)
        m_host.write()
    
    def isExist(self, dnsname)->bool :
        m_host = Hosts()
        return m_host.exists(names=[dnsname])
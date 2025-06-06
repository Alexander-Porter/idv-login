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

from python_hosts import Hosts, HostsEntry, HostsException
from logutil import setup_logger

import os
import sys

FN_HOSTS = Hosts.determine_hosts_path()


class hostmgr:
    def __init__(self) -> None:
        self.logger=setup_logger()
        if (os.path.isfile(FN_HOSTS) == False):
            self.logger.warning(f"Hosts文件不存在，尝试创建中...")
            try:
                open(FN_HOSTS, 'w').close()
            except:
                self.logger.exception(f"Hosts文件创建失败！")
                raise Exception()
        elif not os.access(FN_HOSTS, os.W_OK):
            self.logger.warning(f"Hosts文件不可写，请检查{FN_HOSTS}是否被设置了只读权限！")
            raise Exception()
        else:
            try:
                m_host = Hosts()
                hostsOkay = m_host.exists(['localhost'])
                self.logger.debug(hostsOkay)
            except:
                self.logger.warning(f"Hosts文件编码异常，正在尝试删除{FN_HOSTS}。")
                os.remove(FN_HOSTS)
                open(FN_HOSTS, 'w').close()
                input("按任意键退出。")
                sys.exit(1)

    def add(self, dnsname, ip) :
        m_host = Hosts()
        m_host.add([HostsEntry(entry_type="ipv4", address=ip, names=[dnsname])])
        try:
            m_host.write()
        except:
            self.logger.error(f"写Hosts文件失败，请参考常见问题解决方案。")
            raise Exception()
    def remove(self, dnsname) :
        m_host = Hosts()
        m_host.remove_all_matching(name=dnsname)
        m_host.write()
    
    def isExist(self, dnsname)->bool :
        m_host = Hosts()
        m_host.exists(names=[dnsname])
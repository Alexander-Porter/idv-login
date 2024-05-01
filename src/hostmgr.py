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

from python_hosts import Hosts, HostsEntry
import os

FN_HOSTS = r'C:\Windows\System32\drivers\etc\hosts'

class hostmgr:
    def __init__(self) -> None:
        if (os.path.isfile(FN_HOSTS) == False):
            open(FN_HOSTS, 'w').close()
    def add(self, dnsname, ip) :
        m_host = Hosts()
        m_host.add([HostsEntry(entry_type="ipv4", address=ip, names=[dnsname])])
        m_host.write()
    def remove(self, dnsname) :
        m_host = Hosts()
        m_host.remove_all_matching(name=dnsname)
        m_host.write()

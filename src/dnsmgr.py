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

import random
import requests
import dns.resolver
import dns.nameserver
from envmgr import genv
import socket
from logutil import setup_logger

# Resource Record Types
A = 1
AAAA = 28

# DNS status codes
NOERROR = 0

UNRESERVED_CHARS = (
    "abcdefghijklmnopqrstuvwxyz" "ABCDEFGHIJKLMNOPQRSTUVWXYZ" "0123456789-._~"
)


class InvalidHostName(Exception):
    pass


class SimulatedDNS(object):

    def __init__(self):
        self.logger = setup_logger(__name__)

    def gethostbyname(self, hostname):
        """mimic functionality of socket.gethostbyname"""
        try:
            ip = socket.gethostbyname(hostname)
            return ip
        except socket.gaierror:
            return None

# -*- coding: utf-8 -*-
"""
This package contains all the modules utilised by the python-hosts library.

hosts: Contains the Hosts and HostsEntry classes that represent instances of a
 hosts file, and it's individual lines/entries

utils: Contains helper functions to check the available operations on a hosts
 file and the validity of a hosts file entry

exception: Contains the custom exceptions that are raised in the event of an
 error in processing a hosts file and its entries
"""
# ruff: disable=F401
from python_hosts.hosts import Hosts, HostsEntry # noqa: F401
from python_hosts.utils import (is_readable, is_ipv4, is_ipv6, # noqa: F401
                                valid_hostnames) # noqa: F401
from python_hosts.exception import (HostsException, HostsEntryException, # noqa: F401
                                    InvalidIPv4Address, InvalidIPv6Address,
                                    InvalidComment)

name = "python_hosts"

# -*- coding: utf-8 -*-
"""
This module contains utility functions used by the Hosts and HostsEntry methods
"""
import os
import re

import socket


def is_ipv4(entry):
    """
    Check if the string provided is a valid ipv4 address
    :param entry: A string representation of an IP address
    :return: True if valid, False if invalid
    """
    try:
        if socket.inet_aton(entry):
            return True
    except socket.error:
        return False


def is_ipv6(entry):
    """
    Check if the string provided is a valid ipv6 address
    :param entry: A string representation of an IP address
    :return: True if valid, False if invalid
    """
    try:
        if socket.inet_pton(socket.AF_INET6, entry):
            return True
    except socket.error:
        return False


def valid_hostnames(hostname_list):
    """
    Check if the supplied list of strings are valid hostnames
    :param hostname_list: A list of strings
    :return: True if the strings are valid hostnames, False if not
    """
    for entry in hostname_list:
        if len(entry) > 255:
            return False
        allowed = re.compile(r'(?!-)[A-Z\d-]{1,63}(?<!-)$', re.IGNORECASE)
        if not all(allowed.match(x) for x in entry.split(".")):
            return False
    return True


def is_readable(path=None):
    """
    Test if the supplied filesystem path can be read
    :param path: A filesystem path
    :return: True if the path is a file that can be read. Otherwise, False
    """
    if os.path.isfile(path) and os.access(path, os.R_OK):
        return True
    return False


def dedupe_list(seq):
    """
    Utility function to remove duplicates from a list
    :param seq: The sequence (list) to deduplicate
    :return: A list with original duplicates removed
    """
    seen = set()
    return [x for x in seq if not (x in seen or seen.add(x))]

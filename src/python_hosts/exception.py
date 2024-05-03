# -*- coding: utf-8 -*-

"""
hosts.exceptions
-----------------------

All exceptions used in the hosts code base are defined here.
"""


class HostsException(Exception):
    """ Base exception class. All Hosts-specific exceptions should subclass
    this class.
    """
    pass


class UnableToWriteHosts(HostsException):
    """ Raised when a Hosts file cannot be written. """
    pass


class HostsEntryException(Exception):
    """ Base exception class. All HostsEntry-specific exceptions should
    subclass this class.
    """
    pass


class InvalidIPv4Address(HostsEntryException):
    """ Raised when a HostsEntry is defined as type 'ipv4' but with an
    invalid address.
    """
    pass


class InvalidIPv6Address(HostsEntryException):
    """ Raised when a HostsEntry is defined as type 'ipv6' but
    with an invalid address.
    """
    pass


class InvalidComment(HostsEntryException):
    """ Raised when a HostsEntry is defined as type 'comment' but with an
    invalid comment
    """
    pass

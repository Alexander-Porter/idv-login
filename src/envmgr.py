# coding=UTF-8
class genv:
    global _list
    _list = {}
    def set(key, value):
        _list[key] = value
    def get(key, default = None):
        return _list[key]
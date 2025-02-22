# coding=UTF-8
import json
import os


class genv:
    global _list, _cachePath
    _list = {}
    _cachePath = "config.json"

    def set(key, value, cached=False):
        _list[key] = value
        #if this object is json storeable
        if isinstance(value, (str, int, float, bool, list, dict)) and isinstance(key, str):
            if cached:
                try:
                    if os.path.exists(_cachePath):
                        with open(_cachePath, 'r') as f:
                            data=json.load(f)
                    else:
                        data={}
                    data[key]=value
                    with open(_cachePath, 'w') as f:
                        json.dump(data, f)
                except:
                    print("Failed to cache data",key,value)
                    pass

    def get(key, default=None):
        if key in _list:
            return _list[key]
        else:
            try:
                with open(_cachePath, 'r') as f:
                    data=json.load(f)
                    if key in data:
                        return data[key]
                    else:
                        return default
            except:
                return default


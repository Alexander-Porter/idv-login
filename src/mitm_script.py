
from mitmproxy import http
def request(flow: http.HTTPFlow) -> None:
    if "service.mkey.163.com" in flow.request.pretty_host:
        flow.request.host = "baidu.com"
        flow.request.scheme = "https"
        flow.request.port = 443

# coding=UTF-8
"""本地 DNS 服务器 - 兼容模式专用。

拦截指定域名的 DNS 查询并返回固定 IP，其他请求转发到上游 DNS 服务器。
包含 IP 解析工具函数（硬编码探测 + 上游 DNS 查询）。
"""

import logging
import random
import socket
import ssl
import struct
import threading

logger = logging.getLogger(__name__)

# 预配置的上游 DNS 服务器列表（避免 DNS 回环）
UPSTREAM_DNS_SERVERS = [
    "223.5.5.5",      # 阿里 DNS
    "119.29.29.29",   # 腾讯 DNSPod
    "114.114.114.114",  # 114 DNS
    "8.8.8.8",        # Google DNS
]

# 硬编码的目标服务器 IP（用于 DNS 回环时的备用方案）
HARDCODED_IPS = {
    "service.mkey.163.com": "42.186.193.21",
    "sdk-os.mpsdk.easebar.com": "8.222.80.103",
}


def probe_hardcoded_ip(domain: str, timeout: float = 3.0) -> bool:
    """探测硬编码 IP 是否可访问。

    Args:
        domain: 域名
        timeout: 超时时间（秒）

    Returns:
        是否可访问
    """
    ip = HARDCODED_IPS.get(domain)
    if not ip:
        return False

    try:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        with socket.create_connection((ip, 443), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                return True
    except Exception as e:
        logger.debug(f"探测 {domain} ({ip}) 失败: {e}")
        return False


def resolve_domain_ip(domain: str, use_hardcoded_first: bool = True) -> str | None:
    """解析域名的真实 IP。

    优先使用硬编码 IP（如果可访问），否则通过上游 DNS 解析。

    Args:
        domain: 域名
        use_hardcoded_first: 是否优先尝试硬编码 IP

    Returns:
        IP 地址，解析失败返回 None
    """
    # 1. 尝试硬编码 IP
    if use_hardcoded_first and domain in HARDCODED_IPS:
        hardcoded_ip = HARDCODED_IPS[domain]
        if probe_hardcoded_ip(domain):
            logger.debug(f"使用硬编码 IP: {domain} -> {hardcoded_ip}")
            return hardcoded_ip
        else:
            logger.warning(f"硬编码 IP {hardcoded_ip} 不可访问，尝试 DNS 解析")

    # 2. 通过上游 DNS 解析
    for dns_server in UPSTREAM_DNS_SERVERS:
        try:
            query = _build_dns_query(domain)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(2.0)
                sock.sendto(query, (dns_server, 53))
                response, _ = sock.recvfrom(512)
                ip = _parse_dns_response(response)
                if ip:
                    logger.debug(f"DNS 解析成功: {domain} -> {ip} (via {dns_server})")
                    return ip
        except Exception as e:
            logger.debug(f"DNS 解析失败 ({dns_server}): {e}")
            continue

    # 3. 回退到硬编码 IP（即使不可访问）
    if domain in HARDCODED_IPS:
        logger.warning(f"DNS 解析失败，回退到硬编码 IP: {domain} -> {HARDCODED_IPS[domain]}")
        return HARDCODED_IPS[domain]

    return None


def _build_dns_query(domain: str) -> bytes:
    """构造 DNS A 记录查询报文。"""
    transaction_id = random.randint(0, 65535)
    flags = 0x0100  # Standard query, recursion desired
    header = struct.pack("!HHHHHH", transaction_id, flags, 1, 0, 0, 0)

    question = b""
    for label in domain.split("."):
        question += struct.pack("!B", len(label)) + label.encode("ascii")
    question += b"\x00"
    question += struct.pack("!HH", 1, 1)  # QTYPE=A, QCLASS=IN

    return header + question


def _parse_dns_response(response: bytes) -> str | None:
    """解析 DNS 响应，提取第一个 A 记录。"""
    try:
        pos = 12

        while response[pos] != 0:
            pos += response[pos] + 1
        pos += 5  # Null + QTYPE(2) + QCLASS(2)

        an_count = struct.unpack("!H", response[6:8])[0]
        for _ in range(an_count):
            if response[pos] >= 192:
                pos += 2
            else:
                while response[pos] != 0:
                    pos += response[pos] + 1
                pos += 1

            rtype, rclass, ttl, rdlength = struct.unpack("!HHIH", response[pos:pos + 10])
            pos += 10

            if rtype == 1 and rdlength == 4:  # A record
                ip = ".".join(str(b) for b in response[pos:pos + 4])
                return ip

            pos += rdlength

    except Exception:
        pass

    return None


class DnsPacket:
    """简单的 DNS 报文解析器。"""

    def __init__(self, data: bytes):
        self.raw = data
        self.id = struct.unpack("!H", data[:2])[0]
        self.flags = struct.unpack("!H", data[2:4])[0]
        self.qd_count = struct.unpack("!H", data[4:6])[0]
        self.an_count = struct.unpack("!H", data[6:8])[0]
        self.ns_count = struct.unpack("!H", data[8:10])[0]
        self.ar_count = struct.unpack("!H", data[10:12])[0]

        self.qname = ""
        self.qtype = 0
        self.qclass = 0
        self._parse_question(data[12:])

    def _parse_question(self, data: bytes):
        """解析 DNS 问题部分。"""
        labels = []
        i = 0
        while i < len(data):
            length = data[i]
            if length == 0:
                i += 1
                break
            if length >= 192:
                i += 2
                break
            labels.append(data[i + 1: i + 1 + length].decode("ascii", errors="ignore"))
            i += 1 + length

        self.qname = ".".join(labels).lower()
        if i + 4 <= len(data):
            self.qtype = struct.unpack("!H", data[i:i + 2])[0]
            self.qclass = struct.unpack("!H", data[i + 2:i + 4])[0]

    def build_response(self, ip_address: str) -> bytes:
        """构建包含单个 A 记录的响应报文。

        Args:
            ip_address: 响应的 IP 地址

        Returns:
            DNS 响应报文字节
        """
        response_flags = 0x8180
        header = struct.pack(
            "!HHHHHH",
            self.id,
            response_flags,
            1,  # QDCOUNT
            1,  # ANCOUNT
            0,  # NSCOUNT
            0,  # ARCOUNT
        )

        question_end = 12
        i = 12
        while i < len(self.raw):
            if self.raw[i] == 0:
                question_end = i + 5
                break
            i += 1 + self.raw[i]
        question = self.raw[12:question_end]

        answer = struct.pack(
            "!HHHLH",
            0xC00C,  # 压缩指针
            1,       # TYPE: A
            1,       # CLASS: IN
            300,     # TTL: 300 秒
            4,       # RDLENGTH: 4 字节
        )

        ip_parts = [int(x) for x in ip_address.split(".")]
        answer += struct.pack("!BBBB", *ip_parts)

        return header + question + answer


class LocalDnsServer:
    """本地 DNS 服务器。

    对指定域名返回固定 IP，其他请求转发到上游 DNS 服务器。
    """

    def __init__(
        self,
        intercept_domains: set[str],
        target_ip: str = "127.0.0.1",
        listen_host: str = "127.0.0.1",
        listen_port: int = 53,
    ):
        """
        Args:
            intercept_domains: 要拦截的域名集合
            target_ip: 拦截域名返回的 IP 地址
            listen_host: 监听地址
            listen_port: 监听端口
        """
        self.intercept_domains = {d.lower() for d in intercept_domains}
        self.target_ip = target_ip
        self.listen_host = listen_host
        self.listen_port = listen_port

        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._running = False

    def start(self) -> bool:
        """启动 DNS 服务器。

        Returns:
            是否成功启动
        """
        if self._running:
            logger.warning("DNS 服务器已在运行")
            return True

        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.bind((self.listen_host, self.listen_port))
            self._socket.settimeout(1.0)
        except OSError as e:
            logger.error(f"DNS 服务器绑定端口失败: {e}")
            if self._socket:
                self._socket.close()
                self._socket = None
            return False

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._server_loop,
            name="LocalDnsServer",
            daemon=True,
        )
        self._thread.start()
        self._running = True
        logger.debug(f"本地 DNS 服务器已启动: {self.listen_host}:{self.listen_port}")
        return True

    def stop(self):
        """停止 DNS 服务器。"""
        if not self._running:
            return

        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

        self._running = False
        logger.debug("本地 DNS 服务器已停止")

    def _server_loop(self):
        """服务器主循环。"""
        while not self._stop_event.is_set():
            try:
                data, addr = self._socket.recvfrom(512)
            except socket.timeout:
                continue
            except Exception as e:
                if not self._stop_event.is_set():
                    logger.debug(f"DNS 服务器接收异常: {e}")
                continue

            threading.Thread(
                target=self._handle_request,
                args=(data, addr),
                daemon=True,
            ).start()

    def _handle_request(self, data: bytes, addr: tuple):
        """处理单个 DNS 请求。"""
        try:
            packet = DnsPacket(data)
            logger.debug(f"DNS 查询: {packet.qname} (type={packet.qtype}) from {addr}")

            should_intercept = False
            for domain in self.intercept_domains:
                if packet.qname == domain or packet.qname.endswith("." + domain):
                    should_intercept = True
                    break

            if should_intercept and packet.qtype == 1:  # A 记录
                response = packet.build_response(self.target_ip)
                logger.debug(f"DNS 拦截: {packet.qname} -> {self.target_ip}")
            else:
                response = self._forward_to_upstream(data)
                if response is None:
                    logger.warning(f"DNS 转发失败: {packet.qname}")
                    return

            self._socket.sendto(response, addr)

        except Exception as e:
            logger.debug(f"DNS 请求处理异常: {e}")

    def _forward_to_upstream(self, data: bytes) -> bytes | None:
        """将 DNS 请求转发到上游服务器。"""
        for dns_server in UPSTREAM_DNS_SERVERS:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.settimeout(2.0)
                    sock.sendto(data, (dns_server, 53))
                    response, _ = sock.recvfrom(512)
                    return response
            except Exception:
                continue

        return None

    @property
    def is_running(self) -> bool:
        """服务器是否正在运行。"""
        return self._running

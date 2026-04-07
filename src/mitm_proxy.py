# coding=UTF-8
"""
Copyright (c) 2026 KKeygen

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

import asyncio
import os
import socket
import sys
import threading

from envmgr import genv
from logutil import setup_logger


logger = setup_logger()

# Default proxy listen port
DEFAULT_PROXY_PORT = 10717

# Compat mode reverse proxy port (HTTPS 443)
COMPAT_HTTPS_PORT = 443


# ==================================================================
# DNS 回环防止机制
# 重写 socket.getaddrinfo，对目标域名返回预解析的真实 IP
# ==================================================================

_dns_cache: dict[tuple[str, int], list] = {}
_original_getaddrinfo = socket.getaddrinfo


def _is_ipv4(s: str) -> bool:
    return ":" not in s


def add_custom_dns(domain: str, port: int, ip: str):
    """添加自定义 DNS 解析结果，防止 DNS 回环。

    在兼容模式下，Hosts 文件或 NRPT 将目标域名指向 127.0.0.1。
    当 mitmproxy 需要将请求转发到真实服务器时，必须绕过系统 DNS，
    直接使用预解析的真实 IP。

    Args:
        domain: 域名
        port: 端口
        ip: 真实 IP 地址
    """
    key = (domain, port)
    if _is_ipv4(ip):
        value = (
            socket.AddressFamily.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            (ip, port),
        )
    else:
        value = (
            socket.AddressFamily.AF_INET6,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            (ip, port, 0, 0),
        )
    _dns_cache[key] = [value]
    logger.debug(f"添加自定义 DNS: {domain}:{port} -> {ip}")


def remove_custom_dns(domain: str, port: int):
    """移除自定义 DNS 解析。"""
    key = (domain, port)
    _dns_cache.pop(key, None)


def clear_custom_dns():
    """清除所有自定义 DNS 解析。"""
    _dns_cache.clear()


def _patched_getaddrinfo(*args):
    """替换的 getaddrinfo 函数。"""
    try:
        key = args[:2]  # (hostname, port)
        if key in _dns_cache:
            return _dns_cache[key]
    except Exception:
        pass
    return _original_getaddrinfo(*args)


# 替换 socket.getaddrinfo
socket.getaddrinfo = _patched_getaddrinfo


# Re-export from split modules for backward compatibility
from local_dns_server import (  # noqa: E402, F401
    UPSTREAM_DNS_SERVERS, HARDCODED_IPS,
    probe_hardcoded_ip, resolve_domain_ip,
    DnsPacket, LocalDnsServer,
)
from dns_policy import (  # noqa: E402, F401
    is_nrpt_available, add_nrpt_rule, remove_nrpt_rule,
    remove_all_nrpt_rules, flush_dns_cache,
    DnsPolicyManager,
)


class MitmProxyManager:
    """Manages mitmproxy running in normal (regular) proxy mode.

    Replaces the old ``proxymgr`` / ``macProxyMgr`` which listened on
    port 443 and required hosts-file manipulation.  The new approach
    sets ``HTTP_PROXY`` / ``HTTPS_PROXY`` environment variables for the
    game subprocess so that all game traffic flows through mitmproxy.

    Certificate generation and system trust-store installation is
    handled by ``generate_certificates_if_needed()`` in ``main.py``
    *before* this manager is started.  The mitmproxy confdir is
    pre-populated with ``mitmproxy-ca.pem`` (key + cert) and
    ``mitmproxy-ca-cert.pem`` (cert only).

    Modes:
    - "regular" (default): Standard HTTP proxy on configurable port
    - "compat": Reverse proxy on port 443 for DNS-based traffic interception
    """

    def __init__(self, *, addon, port=DEFAULT_PROXY_PORT, mode="regular"):
        """
        Args:
            addon: The mitmproxy addon to use
            port: Proxy listen port (used in regular mode)
            mode: "regular" for HTTP proxy, "compat" for reverse proxy on 443
        """
        self.addon = addon
        self.port = port
        self.mode = mode
        self._thread: threading.Thread | None = None
        self._master = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------
    # Port selection
    # ------------------------------------------------------------------

    @staticmethod
    def _is_port_available(port: int) -> bool:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return True
            except OSError:
                return False

    def _resolve_port(self):
        """If the configured port is occupied, pick an available one."""
        # In compat mode, we must use port 443
        if self.mode == "compat":
            if not self._is_port_available(COMPAT_HTTPS_PORT):
                logger.error(f"兼容模式需要端口 {COMPAT_HTTPS_PORT}，但该端口已被占用")
                raise RuntimeError(f"Port {COMPAT_HTTPS_PORT} is not available for compat mode")
            self.port = COMPAT_HTTPS_PORT
            return

        if self._is_port_available(self.port):
            return
        original = self.port
        # Try a few ports near the original, then pick a random high port
        for candidate in range(original + 1, original + 20):
            if self._is_port_available(candidate):
                self.port = candidate
                logger.warning(f"端口 {original} 已被占用，改用端口 {self.port}")
                return
        # Fallback: let the OS pick a random available port
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        logger.warning(f"端口 {original} 及附近端口均被占用，改用随机端口 {self.port}")

    # ------------------------------------------------------------------
    # Certificate helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_confdir() -> str:
        """Return the mitmproxy config directory used for certs."""
        return os.path.join(genv.get("FP_WORKDIR", ""), "mitmproxy-conf")

    # ------------------------------------------------------------------
    # Proxy lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Start mitmproxy in a daemon thread."""
        if self._thread and self._thread.is_alive():
            logger.warning("mitmproxy 已经在运行中")
            return

        self._resolve_port()

        self._thread = threading.Thread(
            target=self._run_proxy,
            name="mitmproxy-worker",
            daemon=True,
        )
        self._thread.start()

        mode_desc = "兼容模式 (反向代理)" if self.mode == "compat" else "常规代理模式"
        logger.info(f"mitmproxy {mode_desc}已启动，监听端口 {self.port}")

    def _run_proxy(self):
        """Thread target: create an asyncio event loop and run mitmproxy."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._run_proxy_async())
        except Exception as e:
            logger.exception(f"mitmproxy 运行出错: {e}")
        finally:
            # 取消所有待处理的任务，避免 "task destroyed but pending" 警告
            try:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                
                # 等待所有任务完成取消
                if pending:
                    self._loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception:
                pass
            
            self._loop.close()

    async def _run_proxy_async(self):
        """Async entry point – DumpMaster needs a *running* event loop."""
        import logging as _logging
        from mitmproxy.options import Options
        from mitmproxy.tools.dump import DumpMaster

        # 抑制 mitmproxy 自身的控制台日志输出
        _logging.getLogger("mitmproxy").setLevel(_logging.ERROR)

        confdir = self.get_confdir()

        if self.mode == "compat":
            # 兼容模式：作为反向代理监听 443 端口
            # 客户端（游戏）的 DNS 被劫持到 127.0.0.1，会直接连接 127.0.0.1:443
            # 使用 reverse 模式将请求转发到默认目标服务器
            # _CompatModeAddon 会根据 Host 头将请求路由到正确的服务器
            default_target = genv.get("DOMAIN_TARGET", "service.mkey.163.com")
            opts = Options(
                listen_host="127.0.0.1",
                listen_port=self.port,
                confdir=confdir,
                ssl_insecure=False,
                mode=[f"reverse:https://{default_target}/"],
            )
        else:
            # 常规代理模式
            opts = Options(
                listen_host="127.0.0.1",
                listen_port=self.port,
                confdir=confdir,
                ssl_insecure=False,  # DO verify upstream certs
            )

        self._master = DumpMaster(opts, with_dumper=False)
        self._master.addons.add(self.addon)
        if self.mode == "compat":
            # 兼容模式添加特殊的请求重写 addon
            self._master.addons.add(_CompatModeAddon())
        self._master.addons.add(_ResponseLogAddon())
        await self._master.run()

    def stop(self):
        """Shut down the mitmproxy proxy."""
        if self._master:
            try:
                self._master.shutdown()
            except Exception:
                pass
        
        # 等待代理线程优雅退出
        if self._thread and self._thread.is_alive():
            try:
                self._thread.join(timeout=2.0)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Game launching
    # ------------------------------------------------------------------

    def get_proxy_env(self) -> dict:
        """Return a copy of ``os.environ`` with proxy variables set.
        
        在兼容模式下，流量通过 DNS 劫持拦截，不需要代理环境变量。
        因此兼容模式返回不包含代理变量的环境副本。
        """
        env = os.environ.copy()
        
        # 兼容模式：不设置代理环境变量，流量通过 DNS 劫持处理
        if self.mode == "compat":
            return env
        
        # 常规模式 / 进程模式：设置代理环境变量
        proxy_url = f"http://127.0.0.1:{self.port}"
        env["HTTP_PROXY"] = proxy_url
        env["HTTPS_PROXY"] = proxy_url
        # 设置 NO_PROXY 以绕过特定域名
        no_proxy_value = self._get_no_proxy_value()
        if no_proxy_value:
            env["NO_PROXY"] = no_proxy_value
        if sys.platform != "win32":
            # Unix 环境变量区分大小写，需要同时设置小写
            env["http_proxy"] = proxy_url
            env["https_proxy"] = proxy_url
            if no_proxy_value:
                env["no_proxy"] = no_proxy_value
        return env

    def _get_no_proxy_value(self) -> str:
        """从 CloudRes 获取 NO_PROXY 域名列表并拼接为逗号分隔的字符串。"""
        try:
            from cloudRes import CloudRes
            cloudres = CloudRes()
            domains = cloudres.get_no_proxy_domains()
            return ",".join(domains) if domains else ""
        except Exception:
            return ""


class _CompatModeAddon:
    """兼容模式的请求重写 addon。

    在兼容模式下，客户端直接连接到 127.0.0.1:443，
    mitmproxy 使用反向代理模式接收请求。
    此 addon 负责根据 Host 头将请求路由到正确的上游服务器。
    """

    def request(self, flow):
        from mitmproxy import http

        # 获取原始 Host 头
        host = flow.request.host_header or flow.request.host
        if not host:
            return

        # 获取目标域名配置
        from envmgr import genv
        target_domains = {
            genv.get("DOMAIN_TARGET", "service.mkey.163.com"),
            genv.get("DOMAIN_TARGET_OVERSEA", "sdk-os.mpsdk.easebar.com"),
        }

        # 如果是目标域名，修改 flow 的目标地址
        if host in target_domains:
            # 重写请求的目标服务器为真实服务器
            flow.request.host = host
            flow.request.port = 443
            flow.request.scheme = "https"
            logger.debug(f"[compat] 路由请求: {flow.request.pretty_url} -> {host}:443")


class _ResponseLogAddon:
    """仅将非 200/404 的响应以 DEBUG 级别写入日志，不输出到控制台。"""

    def response(self, flow):
        code = flow.response.status_code
        if code not in (200, 404):
            logger.debug(
                f"[mitmproxy] {flow.request.method} {flow.request.pretty_url} -> {code}"
            )

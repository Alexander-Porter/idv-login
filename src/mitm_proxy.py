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
import threading

from envmgr import genv
from logutil import setup_logger


logger = setup_logger()

# Default proxy listen port
DEFAULT_PROXY_PORT = 8899


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
    """

    def __init__(self, *, addon, port=DEFAULT_PROXY_PORT):
        self.addon = addon
        self.port = port
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
        logger.info(f"mitmproxy 代理已启动，监听端口 {self.port}")

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
        opts = Options(
            listen_host="127.0.0.1",
            listen_port=self.port,
            confdir=confdir,
            ssl_insecure=True,  # don't verify upstream certs
        )
        self._master = DumpMaster(opts, with_dumper=False)
        self._master.addons.add(self.addon)
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
        """Return a copy of ``os.environ`` with proxy variables set."""
        env = os.environ.copy()
        proxy_url = f"http://127.0.0.1:{self.port}"
        env["HTTP_PROXY"] = proxy_url
        env["HTTPS_PROXY"] = proxy_url
        env["http_proxy"] = proxy_url
        env["https_proxy"] = proxy_url
        return env


class _ResponseLogAddon:
    """仅将非 200/404 的响应以 DEBUG 级别写入日志，不输出到控制台。"""

    def response(self, flow):
        code = flow.response.status_code
        if code not in (200, 404):
            logger.debug(
                f"[mitmproxy] {flow.request.method} {flow.request.pretty_url} -> {code}"
            )

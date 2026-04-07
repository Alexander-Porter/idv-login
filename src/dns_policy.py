# coding=UTF-8
"""DNS 策略管理 - 兼容模式专用 (NRPT/Hosts)。

统一管理 NRPT 和 Hosts 方式的 DNS 劫持。优先使用 NRPT，不可用时回退到 Hosts。
"""

import logging
import subprocess
import sys

logger = logging.getLogger(__name__)

# Windows CREATE_NO_WINDOW 标志，防止子进程弹出控制台窗口
_CREATE_NO_WINDOW = 0
if sys.platform == "win32":
    _CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW

# 用于标识本工具创建的 NRPT 规则的显示名称前缀
_NRPT_RULE_PREFIX = "IDVLogin_"


def is_nrpt_available() -> bool:
    """检测 Windows NRPT 命令是否可用。

    NRPT 功能需要 Windows 7+ 且具有管理员权限。
    """
    if sys.platform != "win32":
        return False

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Command Add-DnsClientNrptRule -ErrorAction SilentlyContinue"],
            capture_output=True,
            timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        )
        return result.returncode == 0 and b"Add-DnsClientNrptRule" in result.stdout
    except Exception as e:
        logger.debug(f"检测 NRPT 可用性失败: {e}")
        return False


def add_nrpt_rule(domain: str, dns_server: str = "127.0.0.1") -> bool:
    """为指定域名添加 NRPT 规则，将 DNS 解析指向本地 DNS 服务器。

    Args:
        domain: 要劫持的域名，如 "service.mkey.163.com"
        dns_server: DNS 服务器地址，默认 "127.0.0.1"

    Returns:
        是否成功添加规则
    """
    if sys.platform != "win32":
        logger.warning("NRPT 仅支持 Windows 平台")
        return False

    rule_name = f"{_NRPT_RULE_PREFIX}{domain.replace('.', '_')}"

    # 先尝试删除同名规则（如果存在）
    remove_nrpt_rule(domain)

    ps_cmd = (
        f'Add-DnsClientNrptRule -Namespace ".{domain}" '
        f'-NameServers "{dns_server}" '
        f'-DisplayName "{rule_name}" '
        f'-ErrorAction Stop'
    )

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            timeout=15,
            text=True,
            creationflags=_CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            logger.debug(f"已添加 NRPT 规则: {domain} -> {dns_server}")
            return True
        else:
            logger.error(f"添加 NRPT 规则失败: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"添加 NRPT 规则异常: {e}")
        return False


def remove_nrpt_rule(domain: str) -> bool:
    """移除指定域名的 NRPT 规则。

    Args:
        domain: 域名

    Returns:
        是否成功移除（规则不存在也返回 True）
    """
    if sys.platform != "win32":
        return True

    rule_name = f"{_NRPT_RULE_PREFIX}{domain.replace('.', '_')}"

    ps_cmd = (
        f'Get-DnsClientNrptRule | '
        f'Where-Object {{ $_.DisplayName -eq "{rule_name}" }} | '
        f'Remove-DnsClientNrptRule -Force -ErrorAction SilentlyContinue'
    )

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
        logger.debug(f"已移除 NRPT 规则: {domain}")
        return True
    except Exception as e:
        logger.warning(f"移除 NRPT 规则失败: {e}")
        return False


def remove_all_nrpt_rules() -> bool:
    """移除本工具创建的所有 NRPT 规则。"""
    if sys.platform != "win32":
        return True

    ps_cmd = (
        f'Get-DnsClientNrptRule | '
        f'Where-Object {{ $_.DisplayName -like "{_NRPT_RULE_PREFIX}*" }} | '
        f'Remove-DnsClientNrptRule -Force -ErrorAction SilentlyContinue'
    )

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
        logger.debug("已移除所有 IDVLogin NRPT 规则")
        return True
    except Exception as e:
        logger.warning(f"移除 NRPT 规则失败: {e}")
        return False


def flush_dns_cache() -> bool:
    """刷新 DNS 缓存。"""
    if sys.platform != "win32":
        return True

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Clear-DnsClientCache"],
            capture_output=True,
            timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        )
        logger.debug("已刷新 DNS 缓存")
        return True
    except Exception as e:
        logger.warning(f"刷新 DNS 缓存失败: {e}")
        return False


def _setup_nrpt_batch(domains: list[str], target_ip: str) -> str:
    """用单次 PowerShell 调用完成清理旧规则、添加新规则、刷新缓存。

    跳过 Get-Command 检测，直接 try Add-DnsClientNrptRule，失败则回退。

    Returns:
        "OK" / "FAILED"
    """
    if sys.platform != "win32":
        return "FAILED"

    add_cmds = "\n    ".join(
        f'Add-DnsClientNrptRule -Namespace ".{d}" '
        f'-NameServers "{target_ip}" '
        f'-DisplayName "{_NRPT_RULE_PREFIX}{d.replace(".", "_")}" '
        f'-ErrorAction Stop'
        for d in domains
    )

    ps_script = (
        f'Get-DnsClientNrptRule | Where-Object {{ $_.DisplayName -like "{_NRPT_RULE_PREFIX}*" }}'
        f' | Remove-DnsClientNrptRule -Force -ErrorAction SilentlyContinue\n'
        f'try {{\n    {add_cmds}\n}} catch {{\n'
        f'    Get-DnsClientNrptRule | Where-Object {{ $_.DisplayName -like "{_NRPT_RULE_PREFIX}*" }}'
        f' | Remove-DnsClientNrptRule -Force -ErrorAction SilentlyContinue\n'
        f'    Write-Output "FAILED"; exit 0\n}}\n'
        f'Clear-DnsClientCache -ErrorAction SilentlyContinue\n'
        f'Write-Output "OK"'
    )

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=_CREATE_NO_WINDOW,
        )
        output = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
        if output == "OK":
            return "OK"
        else:
            logger.warning(f"NRPT 设置失败: {result.stderr.strip()}")
            return "FAILED"
    except Exception as e:
        logger.error(f"NRPT 批量设置异常: {e}")
        return "FAILED"


def _cleanup_nrpt_batch():
    """单次 PowerShell 调用完成 NRPT 规则删除 + DNS 缓存刷新。"""
    if sys.platform != "win32":
        return

    ps_script = (
        f'Get-DnsClientNrptRule | Where-Object {{ $_.DisplayName -like "{_NRPT_RULE_PREFIX}*" }}'
        f' | Remove-DnsClientNrptRule -Force -ErrorAction SilentlyContinue\n'
        f'Clear-DnsClientCache -ErrorAction SilentlyContinue'
    )

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
    except Exception as e:
        logger.warning(f"NRPT 批量清理失败: {e}")


class DnsPolicyManager:
    """DNS 策略管理器 - 统一管理 NRPT 和 Hosts 方式的 DNS 劫持。

    优先使用 NRPT，如果不可用则回退到 Hosts 文件方式。
    """

    def __init__(self, domains: list[str], target_ip: str = "127.0.0.1"):
        """
        Args:
            domains: 要劫持的域名列表
            target_ip: 劫持目标 IP，默认 127.0.0.1
        """
        self.domains = domains
        self.target_ip = target_ip
        self._use_nrpt = False
        self._active = False
        self._hostmgr = None

    def setup(self) -> bool:
        """设置 DNS 劫持策略（单次 PowerShell 调用完成 NRPT 检测+设置+刷新）。

        Returns:
            是否成功设置
        """
        if self._active:
            logger.warning("DNS 策略已激活，无需重复设置")
            return True

        # 单次 PowerShell 调用：旧规则清理、新规则添加、DNS 刷新
        nrpt_result = _setup_nrpt_batch(self.domains, self.target_ip)
        if nrpt_result == "OK":
            self._use_nrpt = True
            self._active = True
            logger.debug("DNS 策略已设置 (方式: NRPT)")
            return True

        logger.warning("NRPT 设置失败，尝试 Hosts 方式")

        # 回退到 Hosts 文件方式
        logger.debug("使用 Hosts 文件方式进行 DNS 劫持")
        try:
            from hostmgr import hostmgr
            self._hostmgr = hostmgr()
            for domain in self.domains:
                if self._hostmgr.isExist(domain):
                    self._hostmgr.remove(domain)
                self._hostmgr.add(domain, self.target_ip)
                logger.debug(f"已添加 Hosts 记录: {domain} -> {self.target_ip}")

            flush_dns_cache()
            self._use_nrpt = False
            self._active = True
            return True
        except Exception as e:
            logger.error(f"Hosts 文件方式设置失败: {e}")
            return False

    def cleanup(self):
        """清理 DNS 劫持策略，恢复原始状态。"""
        if not self._active:
            return

        if self._use_nrpt:
            # 单次 PowerShell 调用完成规则删除 + DNS 缓存刷新
            _cleanup_nrpt_batch()
            logger.debug("已清理 NRPT DNS 策略")
        else:
            if self._hostmgr is None:
                try:
                    from hostmgr import hostmgr
                    self._hostmgr = hostmgr()
                except Exception:
                    pass

            if self._hostmgr:
                for domain in self.domains:
                    try:
                        if self._hostmgr.isExist(domain):
                            self._hostmgr.remove(domain)
                            logger.debug(f"已移除 Hosts 记录: {domain}")
                    except Exception as e:
                        logger.warning(f"移除 Hosts 记录失败 ({domain}): {e}")
            flush_dns_cache()

        self._active = False

    @property
    def is_using_nrpt(self) -> bool:
        """是否正在使用 NRPT 方式。"""
        return self._use_nrpt

    @property
    def is_active(self) -> bool:
        """DNS 策略是否已激活。"""
        return self._active

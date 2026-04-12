def _ensure_pillow():
    """确保 pillow 可用；缺失时在后台线程通过国内镜像安装"""
    import sys

    # PyInstaller 不走 pip
    if getattr(sys, 'frozen', False):
        return

    # 版本准入：v6.0.1+ 发行包已内置 pillow，无需安装
    import re
    from envmgr import genv
    version = genv.get("VERSION", "")
    m = re.match(r'v?(\d+)\.(\d+)\.(\d+)', version)
    if m and (int(m.group(1)), int(m.group(2)), int(m.group(3))) >= (6, 0, 1):
        return

    if genv.get("pillow_ensured", False):
        return

    try:
        import PIL          # noqa: F401
        genv.set("pillow_ensured", True, True)
        return
    except ImportError:
        pass

    from logutil import setup_logger
    logger = setup_logger()
    logger.info("pillow 未安装，将在后台尝试安装...")

    import threading, subprocess, os

    def _install():
        mirrors = [
            ("https://pypi.tuna.tsinghua.edu.cn/simple",  "pypi.tuna.tsinghua.edu.cn"),
            ("https://mirrors.aliyun.com/pypi/simple",     "mirrors.aliyun.com"),
            ("https://pypi.mirrors.ustc.edu.cn/simple",    "pypi.mirrors.ustc.edu.cn"),
            ("https://mirror.baidu.com/pypi/simple",       "mirror.baidu.com"),
        ]
        # 清除代理环境变量，避免经过本工具的代理
        env = os.environ.copy()
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                   "ALL_PROXY", "all_proxy"):
            env.pop(k, None)

        for url, host in mirrors:
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "pillow",
                     "--quiet", "--index-url", url, "--trusted-host", host],
                    env=env, timeout=120,
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                )
                genv.set("pillow_ensured", True, True)
                logger.info(f"pillow 安装成功（源: {host}）")
                return
            except Exception as e:
                logger.warning(f"pillow 从 {host} 安装失败: {e}")

        logger.error("pillow 自动安装失败，所有镜像源均不可用")

    threading.Thread(target=_install, daemon=True, name="pillow-installer").start()


def run_once():
    try:
        _ensure_pillow()
    except Exception:
        pass
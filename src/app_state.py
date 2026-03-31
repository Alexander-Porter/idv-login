# coding=UTF-8
"""Typed module-level singletons for cross-module shared objects.

Instead of ``genv.set("PROXY_MGR", mgr)`` / ``genv.get("PROXY_MGR")``,
use ``import app_state; app_state.proxy_mgr = mgr`` /
``app_state.proxy_mgr``.  This lets static-analysis tools (pyflakes,
mypy, pylint …) resolve types and detect dead code.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from channelmgr import ChannelManager
    from cloudRes import CloudRes
    from mitm_proxy import MitmProxyManager
    from uimgr import UIManager
    from PyQt6.QtWidgets import QApplication

channels_helper: ChannelManager | None = None
fake_device: dict | None = None
cloud_res: CloudRes | None = None
app: QApplication | None = None
ui_mgr: UIManager | None = None
proxy_mgr: MitmProxyManager | None = None

# 用于跨线程调度的辅助对象
_main_thread_invoker = None


def _ensure_invoker():
    """确保主线程调度器已初始化（必须在主线程调用）。"""
    global _main_thread_invoker
    if _main_thread_invoker is None and app is not None:
        from PyQt6.QtCore import QObject, pyqtSignal

        class MainThreadInvoker(QObject):
            invoke_signal = pyqtSignal(object)

            def __init__(self):
                super().__init__()
                self.invoke_signal.connect(self._do_invoke)

            def _do_invoke(self, func):
                try:
                    func()
                except Exception:
                    import traceback
                    traceback.print_exc()

        _main_thread_invoker = MainThreadInvoker()


def run_on_main_thread(func: Callable[[], None]) -> None:
    """在 Qt 主线程中执行 func。

    可以从任何线程安全调用。如果没有 Qt 应用运行，则直接执行。
    """
    global _main_thread_invoker
    if _main_thread_invoker is not None:
        _main_thread_invoker.invoke_signal.emit(func)
    elif app is not None:
        # invoker 未初始化，但 app 存在 - 尝试直接用 QTimer
        # 注意：这只在主线程中调用时有效
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, func)
    else:
        func()

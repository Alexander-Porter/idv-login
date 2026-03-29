# coding=UTF-8
"""Typed module-level singletons for cross-module shared objects.

Instead of ``genv.set("PROXY_MGR", mgr)`` / ``genv.get("PROXY_MGR")``,
use ``import app_state; app_state.proxy_mgr = mgr`` /
``app_state.proxy_mgr``.  This lets static-analysis tools (pyflakes,
mypy, pylint …) resolve types and detect dead code.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

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

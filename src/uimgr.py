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

import json
import os
import sys
import threading
from urllib.parse import parse_qs, urlparse

from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, QUrl
from PyQt6.QtWebEngineCore import (
    QWebEngineUrlScheme,
    QWebEngineUrlSchemeHandler,
    QWebEngineUrlRequestJob,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QMainWindow

from envmgr import genv
from logutil import setup_logger

logger = setup_logger()

# The custom URL scheme for the local UI.
SCHEME_NAME = b"idvlogin"


def register_url_scheme():
    """Register the ``idvlogin://`` scheme with QtWebEngine.

    **Must** be called *before* ``QApplication`` is created.
    """
    scheme = QWebEngineUrlScheme(SCHEME_NAME)
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.HostAndPort)
    scheme.setFlags(
        QWebEngineUrlScheme.Flag.SecureScheme
        | QWebEngineUrlScheme.Flag.LocalScheme
        | QWebEngineUrlScheme.Flag.LocalAccessAllowed
        | QWebEngineUrlScheme.Flag.CorsEnabled
    )
    QWebEngineUrlScheme.registerScheme(scheme)


class IDVLoginSchemeHandler(QWebEngineUrlSchemeHandler):
    """Handles ``idvlogin://`` requests inside QtWebEngine.

    Routes are dispatched to :class:`local_handler.LocalRequestHandler`
    so the same logic is shared between the mitmproxy addon and the
    Qt-based UI.
    """

    def __init__(self, *, game_helper, ui_logger, parent=None):
        super().__init__(parent)
        self.game_helper = game_helper
        self.ui_logger = ui_logger

    def requestStarted(self, job: QWebEngineUrlRequestJob):
        url: QUrl = job.requestUrl()
        path = url.path() or "/"
        method = job.requestMethod().data().decode("utf-8", errors="replace")

        # Parse query parameters
        from PyQt6.QtCore import QUrlQuery
        qurl_query = QUrlQuery(url)
        args = {item[0]: item[1] for item in qurl_query.queryItems()}

        # Read body for POST
        json_body = None
        if method.upper() == "POST":
            device = job.requestBody()
            if device and device.isOpen():
                raw = bytes(device.readAll())
                try:
                    json_body = json.loads(raw) if raw else {}
                except Exception:
                    json_body = {}

        # Special case: serve the main page
        if path in ("/", "/open", "/index"):
            path = "/_idv-login/index"
        elif not path.startswith("/_idv-login/"):
            path = "/_idv-login" + path

        # Dispatch to shared handler
        from local_handler import LocalRequestHandler

        handler = LocalRequestHandler(
            game_helper=self.game_helper,
            logger=self.ui_logger,
        )

        try:
            status, headers, body = handler.handle_simple(
                path, method.upper(), args, json_body
            )
        except Exception as e:
            self.ui_logger.exception(f"处理本地请求失败: {path}")
            body = json.dumps({"error": str(e)}).encode("utf-8")
            status = 500
            headers = {"Content-Type": "application/json"}

        content_type = headers.get("Content-Type", "application/octet-stream")
        buf = QBuffer(parent=job)
        buf.setData(QByteArray(body))
        buf.open(QIODevice.OpenModeFlag.ReadOnly)
        job.reply(content_type.encode("utf-8"), buf)


class UIManager:
    """Manages the PyQt6/QtWebEngine window for the account management UI.

    The window is opened when the ``idvlogin://`` URI scheme is
    triggered (e.g. from a QR code redirect) or when the user
    wants to manage accounts.
    """

    def __init__(self, *, game_helper, ui_logger):
        self.game_helper = game_helper
        self.ui_logger = ui_logger
        self._window: QMainWindow | None = None
        self._view: QWebEngineView | None = None
        self._scheme_handler: IDVLoginSchemeHandler | None = None

    def _ensure_window(self):
        if self._window is not None:
            return

        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            raise RuntimeError("QApplication 未创建")

        self._window = QMainWindow()
        self._window.setWindowTitle("渠道服账号管理")
        self._window.resize(900, 700)

        self._view = QWebEngineView(self._window)
        self._window.setCentralWidget(self._view)

        # Install the custom scheme handler on this view's profile.
        profile = self._view.page().profile()
        self._scheme_handler = IDVLoginSchemeHandler(
            game_helper=self.game_helper,
            ui_logger=self.ui_logger,
            parent=self._view,
        )
        profile.installUrlSchemeHandler(SCHEME_NAME, self._scheme_handler)

    def open_for_game(self, game_id: str = ""):
        """Show the UI window for the given *game_id*."""
        self._ensure_window()
        url = QUrl(f"idvlogin://app/_idv-login/index?game_id={game_id}")
        self._view.load(url)
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

    def close(self):
        if self._window:
            self._window.close()

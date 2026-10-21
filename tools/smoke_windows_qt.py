"""Packaging smoke check, run with the staged Windows embedded interpreter.

Only synthetic local HTML is loaded. Do not start main.py: it changes system
proxy/certificate/hosts settings and is not a packaging check.
"""

import os
from pathlib import Path
import sys

os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"  # same as main.py

from PyQt6 import QtCore, QtGui, QtNetwork, QtPrintSupport, QtWebChannel, QtWidgets
from PyQt6.QtWebEngineWidgets import QWebEngineView


app = QtWidgets.QApplication([])
icon = QtGui.QIcon(str(Path(sys.argv[1]).resolve()))
if icon.pixmap(32, 32).isNull():
    raise RuntimeError("Packaged ICO image plugin did not load")
if not QtNetwork.QSslSocket.supportsSsl():
    raise RuntimeError("Packaged Windows TLS backend did not load")
print(f"Qt {QtCore.QT_VERSION_STR}, platform={app.platformName()}, style={app.style().objectName()}")
view = QWebEngineView()
view.resize(320, 200)
view.show()
result = 1


def checked(value):
    global result
    result = 0 if value == "packaging-ok" else 1
    app.quit()


def loaded(ok):
    if not ok:
        app.quit()
        return
    view.page().runJavaScript("document.getElementById('result').textContent", checked)


view.loadFinished.connect(loaded)
QtCore.QTimer.singleShot(30000, app.quit)
view.setHtml("<html><body><p id='result'></p><script>"
             "document.getElementById('result').textContent='packaging-ok';"
             "</script></body></html>")
app.exec()
view.close()
if result:
    raise RuntimeError("Packaged WebEngine failed to render local HTML and execute JavaScript")
print("Windows Qt packaging smoke passed: bindings, ICO, TLS, WebEngine renderer and JavaScript")

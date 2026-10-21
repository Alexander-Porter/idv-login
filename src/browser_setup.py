"""Native first-run/recovery UI; it must work before a browser is installed."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


class BrowserSetupDialog(QDialog):
    def __init__(self, message, *, on_retry, on_cancel, parent=None):
        super().__init__(parent)
        self.setWindowTitle("独立浏览器准备")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        label = QLabel(str(message))
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        layout.addWidget(label)
        note = QLabel(
            "需要 Firefox 153 ESR 或 158 正式版。未来主版本需先更新本工具。安装后返回这里点击重试，无需设为默认浏览器。\n"
            "工具仅使用自己的资料目录，不会读取日常 Firefox 的书签、密码或登录状态。\n"
            "下载和安装由您自行决定，工具不会自动安装或修改系统协议关联。")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QHBoxLayout()
        layout.addLayout(buttons)
        download = QPushButton("打开 Firefox 官方下载页")
        def open_download():
            import webbrowser
            if not webbrowser.open("https://www.mozilla.org/firefox/enterprise/"):
                note.setText(note.text() + "\n请在浏览器中打开 https://www.mozilla.org/firefox/enterprise/")
        download.clicked.connect(open_download)
        buttons.addWidget(download)
        retry = QPushButton("已安装 / 已更新，重试")
        retry.clicked.connect(self.accept)
        retry.setDefault(True)
        buttons.addWidget(retry)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self.finished.connect(lambda result: on_retry() if result == QDialog.DialogCode.Accepted else on_cancel())

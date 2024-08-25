from PyQt5.QtCore import QUrl
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QPushButton, QWidget
from PyQt5.QtCore import QUrl, QTimer

class WebBroswer(QWidget):
    class WebEngineView(QWebEngineView):
        def createWindow(self, QWebEnginePage_WebWindowType):
            page = QWebEngineView(self)
            page.urlChanged.connect(self.on_url_changed)
            return page

        def on_url_changed(self, url):
            self.setUrl(url)

    def __init__(self):
        self.app = QApplication([])
        super().__init__()
        self.view = self.WebEngineView()
        self.profile: QWebEngineProfile = QWebEngineProfile.defaultProfile()
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self.profile.cookieStore().cookieAdded.connect(self.cookie_added)
        self.page = self.view.page()
        self.cookies = {}
        self.result = ""
        # 创建清除Cookie按钮
        self.clear_cookie_button = QPushButton("清除Cookie")
        self.clear_cookie_button.clicked.connect(self.clear_cookies)

        # 设置布局
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.view)
        self.layout.addWidget(self.clear_cookie_button)
        self.setLayout(self.layout)

    def set_url(self, url):
        self.view.load(QUrl(url))

    def listen_url_change(self):
        self.page.urlChanged.connect(self.handle_url_change)

    def handle_url_change(self, url):
        print(f"URL changed: {url.toString()}")
        if self.verify(url.toString()):
            if self.parseReslt(url.toString()):
                self.cleanup()

    def export_cookie(self):
        return self.cookies

    def cookie_added(self, cookie):
        print(f"Cookie added: {cookie.name().data().decode()}")
        self.cookies[cookie.name().data().decode()] = cookie.value().data().decode()

    def verify(self, url):
        return True

    def parseReslt(self, url):
        self.result = url
        return True

    def clear_cookies(self):
        cookie_store = self.profile.cookieStore()
        cookie_store.deleteAllCookies()
        print("Cookies cleared")

    def run(self):
        self.show()
        self.app.exec_()
        return self.result

    def cleanup(self):
        #self.view.setPage(None)
        QTimer.singleShot(0, self.close)


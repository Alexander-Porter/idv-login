from PyQt5.QtCore import QUrl
from PyQt5.QtWidgets import QApplication
from PyQt5 import QtCore
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile,QWebEnginePage
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QPushButton, QWidget, QHBoxLayout
from PyQt5.QtCore import QUrl, QTimer
from PyQt5.QtCore import pyqtSlot
from envmgr import genv
from logutil import setup_logger
class WebBrowser(QWidget):
    class WebEngineView(QWebEngineView):
        def createWindow(self, QWebEnginePage_WebWindowType):
            page = QWebEngineView(self)
            page.urlChanged.connect(self.on_url_changed)
            return page

        def on_url_changed(self, url):
            self.setUrl(url)

    def __init__(self,name="WebLoginDefault",keepCookie=True):
        self.app = QApplication.instance()
        self.logger=setup_logger()
        super().__init__()
        self.view = self.WebEngineView()
        tmpName=genv.get("GLOB_LOGIN_UUID","")
        name=tmpName if tmpName!="" else name
        try:
            self.profile:QWebEngineProfile =  QWebEngineProfile(name)
            self.profile.setPersistentStoragePath(genv.get("GLOB_LOGIN_PROFILE_PATH",name))
            self.profile.setCachePath(genv.get("GLOB_LOGIN_CACHE_PATH",name))
            self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
            self.logger.info(f"Profile创建成功: {name}")
        except Exception as e:
            self.logger.error(f"Profile创建失败： {e}")
            raise

        #cookie相关
        if keepCookie:
            self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        else:
            self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        self.profile.cookieStore().cookieAdded.connect(self.cookie_added)
        
        #page相关
        self.view.setPage(QWebEnginePage(self.profile, self.view))
        self.page = self.view.page()
        self.cookies = {}
        self.result = ""
        self.page.loadFinished.connect(self.on_load_finished)
        self.page.urlChanged.connect(self.handle_url_change)

        # 创建清除Cookie按钮
        self.clear_cookie_button = QPushButton("强制退登")
        self.clear_cookie_button.clicked.connect(self.clear_cookies)

        # 设置布局
        self.toolBarLayout=QHBoxLayout()
        self.toolBarLayout.addWidget(self.clear_cookie_button)

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.view)
        self.layout.addLayout(self.toolBarLayout)
        self.setLayout(self.layout)

        #窗口置顶
        self.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint)
        #设置窗口大小
        self.resize(1000, 1000)

    def set_url(self, url):
        self.view.load(QUrl(url))

    @pyqtSlot(bool)
    def on_load_finished(self, success):
        pass


    def handle_url_change(self, url):
        self.logger.debug(f"URL changed: {url.toString()}")
        if self.verify(url.toString()):
            if self.parseReslt(url.toString()):
                self.cleanup()

    def export_cookie(self):
        return self.cookies

    def cookie_added(self, cookie):
        self.logger.debug(f"Cookie added: {cookie.name().data().decode()}")
        self.cookies[cookie.name().data().decode()] = cookie.value().data().decode()

    def verify(self, url):
        return True

    def parseReslt(self, url):
        self.result = url
        return True

    def clear_cookies(self):
        cookie_store = self.profile.cookieStore()
        cookie_store.deleteAllCookies()
        #重载页面
        self.view.reload()

    def run(self):
        self.show()
        self.app.exec_()
        return self.result

    def cleanup(self):
        #self.view.setPage(None)
        self.profile.cookieStore().cookieAdded.disconnect(self.cookie_added)
        self.close()

    
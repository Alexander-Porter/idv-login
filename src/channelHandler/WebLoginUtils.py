from PyQt6 import QtCore
from PyQt6.QtCore import QUrl, QTimer, pyqtSlot
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QPushButton, QWidget, QHBoxLayout
from envmgr import genv
from logutil import setup_logger
import os
import typing
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
            # 绑定到当前 QWidget，确保窗口销毁时 profile 能被一并释放（避免 Cookies 文件句柄长期占用）
            self.profile:QWebEngineProfile =  QWebEngineProfile(name, self)
            profile_base_path = genv.get("GLOB_LOGIN_PROFILE_PATH", name)
            cache_base_path = genv.get("GLOB_LOGIN_CACHE_PATH", name)
            self._persistent_storage_path = os.path.join(profile_base_path, tmpName)
            self._cache_path = os.path.join(cache_base_path, tmpName)
            self.profile.setPersistentStoragePath(self._persistent_storage_path)
            self.profile.setCachePath(self._cache_path)
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
        self.setWindowFlags(QtCore.Qt.WindowType.WindowStaysOnTopHint)
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
        self.app.exec()
        return self.result

    def cleanup(self):
        # 目标：尽快释放 QtWebEngine 对 profile/Cookies 文件的占用。
        try:
            self.profile.cookieStore().cookieAdded.disconnect(self.cookie_added)
        except Exception:
            pass

        try:
            self.page.loadFinished.disconnect(self.on_load_finished)
        except Exception:
            pass
        try:
            self.page.urlChanged.disconnect(self.handle_url_change)
        except Exception:
            pass

        try:
            self.view.setPage(None)
        except Exception:
            pass

        for attr in ("page", "view", "profile"):
            obj: typing.Any = getattr(self, attr, None)
            if obj is not None:
                try:
                    obj.deleteLater()
                except Exception:
                    pass
                setattr(self, attr, None)

        try:
            self.close()
        except Exception:
            pass
        try:
            self.deleteLater()
        except Exception:
            pass

        app_inst = QApplication.instance()
        if app_inst:
            # 延迟到下一轮事件循环再 quit，让 deleteLater 有机会被处理
            QTimer.singleShot(0, app_inst.quit)

    
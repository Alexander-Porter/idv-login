from playwright.async_api import async_playwright
from logutil import setup_logger
from envmgr import genv
import os
import asyncio

class WebBrowser:
    def __init__(self, name="WebLoginDefault", keep_cookie=True):
        self.logger = setup_logger()
        self.name = name
        self.keep_cookie = keep_cookie
        self.cookies = {}
        self.result = ""
        self.uuid = genv.get("GLOB_LOGIN_UUID","")
        
    async def initialize(self):
        if not os.path.exists(self.uuid):
            os.makedirs(self.uuid)
        user_data_dir = os.path.join(os.getcwd(), self.uuid)
        self.playwright = await async_playwright().start()
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            channel="msedge",
            args=["--start-maximized"],
        )

        if not self.keep_cookie:
            await self.context.clear_cookies()

        self.page = await self.context.new_page()
        self.page.on("load", lambda: asyncio.create_task(self.handle_url_change()))
        self.logger.info("Browser initialized.")


    async def set_url(self, url):
        await self.page.goto(url)

    def on_load_finished(self, success):
        if success:
            self.logger.info("Page loaded successfully")
        else:
            self.logger.error("Page failed to load")

    async def handle_url_change(self):
        url = self.page.url
        self.logger.debug(f"URL changed: {url}")
        if self.verify(url):
            if self.parse_result(url):
                self.cleanup()

    async def export_cookie(self):
        self.cookies = await self.context.cookies()
        self.logger.debug(f"Exported cookies: {self.cookies}")
        return self.cookies

    def verify(self, url):
        return True

    def parse_result(self, url):
        self.result = url
        return True

    async def clear_cookies(self):
        await self.context.clear_cookies()
        self.logger.info("Cookies cleared.")

    async def run(self):
        await self.page.wait_for_event("close", timeout=0)
        #self.page.on("framenavigated", self.handle_url_change)
        
        return self.result

    async def cleanup(self):
        self.logger.info("Cleaning up resources.")
        await self.page.close()
        await self.context.close()
        await self.playwright.stop()

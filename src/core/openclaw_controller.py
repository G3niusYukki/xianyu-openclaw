"""
浏览器自动化控制器
Browser Automation Controller

基于 Playwright 提供浏览器自动化能力，替代原始的 OpenClaw HTTP API 桩实现
"""

import asyncio
import random
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from src.core.config import get_config
from src.core.logger import get_logger
from src.core.error_handler import handle_controller_errors, handle_operation_errors, BrowserError


class BrowserState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class BrowserConfig:
    headless: bool = True
    timeout: int = 30000
    retry_times: int = 3
    delay_min: float = 1.0
    delay_max: float = 3.0
    viewport_width: int = 1280
    viewport_height: int = 800
    user_agent: str = ""


class ElementInfo:
    def __init__(self, locator, tag_name: str = ""):
        self.locator = locator
        self.tag_name = tag_name


class OpenClawController:
    """
    浏览器自动化控制器

    基于 Playwright 提供页面操作能力，包括导航、元素交互、文件上传等
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.browser_config = BrowserConfig()
        if config:
            self._apply_config(config)
        else:
            try:
                cfg = get_config()
                browser_cfg = cfg.browser
                openclaw_cfg = cfg.openclaw
                self._apply_config({
                    "headless": browser_cfg.get("headless", True),
                    "timeout": openclaw_cfg.get("timeout", 30) * 1000,
                    "retry_times": openclaw_cfg.get("retry_times", 3),
                    "delay_min": browser_cfg.get("delay", {}).get("min", 1.0),
                    "delay_max": browser_cfg.get("delay", {}).get("max", 3.0),
                    "viewport_width": browser_cfg.get("viewport", {}).get("width", 1280),
                    "viewport_height": browser_cfg.get("viewport", {}).get("height", 800),
                    "user_agent": browser_cfg.get("user_agent", ""),
                })
            except Exception:
                pass

        self.logger = get_logger()
        self.state = BrowserState.DISCONNECTED
        self._playwright = None
        self._browser = None
        self._context = None
        self._pages: Dict[str, Any] = {}
        self._page_counter = 0

    def _apply_config(self, config: Dict[str, Any]) -> None:
        self.browser_config.headless = config.get("headless", self.browser_config.headless)
        self.browser_config.timeout = config.get("timeout", self.browser_config.timeout)
        self.browser_config.retry_times = config.get("retry_times", self.browser_config.retry_times)
        self.browser_config.delay_min = config.get("delay_min", self.browser_config.delay_min)
        self.browser_config.delay_max = config.get("delay_max", self.browser_config.delay_max)
        self.browser_config.viewport_width = config.get("viewport_width", self.browser_config.viewport_width)
        self.browser_config.viewport_height = config.get("viewport_height", self.browser_config.viewport_height)
        self.browser_config.user_agent = config.get("user_agent", self.browser_config.user_agent)

    def random_delay(self) -> float:
        return random.uniform(self.browser_config.delay_min, self.browser_config.delay_max)

    async def connect(self) -> bool:
        """启动 Playwright 浏览器实例"""
        try:
            self.state = BrowserState.CONNECTING
            self.logger.info("Launching Playwright browser...")

            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()

            launch_args = {
                "headless": self.browser_config.headless,
            }

            self._browser = await self._playwright.chromium.launch(**launch_args)

            context_args = {
                "viewport": {
                    "width": self.browser_config.viewport_width,
                    "height": self.browser_config.viewport_height,
                },
            }
            if self.browser_config.user_agent:
                context_args["user_agent"] = self.browser_config.user_agent

            self._context = await self._browser.new_context(**context_args)
            self._context.set_default_timeout(self.browser_config.timeout)

            self.state = BrowserState.CONNECTED
            self.logger.success(f"Browser launched (headless={self.browser_config.headless})")
            return True

        except ImportError:
            self.state = BrowserState.ERROR
            self.logger.error(
                "Playwright is not installed. Run: pip install playwright && python -m playwright install chromium"
            )
            return False
        except Exception as e:
            self.state = BrowserState.ERROR
            self.logger.error(f"Browser launch failed: {e}")
            return False

    async def disconnect(self) -> None:
        for page_id in list(self._pages.keys()):
            await self.close_page(page_id)

        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

        self.state = BrowserState.DISCONNECTED
        self.logger.info("Browser closed")

    @handle_controller_errors(default_return=False)
    async def is_connected(self) -> bool:
        if self.state != BrowserState.CONNECTED:
            return False
        return self._browser is not None and self._browser.is_connected()

    async def ensure_connected(self) -> bool:
        if not await self.is_connected():
            return await self.connect()
        return True

    async def new_page(self) -> str:
        if not await self.ensure_connected():
            raise BrowserError("Browser is not connected")

        page = await self._context.new_page()
        self._page_counter += 1
        page_id = f"page_{self._page_counter}"
        self._pages[page_id] = page
        self.logger.debug(f"Created new page: {page_id}")
        return page_id

    def _get_page(self, page_id: str):
        page = self._pages.get(page_id)
        if page is None:
            raise BrowserError(f"Page not found: {page_id}")
        return page

    @handle_operation_errors(default_return=False)
    async def close_page(self, page_id: str) -> bool:
        page = self._pages.pop(page_id, None)
        if page:
            await page.close()
        return True

    async def navigate(self, page_id: str, url: str, wait_load: bool = True) -> bool:
        self.logger.info(f"Navigating to {url}")
        page = self._get_page(page_id)

        for attempt in range(self.browser_config.retry_times):
            try:
                wait_until = "domcontentloaded" if wait_load else "commit"
                await page.goto(url, wait_until=wait_until)
                if wait_load:
                    await asyncio.sleep(self.random_delay())
                self.logger.debug(f"Navigated to {url}")
                return True
            except Exception as e:
                self.logger.warning(f"Navigate failed (attempt {attempt + 1}): {e}")
                await asyncio.sleep(2 * (attempt + 1))

        return False

    async def find_element(self, page_id: str, selector: str) -> Optional[ElementInfo]:
        page = self._get_page(page_id)
        try:
            locator = page.locator(selector).first
            if await locator.count() > 0:
                tag = await locator.evaluate("el => el.tagName.toLowerCase()")
                return ElementInfo(locator=locator, tag_name=tag)
            return None
        except Exception as e:
            self.logger.debug(f"Find element error for '{selector}': {e}")
            return None

    async def find_elements(self, page_id: str, selector: str) -> List[ElementInfo]:
        page = self._get_page(page_id)
        try:
            locator = page.locator(selector)
            count = await locator.count()
            return [ElementInfo(locator=locator.nth(i)) for i in range(count)]
        except Exception as e:
            self.logger.debug(f"Find elements error for '{selector}': {e}")
            return []

    async def click(self, page_id: str, selector: str,
                    timeout: int = 10000, retry: bool = True) -> bool:
        self.logger.debug(f"Clicking: {selector}")
        page = self._get_page(page_id)

        attempts = self.browser_config.retry_times if retry else 1
        for attempt in range(attempts):
            try:
                await page.locator(selector).first.click(timeout=timeout)
                await asyncio.sleep(self.random_delay())
                return True
            except Exception as e:
                self.logger.debug(f"Click error (attempt {attempt + 1}): {e}")
                await asyncio.sleep(1)

        self.logger.warning(f"Failed to click: {selector}")
        return False

    @handle_operation_errors(default_return=False)
    async def double_click(self, page_id: str, selector: str) -> bool:
        page = self._get_page(page_id)
        await page.locator(selector).first.dblclick()
        return True

    async def type_text(self, page_id: str, selector: str, text: str,
                        clear: bool = True) -> bool:
        self.logger.debug(f"Typing into {selector}: {text[:50]}...")
        page = self._get_page(page_id)

        try:
            locator = page.locator(selector).first
            if clear:
                await locator.fill(text)
            else:
                await locator.type(text)
            await asyncio.sleep(self.random_delay())
            return True
        except Exception as e:
            self.logger.warning(f"Type text error for '{selector}': {e}")
            return False

    @handle_operation_errors(default_return=None)
    async def get_text(self, page_id: str, selector: str) -> Optional[str]:
        page = self._get_page(page_id)
        return await page.locator(selector).first.inner_text()

    @handle_operation_errors(default_return=None)
    async def get_value(self, page_id: str, selector: str) -> Optional[str]:
        page = self._get_page(page_id)
        return await page.locator(selector).first.input_value()

    @handle_operation_errors(default_return=False)
    async def select_option(self, page_id: str, selector: str, value: str) -> bool:
        page = self._get_page(page_id)
        await page.locator(selector).first.select_option(value)
        return True

    @handle_operation_errors(default_return=False)
    async def check(self, page_id: str, selector: str, checked: bool = True) -> bool:
        page = self._get_page(page_id)
        locator = page.locator(selector).first
        if checked:
            await locator.check()
        else:
            await locator.uncheck()
        return True

    async def upload_file(self, page_id: str, selector: str, file_path: str) -> bool:
        self.logger.info(f"Uploading file: {file_path}")
        if not file_path:
            return False

        page = self._get_page(page_id)
        try:
            await page.locator(selector).first.set_input_files(file_path)
            self.logger.success(f"Uploaded: {file_path}")
            await asyncio.sleep(self.random_delay() * 2)
            return True
        except Exception as e:
            self.logger.error(f"Upload error: {e}")
            return False

    async def upload_files(self, page_id: str, selector: str,
                           file_paths: List[str]) -> bool:
        if not file_paths:
            return True

        self.logger.info(f"Uploading {len(file_paths)} files")
        page = self._get_page(page_id)
        try:
            await page.locator(selector).first.set_input_files(file_paths)
            await asyncio.sleep(self.random_delay() * len(file_paths))
            return True
        except Exception as e:
            self.logger.error(f"Batch upload error: {e}")
            return False

    async def wait_for_selector(self, page_id: str, selector: str,
                                timeout: int = 10000, visible: bool = True) -> bool:
        self.logger.debug(f"Waiting for selector: {selector}")
        page = self._get_page(page_id)
        try:
            state = "visible" if visible else "attached"
            await page.locator(selector).first.wait_for(timeout=timeout, state=state)
            self.logger.debug(f"Found selector: {selector}")
            return True
        except Exception:
            self.logger.warning(f"Timeout waiting for selector: {selector}")
            return False

    async def wait_for_url(self, page_id: str, pattern: str,
                           timeout: int = 30000) -> bool:
        page = self._get_page(page_id)
        try:
            await page.wait_for_url(f"**{pattern}**", timeout=timeout)
            return True
        except Exception:
            return False

    async def scroll_to_element(self, page_id: str, selector: str) -> bool:
        page = self._get_page(page_id)
        try:
            await page.locator(selector).first.scroll_into_view_if_needed()
            return True
        except Exception:
            return False

    async def scroll_to_top(self, page_id: str) -> bool:
        return await self.execute_script(page_id, "window.scrollTo(0, 0); true;") is True

    async def scroll_to_bottom(self, page_id: str) -> bool:
        return await self.execute_script(page_id, "window.scrollTo(0, document.body.scrollHeight); true;") is True

    async def scroll_by(self, page_id: str, x: int, y: int) -> bool:
        script = f"window.scrollBy({x}, {y}); true;"
        return await self.execute_script(page_id, script) is True

    async def execute_script(self, page_id: str, script: str) -> Any:
        page = self._get_page(page_id)
        try:
            return await page.evaluate(script)
        except Exception as e:
            self.logger.debug(f"Script execution error: {e}")
            return None

    async def take_screenshot(self, page_id: str, path: str) -> bool:
        page = self._get_page(page_id)
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=path)
            return True
        except Exception as e:
            self.logger.error(f"Screenshot error: {e}")
            return False

    @handle_operation_errors(default_return=[])
    async def get_cookies(self, page_id: str) -> List[Dict[str, str]]:
        return await self._context.cookies()

    @handle_operation_errors(default_return=False)
    async def add_cookie(self, page_id: str, cookie: Dict[str, str]) -> bool:
        await self._context.add_cookies([cookie])
        return True

    @handle_operation_errors(default_return=False)
    async def delete_cookies(self, page_id: str, name: Optional[str] = None) -> bool:
        await self._context.clear_cookies()
        return True

    @handle_operation_errors(default_return=False)
    async def reload(self, page_id: str) -> bool:
        page = self._get_page(page_id)
        await page.reload()
        return True

    @handle_operation_errors(default_return=False)
    async def go_back(self, page_id: str) -> bool:
        page = self._get_page(page_id)
        await page.go_back()
        return True

    @handle_operation_errors(default_return=False)
    async def go_forward(self, page_id: str) -> bool:
        page = self._get_page(page_id)
        await page.go_forward()
        return True

    @handle_operation_errors(default_return=None)
    async def get_page_source(self, page_id: str) -> Optional[str]:
        page = self._get_page(page_id)
        return await page.content()

    @handle_operation_errors(default_return=False)
    async def handle_dialog(self, page_id: str, accept: bool = True,
                            text: str = "") -> bool:
        page = self._get_page(page_id)

        async def _dialog_handler(dialog):
            if accept:
                await dialog.accept(text if text else None)
            else:
                await dialog.dismiss()

        page.on("dialog", _dialog_handler)
        return True

    async def set_cookies_for_domain(self, cookies_str: str, domain: str = ".goofish.com") -> None:
        """从 cookie 字符串设置浏览器 cookie"""
        if not self._context:
            raise BrowserError("Browser context not initialized")

        cookies = []
        for item in cookies_str.split(";"):
            item = item.strip()
            if "=" in item:
                name, value = item.split("=", 1)
                cookies.append({
                    "name": name.strip(),
                    "value": value.strip(),
                    "domain": domain,
                    "path": "/",
                })

        if cookies:
            await self._context.add_cookies(cookies)
            self.logger.info(f"Set {len(cookies)} cookies for {domain}")


async def create_controller(config: Optional[Dict[str, Any]] = None) -> OpenClawController:
    """创建并连接控制器"""
    controller = OpenClawController(config)
    connected = await controller.connect()
    if not connected:
        raise BrowserError("Failed to launch browser. Is Playwright installed?")
    return controller

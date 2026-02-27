"""
Playwright Lite Browser Client

本地轻量浏览器客户端：
- 不依赖 OpenClaw Gateway
- 直接使用 Playwright 驱动 Chromium
- 兼容现有服务层常用方法签名
"""

from __future__ import annotations

import asyncio
import os
import random
import uuid
from pathlib import Path
from typing import Any

from src.core.error_handler import BrowserError
from src.core.logger import get_logger

try:
    from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
except Exception:  # pragma: no cover - optional dependency path
    Browser = Any  # type: ignore[assignment]
    BrowserContext = Any  # type: ignore[assignment]
    Page = Any  # type: ignore[assignment]
    Playwright = Any  # type: ignore[assignment]
    async_playwright = None  # type: ignore[assignment]


class PlaywrightBrowserClient:
    """Lite 模式浏览器客户端。"""

    def __init__(self, config: dict[str, Any] | None = None):
        from src.core.config import get_config

        app_config = get_config()
        browser_cfg = app_config.browser

        self.logger = get_logger()
        self.config = config or {}
        self.headless = bool(self.config.get("headless", browser_cfg.get("headless", True)))
        self.timeout = int(self.config.get("timeout", 30))

        delay_cfg = browser_cfg.get("delay", {})
        self.delay_min = float(self.config.get("delay_min", delay_cfg.get("min", 1.0)))
        self.delay_max = float(self.config.get("delay_max", delay_cfg.get("max", 3.0)))

        viewport_cfg = browser_cfg.get("viewport", {"width": 1280, "height": 800})
        self.viewport = {
            "width": int(viewport_cfg.get("width", 1280)),
            "height": int(viewport_cfg.get("height", 800)),
        }
        self.user_agent = str(browser_cfg.get("user_agent", "") or "").strip()
        self._cookies_seed = os.getenv("XIANYU_COOKIE_1", "")

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._pages: dict[str, Page] = {}

    def random_delay(self) -> float:
        return random.uniform(self.delay_min, self.delay_max)

    async def connect(self) -> bool:
        if async_playwright is None:
            self.logger.error("Playwright is not installed. Run: pip install playwright && playwright install chromium")
            return False

        if self._context is not None:
            return True

        try:
            self._playwright = await async_playwright().start()

            launch_kwargs: dict[str, Any] = {"headless": self.headless}
            executable_path = os.getenv("PLAYWRIGHT_EXECUTABLE_PATH", "").strip()
            if executable_path:
                launch_kwargs["executable_path"] = executable_path

            self._browser = await self._playwright.chromium.launch(**launch_kwargs)

            context_kwargs: dict[str, Any] = {"viewport": self.viewport}
            if self.user_agent:
                context_kwargs["user_agent"] = self.user_agent
            self._context = await self._browser.new_context(**context_kwargs)

            if self._cookies_seed:
                await self.set_cookies_for_domain(self._cookies_seed)

            self.logger.info("Connected to Playwright Lite browser")
            return True
        except Exception as exc:
            self.logger.error(f"Playwright connect failed: {exc}")
            await self.disconnect()
            return False

    async def disconnect(self) -> None:
        for page_id in list(self._pages.keys()):
            await self.close_page(page_id)

        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def is_connected(self) -> bool:
        return self._context is not None

    async def ensure_connected(self) -> bool:
        if await self.is_connected():
            return True
        return await self.connect()

    async def new_page(self) -> str:
        if not await self.ensure_connected() or self._context is None:
            raise BrowserError("Playwright browser is not connected")
        page = await self._context.new_page()
        page_id = f"pw_{uuid.uuid4().hex[:12]}"
        self._pages[page_id] = page
        return page_id

    async def close_page(self, page_id: str) -> bool:
        page = self._pages.pop(page_id, None)
        if page is None:
            return False
        try:
            await page.close()
            return True
        except Exception:
            return False

    def _get_page(self, page_id: str) -> Page:
        page = self._pages.get(page_id)
        if page is None:
            raise BrowserError(f"Page not found: {page_id}")
        return page

    async def navigate(self, page_id: str, url: str, wait_load: bool = True) -> bool:
        page = self._get_page(page_id)
        try:
            target = url or page.url
            await page.goto(target, wait_until="domcontentloaded", timeout=self.timeout * 1000)
            if wait_load:
                await asyncio.sleep(self.random_delay())
            return True
        except Exception as exc:
            self.logger.warning(f"Navigate failed: {exc}")
            return False

    async def click(self, page_id: str, selector: str, timeout: int = 10000, retry: bool = True) -> bool:
        page = self._get_page(page_id)
        attempts = 3 if retry else 1
        for _ in range(attempts):
            try:
                await page.click(selector, timeout=timeout)
                await asyncio.sleep(self.random_delay())
                return True
            except Exception:
                await asyncio.sleep(0.2)
        return False

    async def type_text(self, page_id: str, selector: str, text: str, clear: bool = True) -> bool:
        page = self._get_page(page_id)
        try:
            if clear:
                await page.fill(selector, text)
            else:
                await page.type(selector, text, delay=20)
            await asyncio.sleep(self.random_delay())
            return True
        except Exception as exc:
            self.logger.warning(f"Type text failed: {exc}")
            return False

    async def find_elements(self, page_id: str, selector: str) -> list[dict[str, Any]]:
        page = self._get_page(page_id)
        try:
            locator = page.locator(selector)
            count = await locator.count()
            return [{"selector": selector, "index": i} for i in range(count)]
        except Exception:
            return []

    async def find_element(self, page_id: str, selector: str) -> dict[str, Any] | None:
        items = await self.find_elements(page_id, selector)
        return items[0] if items else None

    async def get_text(self, page_id: str, selector: str) -> str | None:
        page = self._get_page(page_id)
        try:
            return await page.locator(selector).first.inner_text()
        except Exception:
            return None

    async def get_value(self, page_id: str, selector: str) -> str | None:
        page = self._get_page(page_id)
        try:
            return await page.locator(selector).first.input_value()
        except Exception:
            return None

    async def wait_for_selector(self, page_id: str, selector: str, timeout: int = 10000, visible: bool = True) -> bool:
        page = self._get_page(page_id)
        state = "visible" if visible else "attached"
        try:
            await page.wait_for_selector(selector, timeout=timeout, state=state)
            return True
        except Exception:
            return False

    async def wait_for_url(self, page_id: str, pattern: str, timeout: int = 30000) -> bool:
        page = self._get_page(page_id)
        try:
            await page.wait_for_url(f"**{pattern}**", timeout=timeout)
            return True
        except Exception:
            return False

    async def upload_file(self, page_id: str, selector: str, file_path: str) -> bool:
        return await self.upload_files(page_id, selector, [file_path])

    async def upload_files(self, page_id: str, selector: str, file_paths: list[str]) -> bool:
        page = self._get_page(page_id)
        normalized = [str(Path(p).resolve()) for p in file_paths if str(p).strip()]
        if not normalized:
            return False
        try:
            await page.set_input_files(selector, normalized)
            await asyncio.sleep(self.random_delay())
            return True
        except Exception as exc:
            self.logger.warning(f"Upload failed: {exc}")
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
        return await self.execute_script(page_id, f"window.scrollBy({x}, {y}); true;") is True

    async def execute_script(self, page_id: str, script: str) -> Any:
        page = self._get_page(page_id)
        try:
            return await page.evaluate(script)
        except Exception as exc:
            self.logger.debug(f"Script execute failed: {exc}")
            return None

    async def take_screenshot(self, page_id: str, path: str) -> bool:
        page = self._get_page(page_id)
        try:
            out = Path(path)
            out.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(out), full_page=False)
            return True
        except Exception:
            return False

    async def get_cookies(self, page_id: str = "") -> list[dict[str, Any]]:
        if self._context is None:
            return []
        try:
            return await self._context.cookies()
        except Exception:
            return []

    async def add_cookie(self, page_id: str, cookie: dict[str, Any]) -> bool:
        if self._context is None:
            return False
        try:
            await self._context.add_cookies([cookie])
            return True
        except Exception:
            return False

    async def delete_cookies(self, page_id: str = "", name: str | None = None) -> bool:
        if self._context is None:
            return False
        try:
            await self._context.clear_cookies()
            return True
        except Exception:
            return False

    async def set_cookies_for_domain(self, cookies_str: str, domain: str = ".goofish.com") -> None:
        if self._context is None:
            return

        cookies = []
        for item in cookies_str.split(";"):
            item = item.strip()
            if "=" not in item:
                continue
            name, value = item.split("=", 1)
            cookies.append(
                {
                    "name": name.strip(),
                    "value": value.strip(),
                    "domain": domain,
                    "path": "/",
                }
            )

        if cookies:
            await self._context.add_cookies(cookies)


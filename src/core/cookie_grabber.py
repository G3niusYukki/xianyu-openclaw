"""
自动获取闲鱼 Cookie 模块

两级策略：
  Level 1 — 从本地浏览器 Cookie 数据库直接读取（零操作）
  Level 2 — 打开 Chrome 窗口让用户扫码登录后提取
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from src.core.logger import get_logger

logger = get_logger()

_GOOFISH_DOMAINS = [".goofish.com", ".taobao.com", ".tmall.com"]
_GOOFISH_URL = "https://www.goofish.com/"
_LOGIN_TIMEOUT_MS = 300_000  # 5 minutes


class GrabStage(str, Enum):
    IDLE = "idle"
    READING_DB = "reading_db"
    VALIDATING = "validating"
    LOGIN_REQUIRED = "login_required"
    WAITING_LOGIN = "waiting_login"
    SAVING = "saving"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class GrabProgress:
    stage: GrabStage = GrabStage.IDLE
    message: str = ""
    hint: str = ""
    progress: int = 0
    cookie_preview: str = ""
    error: str = ""


@dataclass
class GrabResult:
    ok: bool = False
    cookie_str: str = ""
    source: str = ""
    message: str = ""
    error: str = ""


class CookieGrabber:
    """自动获取闲鱼 Cookie。"""

    def __init__(self) -> None:
        self._cancel = False
        self._progress = GrabProgress()
        self._listeners: list[Any] = []

    @property
    def progress(self) -> GrabProgress:
        return self._progress

    def cancel(self) -> None:
        self._cancel = True
        self._update(GrabStage.CANCELLED, "已取消")

    def add_listener(self, fn: Any) -> None:
        self._listeners.append(fn)

    def _update(self, stage: GrabStage, message: str, hint: str = "", progress: int = 0) -> None:
        self._progress = GrabProgress(stage=stage, message=message, hint=hint, progress=progress)
        for fn in self._listeners:
            try:
                fn(self._progress)
            except Exception:
                pass

    async def auto_grab(self) -> GrabResult:
        """组合 Level1 + Level2 的完整获取流程。"""
        self._cancel = False

        cookie = await self._grab_from_browser_db()
        if self._cancel:
            return GrabResult(ok=False, error="已取消")
        if cookie:
            valid = await self._validate(cookie)
            if valid:
                self._save(cookie, source="browser_db")
                self._update(GrabStage.SUCCESS, "Cookie 获取成功！", "Cookie 有效期约 7-30 天，过期后可再次自动获取", 100)
                return GrabResult(ok=True, cookie_str=cookie, source="browser_db", message="从浏览器数据库获取成功")

        cookie = await self._grab_via_login()
        if self._cancel:
            return GrabResult(ok=False, error="已取消")
        if cookie:
            valid = await self._validate(cookie)
            if valid:
                self._save(cookie, source="browser_login")
                self._update(GrabStage.SUCCESS, "Cookie 获取成功！", "Cookie 有效期约 7-30 天，过期后可再次自动获取", 100)
                return GrabResult(ok=True, cookie_str=cookie, source="browser_login", message="从浏览器登录获取成功")

        self._update(GrabStage.FAILED, "Cookie 获取失败", "请确认已安装 Chrome 浏览器，或尝试手动粘贴 Cookie")
        return GrabResult(ok=False, error="所有获取方式均失败")

    async def _grab_from_browser_db(self) -> str | None:
        """Level 1：从本地浏览器 Cookie 数据库读取。"""
        self._update(GrabStage.READING_DB, "正在读取浏览器 Cookie...", "如果弹出"钥匙串访问"弹窗，请点击"允许"", 10)

        browsers = [
            ("Chrome", self._read_chrome),
            ("Edge", self._read_edge),
            ("Firefox", self._read_firefox),
        ]

        for name, reader in browsers:
            if self._cancel:
                return None
            try:
                cookie_str = reader()
                if cookie_str and len(cookie_str) > 50:
                    logger.info(f"从 {name} 浏览器数据库读取到 Cookie ({len(cookie_str)} chars)")
                    return cookie_str
            except Exception as exc:
                logger.debug(f"{name} Cookie 读取失败: {exc}")
                continue

        logger.info("本地浏览器数据库中未找到有效的闲鱼 Cookie")
        return None

    def _read_chrome(self) -> str | None:
        try:
            import rookiepy
            cookies = rookiepy.chrome(domains=[".goofish.com"])
            return self._format_cookies(cookies)
        except Exception as exc:
            logger.debug(f"Chrome rookiepy 读取失败: {exc}")
            return None

    def _read_edge(self) -> str | None:
        try:
            import rookiepy
            cookies = rookiepy.edge(domains=[".goofish.com"])
            return self._format_cookies(cookies)
        except Exception as exc:
            logger.debug(f"Edge rookiepy 读取失败: {exc}")
            return None

    def _read_firefox(self) -> str | None:
        try:
            import rookiepy
            cookies = rookiepy.firefox(domains=[".goofish.com"])
            return self._format_cookies(cookies)
        except Exception as exc:
            logger.debug(f"Firefox rookiepy 读取失败: {exc}")
            return None

    @staticmethod
    def _format_cookies(cookies: list[dict[str, Any]]) -> str | None:
        if not cookies:
            return None
        pairs = []
        for c in cookies:
            name = c.get("name", "")
            value = c.get("value", "")
            if name and value:
                pairs.append(f"{name}={value}")
        return "; ".join(pairs) if pairs else None

    async def _grab_via_login(self) -> str | None:
        """Level 2：打开 Chrome 窗口让用户扫码登录。"""
        self._update(
            GrabStage.LOGIN_REQUIRED,
            "需要登录闲鱼",
            "即将打开 Chrome 浏览器窗口，请在浏览器中扫码登录",
            30,
        )
        await asyncio.sleep(2)

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self._update(GrabStage.FAILED, "Playwright 未安装", "请执行: pip install playwright && playwright install chromium")
            return None

        pw = None
        browser = None
        try:
            pw = await async_playwright().start()

            launch_kwargs: dict[str, Any] = {"headless": False}
            try:
                browser = await pw.chromium.launch(channel="chrome", **launch_kwargs)
            except Exception:
                try:
                    browser = await pw.chromium.launch(channel="msedge", **launch_kwargs)
                except Exception:
                    browser = await pw.chromium.launch(**launch_kwargs)

            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            self._update(GrabStage.WAITING_LOGIN, "已打开浏览器窗口", "请在浏览器中用手机扫码登录闲鱼", 40)

            await page.goto(_GOOFISH_URL, wait_until="domcontentloaded", timeout=30000)

            deadline = time.time() + (_LOGIN_TIMEOUT_MS / 1000)
            while time.time() < deadline:
                if self._cancel:
                    return None

                current_url = page.url
                if self._is_logged_in_url(current_url):
                    break

                try:
                    await page.wait_for_url(
                        re.compile(r"goofish\.com/(my|$)"),
                        timeout=5000,
                    )
                    if self._is_logged_in_url(page.url):
                        break
                except Exception:
                    pass

                remaining = int(deadline - time.time())
                if remaining > 0:
                    self._update(
                        GrabStage.WAITING_LOGIN,
                        f"等待登录中... (剩余 {remaining} 秒)",
                        "请在浏览器中用手机扫码登录闲鱼",
                        40 + int(50 * (1 - remaining / (_LOGIN_TIMEOUT_MS / 1000))),
                    )

            if not self._is_logged_in_url(page.url):
                self._update(GrabStage.FAILED, "登录超时", "请在 5 分钟内完成登录，或尝试手动粘贴 Cookie")
                return None

            await asyncio.sleep(2)

            all_cookies = await context.cookies()
            goofish_cookies = [
                c for c in all_cookies
                if any(d in (c.get("domain", "")) for d in _GOOFISH_DOMAINS)
            ]

            if not goofish_cookies:
                self._update(GrabStage.FAILED, "登录成功但未获取到 Cookie", "请尝试手动粘贴 Cookie")
                return None

            cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in goofish_cookies if c.get("name"))
            logger.info(f"从浏览器登录获取到 Cookie ({len(cookie_str)} chars, {len(goofish_cookies)} items)")
            return cookie_str

        except Exception as exc:
            logger.error(f"浏览器登录获取 Cookie 失败: {exc}")
            self._update(GrabStage.FAILED, f"浏览器打开失败: {exc}", "请确认已安装 Chrome 浏览器")
            return None
        finally:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass
            if pw:
                try:
                    await pw.stop()
                except Exception:
                    pass

    @staticmethod
    def _is_logged_in_url(url: str) -> bool:
        url_lower = url.lower()
        if "login" in url_lower or "signin" in url_lower:
            return False
        if "goofish.com/my" in url_lower:
            return True
        if re.match(r"https?://(www\.)?goofish\.com/?$", url_lower):
            return True
        return False

    async def _validate(self, cookie_str: str) -> bool:
        """使用 CookieHealthChecker 验证 Cookie 有效性。"""
        self._update(GrabStage.VALIDATING, "正在验证 Cookie 有效性...", "", 85)
        try:
            from src.core.cookie_health import CookieHealthChecker
            checker = CookieHealthChecker(cookie_str, timeout_seconds=10.0)
            result = checker.check_sync(force=True)
            if result.get("healthy"):
                logger.info("Cookie 验证通过")
                return True
            logger.warning(f"Cookie 验证失败: {result.get('message', 'unknown')}")
            return False
        except Exception as exc:
            logger.warning(f"Cookie 验证异常，跳过验证: {exc}")
            return True

    def _save(self, cookie_str: str, source: str = "auto") -> None:
        """保存 Cookie 到环境变量和 .env 文件。"""
        self._update(GrabStage.SAVING, "正在保存 Cookie...", "", 90)

        os.environ["XIANYU_COOKIE_1"] = cookie_str

        env_path = Path(".env")
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            if "XIANYU_COOKIE_1=" in content:
                content = re.sub(
                    r"XIANYU_COOKIE_1=.*",
                    f"XIANYU_COOKIE_1={cookie_str}",
                    content,
                )
            else:
                content += f"\nXIANYU_COOKIE_1={cookie_str}\n"
            env_path.write_text(content, encoding="utf-8")
        else:
            env_path.write_text(f"XIANYU_COOKIE_1={cookie_str}\n", encoding="utf-8")

        logger.info(f"Cookie 已保存 (source={source}, length={len(cookie_str)})")

"""
自动获取闲鱼 Cookie 模块

三级降级策略：
  Level 1   — rookiepy 直读本地浏览器 Cookie 数据库（零操作）
  Level 1.5 — Playwright persistent context 复用 Chrome Profile（静默）
  Level 2   — Playwright 全新窗口让用户扫码登录
"""

from __future__ import annotations

import asyncio
import os
import platform
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from collections.abc import Callable

from src.core.logger import get_logger

logger = get_logger()

_GOOFISH_DOMAINS = [".goofish.com", ".taobao.com", ".tmall.com"]
_MY_PAGE_URL = "https://www.goofish.com/personal"
_LOGIN_TIMEOUT_MS = 300_000  # 5 minutes
_AUTH_COOKIES = {"unb", "cookie2", "sgcookie"}
_WEAK_LOGIN_COOKIES = {"_m_h5_tk", "_tb_token_"}


class GrabStage(str, Enum):
    IDLE = "idle"
    READING_DB = "reading_db"
    READING_PROFILE = "reading_profile"
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
    """自动获取闲鱼 Cookie — 三级降级策略。"""

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

    # ------------------------------------------------------------------
    # Main flow
    # ------------------------------------------------------------------

    async def auto_grab(self) -> GrabResult:
        """组合 Level 1 → 1.5 → 2 的完整获取流程。"""
        self._cancel = False

        # Level 1: rookiepy 直读浏览器 Cookie DB
        cookie = await self._grab_from_browser_db()
        if self._cancel:
            return GrabResult(ok=False, error="已取消")
        if cookie:
            valid = await self._validate(cookie)
            if valid:
                self._save(cookie, source="browser_db")
                self._update(GrabStage.SUCCESS, "Cookie 获取成功！",
                             "从浏览器数据库直接读取，Cookie 有效期约 7-30 天", 100)
                return GrabResult(ok=True, cookie_str=cookie, source="browser_db",
                                  message="从浏览器数据库获取成功")

        # Level 1.5: Playwright persistent context 复用 Chrome Profile
        cookie = await self._grab_from_profile()
        if self._cancel:
            return GrabResult(ok=False, error="已取消")
        if cookie:
            valid = await self._validate(cookie)
            if valid:
                self._save(cookie, source="chrome_profile")
                self._update(GrabStage.SUCCESS, "Cookie 获取成功！",
                             "从 Chrome 已有登录态提取，Cookie 有效期约 7-30 天", 100)
                return GrabResult(ok=True, cookie_str=cookie, source="chrome_profile",
                                  message="从 Chrome 已有登录态获取成功")

        # Level 2: Playwright 全新窗口 QR 扫码登录
        cookie = await self._grab_via_login()
        if self._cancel:
            return GrabResult(ok=False, error="已取消")
        if cookie:
            valid = await self._validate(cookie)
            if valid:
                self._save(cookie, source="browser_login")
                self._update(GrabStage.SUCCESS, "Cookie 获取成功！",
                             "Cookie 有效期约 7-30 天，过期后可再次自动获取", 100)
                return GrabResult(ok=True, cookie_str=cookie, source="browser_login",
                                  message="从浏览器登录获取成功")

        self._update(GrabStage.FAILED, "Cookie 获取失败",
                     "所有自动方式均未成功，请手动粘贴 Cookie（F12 → Network → 复制 Cookie 请求头）")

        from src.core.notify import send_system_notification
        send_system_notification(
            "【闲鱼自动化】⚠️ Cookie 自动获取全部失败\n"
            "三级策略（浏览器数据库 → Chrome Profile → QR 扫码登录）均未成功。\n"
            "请尽快手动打开 Dashboard 更新 Cookie，否则消息自动回复将中断。",
            event="cookie_expire",
        )
        return GrabResult(ok=False, error="所有获取方式均失败")

    # ------------------------------------------------------------------
    # Level 1: rookiepy 直读浏览器 Cookie DB
    # ------------------------------------------------------------------

    async def _grab_from_browser_db(self) -> str | None:
        self._update(GrabStage.READING_DB, "正在读取浏览器 Cookie 数据库...",
                     '如果弹出"钥匙串访问"弹窗，请点击"允许"', 5)

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

        logger.info("Level 1: 本地浏览器数据库中未找到有效 Cookie")
        return None

    def _read_chrome(self) -> str | None:
        try:
            import rookiepy
            cookies = rookiepy.chrome(domains=[".goofish.com"])
            return self._format_cookies(cookies)
        except Exception as exc:
            logger.debug(f"Chrome rookiepy: {exc}")
            return None

    def _read_edge(self) -> str | None:
        try:
            import rookiepy
            cookies = rookiepy.edge(domains=[".goofish.com"])
            return self._format_cookies(cookies)
        except Exception as exc:
            logger.debug(f"Edge rookiepy: {exc}")
            return None

    def _read_firefox(self) -> str | None:
        try:
            import rookiepy
            cookies = rookiepy.firefox(domains=[".goofish.com"])
            return self._format_cookies(cookies)
        except Exception as exc:
            logger.debug(f"Firefox rookiepy: {exc}")
            return None

    # ------------------------------------------------------------------
    # Level 1.5: Playwright persistent context 复用 Chrome Profile
    # ------------------------------------------------------------------

    async def _grab_from_profile(self) -> str | None:
        """静默加载用户 Chrome Profile，提取已有登录态 Cookie。"""
        self._update(GrabStage.READING_PROFILE, "正在尝试读取 Chrome 已有登录态...",
                     "如果你之前在 Chrome 中登录过闲鱼，可直接提取", 20)

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.debug("Level 1.5: playwright 未安装，跳过")
            return None

        chrome_dir = self._find_chrome_user_data_dir()
        if not chrome_dir:
            logger.info("Level 1.5: 未找到 Chrome 用户数据目录")
            return None

        if self._is_chrome_running():
            logger.info("Level 1.5: Chrome 正在运行，无法使用其 Profile（会产生锁冲突）")
            self._update(GrabStage.READING_PROFILE, "Chrome 正在运行，跳过 Profile 读取...",
                         "关闭 Chrome 后重试可直接提取已有登录态", 25)
            await asyncio.sleep(1)
            return None

        pw = None
        context = None
        try:
            pw = await async_playwright().start()
            self._update(GrabStage.READING_PROFILE, "正在加载 Chrome 用户数据...",
                         "静默读取中，无需操作", 30)

            context = await pw.chromium.launch_persistent_context(
                str(chrome_dir),
                channel="chrome",
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1280, "height": 800},
            )

            page = context.pages[0] if context.pages else await context.new_page()

            try:
                await page.goto(_MY_PAGE_URL, wait_until="domcontentloaded", timeout=15000)
            except Exception as exc:
                logger.debug(f"Level 1.5: 导航到 /personal 失败: {exc}")

            await asyncio.sleep(2)

            all_cookies = await context.cookies()
            cookie_str = self._extract_goofish_cookies(all_cookies)
            if not cookie_str:
                logger.info("Level 1.5: Chrome Profile 中未找到闲鱼 Cookie")
                return None

            if not self._has_login_cookies(all_cookies):
                logger.info("Level 1.5: Chrome Profile 有 Cookie 但缺少登录态标记")
                return None

            logger.info(f"Level 1.5: 从 Chrome Profile 提取到 Cookie ({len(cookie_str)} chars)")
            return cookie_str

        except Exception as exc:
            logger.info(f"Level 1.5: Chrome Profile 读取失败: {exc}")
            return None
        finally:
            if context:
                try:
                    await context.close()
                except Exception:
                    pass
            if pw:
                try:
                    await pw.stop()
                except Exception:
                    pass
            self._cleanup_singleton_lock(chrome_dir)

    @staticmethod
    def _find_chrome_user_data_dir() -> Path | None:
        system = platform.system()
        candidates: list[Path] = []

        if system == "Darwin":
            candidates = [
                Path.home() / "Library" / "Application Support" / "Google" / "Chrome",
                Path.home() / "Library" / "Application Support" / "Microsoft Edge",
            ]
        elif system == "Windows":
            local = Path(os.environ.get("LOCALAPPDATA", ""))
            candidates = [
                local / "Google" / "Chrome" / "User Data",
                local / "Microsoft" / "Edge" / "User Data",
            ]
        else:  # Linux
            candidates = [
                Path.home() / ".config" / "google-chrome",
                Path.home() / ".config" / "microsoft-edge",
                Path.home() / ".config" / "chromium",
            ]

        for path in candidates:
            if path.exists() and (path / "Default").is_dir():
                logger.debug(f"找到 Chrome 用户数据目录: {path}")
                return path

        return None

    @staticmethod
    def _is_chrome_running() -> bool:
        system = platform.system()
        try:
            if system == "Darwin":
                r = subprocess.run(["pgrep", "-x", "Google Chrome"], capture_output=True)
                if r.returncode == 0:
                    return True
                r = subprocess.run(["pgrep", "-x", "Microsoft Edge"], capture_output=True)
                return r.returncode == 0
            elif system == "Windows":
                r = subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
                    capture_output=True, text=True,
                )
                return "chrome.exe" in (r.stdout or "").lower()
            else:
                r = subprocess.run(["pgrep", "-f", "chrome|chromium"], capture_output=True)
                return r.returncode == 0
        except Exception:
            return True  # 检测失败时假设在运行，避免锁冲突

    @staticmethod
    def _cleanup_singleton_lock(chrome_dir: Path) -> None:
        lock = chrome_dir / "SingletonLock"
        try:
            if lock.exists():
                lock.unlink()
                logger.debug(f"已清理 SingletonLock: {lock}")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Level 2: Playwright 全新窗口 QR 扫码登录
    # ------------------------------------------------------------------

    async def _grab_via_login(self) -> str | None:
        """打开浏览器窗口，导航到"我的闲鱼"触发登录。"""
        self._update(
            GrabStage.LOGIN_REQUIRED,
            "需要扫码登录闲鱼",
            "即将打开浏览器窗口，请用闲鱼 App 扫描二维码登录",
            40,
        )
        await asyncio.sleep(2)

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self._update(GrabStage.FAILED, "Playwright 未安装",
                         "请执行: pip install playwright && playwright install chromium")
            return None

        pw = None
        browser = None
        try:
            pw = await async_playwright().start()

            launch_kwargs: dict[str, Any] = {
                "headless": False,
                "args": ["--disable-blink-features=AutomationControlled"],
            }
            for channel in ("chrome", "msedge", None):
                try:
                    kw = {**launch_kwargs}
                    if channel:
                        kw["channel"] = channel
                    browser = await pw.chromium.launch(**kw)
                    break
                except Exception:
                    continue

            if not browser:
                self._update(GrabStage.FAILED, "无法启动浏览器",
                             "请确认已安装 Chrome 或 Edge 浏览器")
                return None

            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            self._update(GrabStage.WAITING_LOGIN, "正在打开闲鱼...",
                         "请等待浏览器加载完成", 45)

            await page.goto(_MY_PAGE_URL, wait_until="domcontentloaded", timeout=30000)

            await asyncio.sleep(2)
            initial_cookies = await context.cookies()
            initial_names = {c.get("name", "") for c in initial_cookies}
            logger.debug(f"Level 2: 初始 Cookie 数量={len(initial_cookies)}, 名称={initial_names & (_AUTH_COOKIES | _WEAK_LOGIN_COOKIES)}")

            self._update(GrabStage.WAITING_LOGIN, "请在浏览器中登录闲鱼",
                         "点击页面上的「登录」按钮，用闲鱼 App 扫码完成登录", 50)

            deadline = time.time() + (_LOGIN_TIMEOUT_MS / 1000)
            logged_in = False

            while time.time() < deadline:
                if self._cancel:
                    return None

                await asyncio.sleep(3)

                all_cookies = await context.cookies()
                current_names = {c.get("name", "") for c in all_cookies}
                new_auth = (current_names & _AUTH_COOKIES) - initial_names
                if new_auth:
                    logger.info(f"Level 2: 检测到新增认证 Cookie: {new_auth}")
                    logged_in = True
                    break

                remaining = max(0, int(deadline - time.time()))
                pct = 50 + int(40 * (1 - remaining / (_LOGIN_TIMEOUT_MS / 1000)))
                self._update(
                    GrabStage.WAITING_LOGIN,
                    f"等待登录中... (剩余 {remaining} 秒)",
                    "点击页面上的「登录」按钮，用闲鱼 App 扫码完成登录",
                    pct,
                )

            if not logged_in:
                self._update(GrabStage.FAILED, "登录超时",
                             "5 分钟内未完成登录，请重试或手动粘贴 Cookie")
                return None

            self._update(GrabStage.WAITING_LOGIN, "登录成功，正在提取 Cookie...", "", 88)
            await asyncio.sleep(3)

            all_cookies = await context.cookies()
            cookie_str = self._extract_goofish_cookies(all_cookies)

            if not cookie_str:
                self._update(GrabStage.FAILED, "登录成功但未获取到 Cookie",
                             "请尝试手动粘贴 Cookie")
                return None

            if not self._has_login_cookies(all_cookies):
                logger.warning("Level 2: Cookie 缺少登录态标记，但仍尝试使用")

            logger.info(f"Level 2: 从浏览器登录获取到 Cookie ({len(cookie_str)} chars)")
            return cookie_str

        except Exception as exc:
            logger.error(f"Level 2: 浏览器登录失败: {exc}")
            self._update(GrabStage.FAILED, f"浏览器打开失败: {type(exc).__name__}",
                         "请确认已安装 Chrome 浏览器")
            return None

    # ------------------------------------------------------------------
    # Cookie extraction & login detection helpers
    # ------------------------------------------------------------------

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

    @staticmethod
    def _extract_goofish_cookies(all_cookies: list[dict[str, Any]]) -> str | None:
        goofish = [
            c for c in all_cookies
            if any(d in (c.get("domain", "")) for d in _GOOFISH_DOMAINS)
        ]
        if not goofish:
            return None
        cookie_str = "; ".join(
            f"{c['name']}={c['value']}" for c in goofish if c.get("name")
        )
        return cookie_str if len(cookie_str) > 50 else None

    @staticmethod
    def _has_login_cookies(cookies: list[dict[str, Any]]) -> bool:
        """检查是否包含登录后才会出现的 Cookie（unb=用户ID, cookie2, sgcookie）。"""
        names = {c.get("name", "") for c in cookies}
        return bool(names & _AUTH_COOKIES)

    @staticmethod
    def _is_logged_in(url: str) -> bool:
        url_lower = url.lower()
        if "login" in url_lower or "signin" in url_lower:
            return False
        if "goofish.com/personal" in url_lower:
            return True
        return False

    @staticmethod
    def _is_login_page(url: str) -> bool:
        url_lower = url.lower()
        return ("login" in url_lower or "signin" in url_lower
                or "passport" in url_lower or "qrcode" in url_lower)

    # ------------------------------------------------------------------
    # Validation & persistence
    # ------------------------------------------------------------------

    async def _validate(self, cookie_str: str) -> bool:
        self._update(GrabStage.VALIDATING, "正在验证 Cookie 有效性...", "", 92)
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
        self._update(GrabStage.SAVING, "正在保存 Cookie...", "", 95)

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


# ======================================================================
# 后台静默 Cookie 自动刷新器
# ======================================================================

@dataclass
class AutoRefreshStatus:
    """自动刷新器的运行状态快照。"""
    enabled: bool = False
    interval_minutes: int = 30
    last_check_at: float = 0.0
    last_check_ok: bool | None = None
    last_check_message: str = ""
    last_refresh_at: float = 0.0
    last_refresh_ok: bool | None = None
    last_refresh_source: str = ""
    total_checks: int = 0
    total_refreshes: int = 0
    next_check_in_seconds: int = 0


class CookieAutoRefresher:
    """后台静默 Cookie 刷新器 — 仅使用 Level 1 (rookiepy)。

    在守护线程中定期检查 Cookie 健康状态，失效时自动尝试从浏览器
    Cookie 数据库静默读取新的 Cookie，无需用户交互。
    """

    def __init__(
        self,
        interval_minutes: int = 30,
        on_refreshed: Callable[[str], Any] | None = None,
    ) -> None:
        self._interval = max(5, interval_minutes) * 60  # 最小 5 分钟
        self._interval_minutes = max(5, interval_minutes)
        self._on_refreshed = on_refreshed
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        self._last_check_at: float = 0.0
        self._last_check_ok: bool | None = None
        self._last_check_msg: str = ""
        self._last_refresh_at: float = 0.0
        self._last_refresh_ok: bool | None = None
        self._last_refresh_source: str = ""
        self._total_checks: int = 0
        self._total_refreshes: int = 0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def status(self) -> AutoRefreshStatus:
        elapsed = time.time() - self._last_check_at if self._last_check_at else 0
        remaining = max(0, int(self._interval - elapsed)) if self._last_check_at else 0
        return AutoRefreshStatus(
            enabled=self.running,
            interval_minutes=self._interval_minutes,
            last_check_at=self._last_check_at,
            last_check_ok=self._last_check_ok,
            last_check_message=self._last_check_msg,
            last_refresh_at=self._last_refresh_at,
            last_refresh_ok=self._last_refresh_ok,
            last_refresh_source=self._last_refresh_source,
            total_checks=self._total_checks,
            total_refreshes=self._total_refreshes,
            next_check_in_seconds=remaining,
        )

    def start(self) -> None:
        if self.running:
            logger.debug("CookieAutoRefresher 已在运行")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="cookie-auto-refresh")
        self._thread.start()
        logger.info(f"Cookie 静默自动刷新已启动 (间隔 {self._interval_minutes} 分钟)")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("Cookie 静默自动刷新已停止")

    def _loop(self) -> None:
        # 启动后等待 60 秒再做第一次检查，避免和服务启动竞争
        self._stop_event.wait(60)

        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as exc:
                logger.error(f"Cookie 自动刷新异常: {exc}")
            self._stop_event.wait(self._interval)

    def _tick(self) -> None:
        self._total_checks += 1
        self._last_check_at = time.time()

        cookie_text = os.environ.get("XIANYU_COOKIE_1", "")

        # 1) 检查当前 Cookie 是否健康
        healthy, msg = self._check_health(cookie_text)
        self._last_check_ok = healthy
        self._last_check_msg = msg

        if healthy:
            logger.debug(f"Cookie 自动检查: 健康 ({msg})")
            return

        logger.info(f"Cookie 自动检查: 不健康 ({msg})，尝试静默刷新...")

        # 2) 尝试 Level 1 静默获取
        loop = asyncio.new_event_loop()
        try:
            grabber = CookieGrabber()
            new_cookie = loop.run_until_complete(grabber._grab_from_browser_db())
        finally:
            loop.close()

        if not new_cookie:
            logger.info("Cookie 静默刷新: Level 1 未获取到 Cookie")
            self._last_refresh_ok = False
            self._last_refresh_source = ""
            self._send_notification(
                "⚠️ Cookie 已失效且自动刷新失败",
                f"【闲鱼自动化】Cookie 过期告警\n状态: {msg}\n静默刷新: 未获取到新 Cookie\n请手动打开 Dashboard 更新 Cookie",
                event="cookie_expire",
            )
            return

        # 3) 验证新 Cookie
        valid = self._validate_sync(new_cookie)
        if not valid:
            logger.info("Cookie 静默刷新: 新 Cookie 验证失败")
            self._last_refresh_ok = False
            self._send_notification(
                "⚠️ Cookie 自动刷新失败",
                f"【闲鱼自动化】Cookie 过期告警\n状态: {msg}\n静默刷新: 获取到新 Cookie 但验证失败\n请手动打开 Dashboard 更新 Cookie",
                event="cookie_expire",
            )
            return

        # 4) 保存并通知
        self._total_refreshes += 1
        self._last_refresh_at = time.time()
        self._last_refresh_ok = True
        self._last_refresh_source = "browser_db"
        self._last_check_ok = True
        self._last_check_msg = "静默刷新成功"

        os.environ["XIANYU_COOKIE_1"] = new_cookie
        self._save_to_env(new_cookie)

        logger.info(f"Cookie 静默刷新成功 (length={len(new_cookie)})")

        self._send_notification(
            "Cookie 自动刷新成功",
            "【闲鱼自动化】✅ Cookie 已自动刷新\n来源: 浏览器数据库\n状态: 验证通过\n系统已恢复正常运行",
            event="cookie_refresh",
        )

        if self._on_refreshed:
            try:
                self._on_refreshed(new_cookie)
            except Exception as exc:
                logger.error(f"Cookie 刷新回调失败: {exc}")

    @staticmethod
    def _send_notification(title: str, body: str, *, event: str = "") -> None:
        from src.core.notify import send_system_notification
        send_system_notification(body, event=event)

    @staticmethod
    def _check_health(cookie_text: str) -> tuple[bool, str]:
        if not cookie_text:
            return False, "Cookie 未配置"
        try:
            from src.core.cookie_health import CookieHealthChecker
            checker = CookieHealthChecker(cookie_text, timeout_seconds=10.0)
            result = checker.check_sync(force=True)
            return bool(result.get("healthy")), result.get("message", "")
        except Exception as exc:
            return False, f"检查异常: {exc}"

    @staticmethod
    def _validate_sync(cookie_str: str) -> bool:
        try:
            from src.core.cookie_health import CookieHealthChecker
            checker = CookieHealthChecker(cookie_str, timeout_seconds=10.0)
            result = checker.check_sync(force=True)
            return bool(result.get("healthy"))
        except Exception:
            return True  # 验证异常时放行

    @staticmethod
    def _save_to_env(cookie_str: str) -> None:
        env_path = Path(".env")
        try:
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
        except Exception as exc:
            logger.error(f"Cookie 写入 .env 失败: {exc}")

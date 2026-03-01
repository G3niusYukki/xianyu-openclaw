"""
Cookie 健康监控模块
Cookie Health Monitor

定期探测闲鱼 Cookie 有效性，失效时通过飞书告警。
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from src.core.logger import get_logger

logger = get_logger()

# 闲鱼个人主页，需要登录态才能正常访问（未登录会 302 到登录页）
_PROBE_URL = "https://www.goofish.com/my"
_LOGIN_URL_FRAGMENT = "login"


class CookieHealthChecker:
    """Cookie 有效性探测 + 飞书告警。

    通过请求闲鱼个人页判断 Cookie 是否有效：
    - HTTP 200 且未跳转到登录页 → 有效
    - HTTP 302 / 跳转到登录页 / 请求失败 → 无效

    集成飞书告警：Cookie 失效时即时通知，恢复后发送恢复消息。
    """

    def __init__(
        self,
        cookie_text: str | None = None,
        *,
        check_interval_seconds: float = 300.0,
        alert_cooldown_seconds: float = 1800.0,
        timeout_seconds: float = 10.0,
        notifier: Any | None = None,
    ):
        self._cookie_text = cookie_text or os.getenv("XIANYU_COOKIE_1", "")
        self._check_interval = max(60.0, float(check_interval_seconds))
        self._alert_cooldown = max(60.0, float(alert_cooldown_seconds))
        self._timeout = max(3.0, float(timeout_seconds))
        self._notifier = notifier

        # 状态追踪
        self._last_check_ts: float = 0.0
        self._last_healthy: bool | None = None
        self._last_alert_ts: float = 0.0
        self._cached_result: dict[str, Any] | None = None

    @property
    def cookie_text(self) -> str:
        return self._cookie_text

    @cookie_text.setter
    def cookie_text(self, value: str) -> None:
        self._cookie_text = value or ""
        # 清除缓存使下次检查立即执行
        self._last_check_ts = 0.0
        self._cached_result = None

    def _needs_check(self) -> bool:
        """是否到了需要再次检查的时间。"""
        if not self._cookie_text:
            return True
        return (time.time() - self._last_check_ts) >= self._check_interval

    def check_sync(self, force: bool = False) -> dict[str, Any]:
        """同步检查 Cookie 健康状态。

        Args:
            force: 强制检查，忽略 TTL 缓存。

        Returns:
            包含 healthy, message, checked_at 等字段的字典。
        """
        if not force and not self._needs_check() and self._cached_result is not None:
            return self._cached_result

        result = self._do_check_sync()
        self._last_check_ts = time.time()
        self._cached_result = result
        return result

    async def check_async(self, force: bool = False) -> dict[str, Any]:
        """异步检查 Cookie 健康状态。

        Args:
            force: 强制检查，忽略 TTL 缓存。

        Returns:
            包含 healthy, message, checked_at 等字段的字典。
        """
        if not force and not self._needs_check() and self._cached_result is not None:
            return self._cached_result

        result = await self._do_check_async()
        self._last_check_ts = time.time()
        self._cached_result = result

        # 状态变化时触发告警 / 恢复通知
        await self._handle_state_change(result)

        return result

    def _do_check_sync(self) -> dict[str, Any]:
        """同步 HTTP 探测。"""
        if not self._cookie_text:
            return self._build_result(False, "Cookie 未配置")

        try:
            with httpx.Client(
                timeout=self._timeout,
                follow_redirects=False,
                headers={"Cookie": self._cookie_text, "User-Agent": "Mozilla/5.0"},
            ) as client:
                resp = client.get(_PROBE_URL)
                return self._evaluate_response(resp)
        except httpx.TimeoutException:
            return self._build_result(False, "探测超时")
        except Exception as exc:
            return self._build_result(False, f"探测异常: {type(exc).__name__}")

    async def _do_check_async(self) -> dict[str, Any]:
        """异步 HTTP 探测。"""
        if not self._cookie_text:
            return self._build_result(False, "Cookie 未配置")

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=False,
                headers={"Cookie": self._cookie_text, "User-Agent": "Mozilla/5.0"},
            ) as client:
                resp = await client.get(_PROBE_URL)
                return self._evaluate_response(resp)
        except httpx.TimeoutException:
            return self._build_result(False, "探测超时")
        except Exception as exc:
            return self._build_result(False, f"探测异常: {type(exc).__name__}")

    def _evaluate_response(self, resp: httpx.Response) -> dict[str, Any]:
        """根据 HTTP 响应判断 Cookie 是否有效。"""
        # 302 重定向到登录页 → Cookie 过期
        if resp.status_code in {301, 302, 303, 307, 308}:
            location = resp.headers.get("location", "")
            if _LOGIN_URL_FRAGMENT in location.lower():
                return self._build_result(False, "Cookie 已过期（被重定向到登录页）")
            return self._build_result(False, f"非预期跳转: {location[:80]}")

        # 200 但需检查是否是登录页内容
        if resp.status_code == 200:
            return self._build_result(True, "Cookie 有效")

        # 403 / 其他错误
        return self._build_result(False, f"HTTP {resp.status_code}")

    def _build_result(self, healthy: bool, message: str) -> dict[str, Any]:
        return {
            "healthy": healthy,
            "message": message,
            "checked_at": time.time(),
            "previous_healthy": self._last_healthy,
        }

    async def _handle_state_change(self, result: dict[str, Any]) -> None:
        """状态变化时触发飞书告警或恢复通知。"""
        healthy = result["healthy"]
        prev = self._last_healthy
        self._last_healthy = healthy

        if self._notifier is None:
            return

        now = time.time()

        # 从健康变为不健康 → 告警
        if prev is not False and not healthy:
            if (now - self._last_alert_ts) >= self._alert_cooldown:
                msg = (
                    "【闲鱼自动化】⚠️ Cookie 失效告警\n"
                    f"状态: {result['message']}\n"
                    "请尽快在 Dashboard 或 .env 中更新 Cookie\n"
                    "更新后系统将自动恢复运行"
                )
                try:
                    await self._notifier.send_text(msg)
                    self._last_alert_ts = now
                    logger.warning(f"Cookie 健康告警已发送: {result['message']}")
                except Exception as exc:
                    logger.error(f"发送 Cookie 告警失败: {exc}")

        # 从不健康恢复为健康 → 恢复通知
        elif prev is False and healthy:
            msg = (
                "【闲鱼自动化】✅ Cookie 已恢复\n"
                "Cookie 有效性检测通过，系统恢复正常运行"
            )
            try:
                await self._notifier.send_text(msg)
                logger.info("Cookie 恢复通知已发送")
            except Exception as exc:
                logger.error(f"发送 Cookie 恢复通知失败: {exc}")

"""Cookie 健康监控测试。"""

import time
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from src.core.cookie_health import CookieHealthChecker


class TestCookieHealthChecker:
    """CookieHealthChecker 单元测试。"""

    def test_empty_cookie_reports_unhealthy(self, monkeypatch) -> None:
        monkeypatch.delenv("XIANYU_COOKIE_1", raising=False)
        checker = CookieHealthChecker(cookie_text="")
        result = checker.check_sync(force=True)
        assert result["healthy"] is False
        assert "未配置" in result["message"]

    def test_check_sync_healthy_on_200(self, monkeypatch) -> None:
        resp = Mock(spec=httpx.Response)
        resp.status_code = 200
        resp.headers = {}

        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.get = Mock(return_value=resp)

        monkeypatch.setattr(httpx, "Client", lambda **kwargs: mock_client)

        checker = CookieHealthChecker(cookie_text="test_cookie=abc123")
        result = checker.check_sync(force=True)
        assert result["healthy"] is True
        assert "有效" in result["message"]

    def test_check_sync_unhealthy_on_302_to_login(self, monkeypatch) -> None:
        resp = Mock(spec=httpx.Response)
        resp.status_code = 302
        resp.headers = {"location": "https://login.goofish.com/xxx"}

        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.get = Mock(return_value=resp)

        monkeypatch.setattr(httpx, "Client", lambda **kwargs: mock_client)

        checker = CookieHealthChecker(cookie_text="test_cookie=abc123")
        result = checker.check_sync(force=True)
        assert result["healthy"] is False
        assert "过期" in result["message"]

    def test_check_sync_unhealthy_on_timeout(self, monkeypatch) -> None:
        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.get = Mock(side_effect=httpx.TimeoutException("timeout"))

        monkeypatch.setattr(httpx, "Client", lambda **kwargs: mock_client)

        checker = CookieHealthChecker(cookie_text="test_cookie=abc123")
        result = checker.check_sync(force=True)
        assert result["healthy"] is False
        assert "超时" in result["message"]

    def test_ttl_cache_returns_cached_result(self, monkeypatch) -> None:
        resp = Mock(spec=httpx.Response)
        resp.status_code = 200
        resp.headers = {}

        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client.get = Mock(return_value=resp)

        monkeypatch.setattr(httpx, "Client", lambda **kwargs: mock_client)

        checker = CookieHealthChecker(
            cookie_text="test_cookie=abc123",
            check_interval_seconds=60.0,
        )
        result1 = checker.check_sync(force=True)
        result2 = checker.check_sync(force=False)  # should use cache

        assert result1["healthy"] is True
        assert result2["healthy"] is True
        assert mock_client.get.call_count == 1  # only called once

    @pytest.mark.asyncio
    async def test_check_async_triggers_alert_on_state_change(self, monkeypatch) -> None:
        resp = Mock(spec=httpx.Response)
        resp.status_code = 302
        resp.headers = {"location": "https://login.goofish.com/xxx"}

        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.get = AsyncMock(return_value=resp)

        monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: mock_async_client)

        notifier = AsyncMock()
        notifier.send_text = AsyncMock(return_value=True)

        checker = CookieHealthChecker(
            cookie_text="test_cookie=abc123",
            notifier=notifier,
            alert_cooldown_seconds=60.0,
        )

        result = await checker.check_async(force=True)
        assert result["healthy"] is False
        notifier.send_text.assert_awaited_once()
        call_text = notifier.send_text.call_args[0][0]
        assert "失效" in call_text

    @pytest.mark.asyncio
    async def test_check_async_sends_recovery_notification(self, monkeypatch) -> None:
        notifier = AsyncMock()
        notifier.send_text = AsyncMock(return_value=True)

        checker = CookieHealthChecker(
            cookie_text="test_cookie=abc123",
            notifier=notifier,
            alert_cooldown_seconds=60.0,
        )

        # Simulate previous unhealthy state
        checker._last_healthy = False

        # Now make it healthy
        resp = Mock(spec=httpx.Response)
        resp.status_code = 200
        resp.headers = {}

        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.get = AsyncMock(return_value=resp)

        monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: mock_async_client)

        result = await checker.check_async(force=True)
        assert result["healthy"] is True
        notifier.send_text.assert_awaited_once()
        call_text = notifier.send_text.call_args[0][0]
        assert "恢复" in call_text

    def test_cookie_setter_clears_cache(self) -> None:
        checker = CookieHealthChecker(cookie_text="old_cookie")
        checker._last_check_ts = time.time()
        checker._cached_result = {"healthy": True, "message": "cached"}

        checker.cookie_text = "new_cookie"

        assert checker._last_check_ts == 0.0
        assert checker._cached_result is None

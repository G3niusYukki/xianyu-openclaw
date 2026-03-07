from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.core.cookie_health import CookieHealthChecker


class TestCookieHealthChecker:
    def test_cookie_text_setter(self):
        checker = CookieHealthChecker("original_cookie")
        assert checker.cookie_text == "original_cookie"
        checker.cookie_text = "new_cookie"
        assert checker.cookie_text == "new_cookie"
        assert checker._last_check_ts == 0.0
        assert checker._cached_result is None

    def test_cookie_text_setter_empty(self):
        checker = CookieHealthChecker("original")
        checker.cookie_text = ""
        assert checker.cookie_text == ""

    def test_needs_check_no_cookie(self):
        checker = CookieHealthChecker("")
        assert checker._needs_check() is True

    def test_needs_check_time_elapsed(self):
        checker = CookieHealthChecker("cookie", check_interval_seconds=60)
        checker._last_check_ts = time.time() - 120
        assert checker._needs_check() is True

    def test_needs_check_not_yet(self):
        checker = CookieHealthChecker("cookie", check_interval_seconds=600)
        checker._last_check_ts = time.time()
        assert checker._needs_check() is False

    def test_check_sync_cached(self):
        checker = CookieHealthChecker("cookie", check_interval_seconds=600)
        checker._last_check_ts = time.time()
        checker._cached_result = {"healthy": True, "message": "cached"}
        result = checker.check_sync()
        assert result["message"] == "cached"

    def test_check_sync_no_cookie(self):
        checker = CookieHealthChecker("")
        result = checker.check_sync(force=True)
        assert result["healthy"] is False
        assert "未配置" in result["message"]

    def test_check_sync_success(self):
        checker = CookieHealthChecker("valid_cookie")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        with patch("httpx.Client", return_value=mock_client):
            result = checker.check_sync(force=True)
            assert result["healthy"] is True

    def test_check_sync_redirect_to_login(self):
        checker = CookieHealthChecker("expired_cookie")
        mock_resp = MagicMock()
        mock_resp.status_code = 302
        mock_resp.headers = {"location": "https://login.example.com/login?redirect=xxx"}
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        with patch("httpx.Client", return_value=mock_client):
            result = checker.check_sync(force=True)
            assert result["healthy"] is False
            assert "过期" in result["message"]

    def test_check_sync_redirect_non_login(self):
        checker = CookieHealthChecker("cookie")
        mock_resp = MagicMock()
        mock_resp.status_code = 301
        mock_resp.headers = {"location": "https://other.example.com/somewhere"}
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        with patch("httpx.Client", return_value=mock_client):
            result = checker.check_sync(force=True)
            assert result["healthy"] is False
            assert "跳转" in result["message"]

    def test_check_sync_403(self):
        checker = CookieHealthChecker("cookie")
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        with patch("httpx.Client", return_value=mock_client):
            result = checker.check_sync(force=True)
            assert result["healthy"] is False
            assert "403" in result["message"]

    def test_check_sync_timeout(self):
        checker = CookieHealthChecker("cookie")
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.TimeoutException("timeout")
        with patch("httpx.Client", return_value=mock_client):
            result = checker.check_sync(force=True)
            assert result["healthy"] is False
            assert "超时" in result["message"]

    def test_check_sync_exception(self):
        checker = CookieHealthChecker("cookie")
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = RuntimeError("unexpected")
        with patch("httpx.Client", return_value=mock_client):
            result = checker.check_sync(force=True)
            assert result["healthy"] is False
            assert "RuntimeError" in result["message"]

    async def test_check_async_cached(self):
        checker = CookieHealthChecker("cookie", check_interval_seconds=600)
        checker._last_check_ts = time.time()
        checker._cached_result = {"healthy": True, "message": "cached"}
        result = await checker.check_async()
        assert result["message"] == "cached"

    async def test_check_async_no_cookie(self):
        checker = CookieHealthChecker("")
        result = await checker.check_async(force=True)
        assert result["healthy"] is False

    async def test_check_async_success_triggers_state_change(self):
        notifier = AsyncMock()
        checker = CookieHealthChecker("cookie", notifier=notifier)
        checker._last_healthy = False

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_async_client):
            result = await checker.check_async(force=True)
            assert result["healthy"] is True
            notifier.send_text.assert_called_once()

    async def test_check_async_failure_triggers_alert(self):
        notifier = AsyncMock()
        checker = CookieHealthChecker("cookie", notifier=notifier, alert_cooldown_seconds=60)
        checker._last_healthy = True
        checker._last_alert_ts = 0.0

        mock_resp = MagicMock()
        mock_resp.status_code = 302
        mock_resp.headers = {"location": "https://login.example.com/login"}
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_async_client):
            result = await checker.check_async(force=True)
            assert result["healthy"] is False
            notifier.send_text.assert_called_once()

    async def test_check_async_alert_send_fails(self):
        notifier = AsyncMock()
        notifier.send_text.side_effect = RuntimeError("send failed")
        checker = CookieHealthChecker("cookie", notifier=notifier, alert_cooldown_seconds=60)
        checker._last_healthy = True
        checker._last_alert_ts = 0.0

        mock_resp = MagicMock()
        mock_resp.status_code = 302
        mock_resp.headers = {"location": "https://login.example.com/login"}
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_async_client):
            result = await checker.check_async(force=True)
            assert result["healthy"] is False

    async def test_check_async_recovery_send_fails(self):
        notifier = AsyncMock()
        notifier.send_text.side_effect = RuntimeError("send failed")
        checker = CookieHealthChecker("cookie", notifier=notifier)
        checker._last_healthy = False

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_async_client):
            result = await checker.check_async(force=True)
            assert result["healthy"] is True

    async def test_check_async_timeout(self):
        checker = CookieHealthChecker("cookie")
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.get = AsyncMock(side_effect=httpx.TimeoutException("t"))

        with patch("httpx.AsyncClient", return_value=mock_async_client):
            result = await checker.check_async(force=True)
            assert result["healthy"] is False

    async def test_check_async_exception(self):
        checker = CookieHealthChecker("cookie")
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.get = AsyncMock(side_effect=RuntimeError("err"))

        with patch("httpx.AsyncClient", return_value=mock_async_client):
            result = await checker.check_async(force=True)
            assert result["healthy"] is False

    async def test_no_notifier_state_change(self):
        checker = CookieHealthChecker("cookie", notifier=None)
        checker._last_healthy = False
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_async_client):
            result = await checker.check_async(force=True)
            assert result["healthy"] is True

    async def test_alert_cooldown_not_reached(self):
        notifier = AsyncMock()
        checker = CookieHealthChecker("cookie", notifier=notifier, alert_cooldown_seconds=3600)
        checker._last_healthy = None
        checker._last_alert_ts = time.time()

        mock_resp = MagicMock()
        mock_resp.status_code = 302
        mock_resp.headers = {"location": "https://login.example.com/login"}
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_async_client):
            result = await checker.check_async(force=True)
            assert result["healthy"] is False
            notifier.send_text.assert_not_called()

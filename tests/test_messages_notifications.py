"""Tests for src.modules.messages.notifications."""

import pytest

from src.modules.messages.notifications import (
    FeishuNotifier,
    format_alert_message,
    format_heartbeat_message,
    format_recovery_message,
    format_start_message,
)


class _DummyResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _DummyClient:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.called = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json):
        self.called.append((url, json))
        return _DummyResponse(200)


@pytest.mark.asyncio
async def test_feishu_notifier_disabled_returns_false() -> None:
    """分支：enabled=False 时 send_text 直接返回 False。"""
    notifier = FeishuNotifier(webhook_url="   ")

    ok = await notifier.send_text("hello")

    assert notifier.enabled is False
    assert ok is False


@pytest.mark.asyncio
async def test_feishu_notifier_send_success(monkeypatch) -> None:
    """分支：httpx post 2xx 返回 True，并验证 payload strip。"""

    holder = {}

    def _factory(*args, **kwargs):
        client = _DummyClient(*args, **kwargs)
        holder["client"] = client
        return client

    monkeypatch.setattr("src.modules.messages.notifications.httpx.AsyncClient", _factory)

    notifier = FeishuNotifier(webhook_url=" https://hook.local ", timeout_seconds=0.2)
    ok = await notifier.send_text("  ping  ")

    assert ok is True
    assert holder["client"].kwargs["timeout"] == 1.0  # min timeout guard
    (url, payload), *_ = holder["client"].called
    assert url == "https://hook.local"
    assert payload == {"msg_type": "text", "content": {"text": "ping"}}


@pytest.mark.asyncio
async def test_feishu_notifier_send_non_2xx_and_exception(monkeypatch) -> None:
    """分支：非2xx返回 False；异常捕获返回 False。"""

    class _BadStatusClient(_DummyClient):
        async def post(self, url, json):  # noqa: ARG002
            return _DummyResponse(500)

    class _ErrorClient(_DummyClient):
        async def post(self, url, json):  # noqa: ARG002
            raise RuntimeError("boom")

    monkeypatch.setattr("src.modules.messages.notifications.httpx.AsyncClient", _BadStatusClient)
    notifier = FeishuNotifier(webhook_url="https://hook.local")
    assert await notifier.send_text("x") is False

    monkeypatch.setattr("src.modules.messages.notifications.httpx.AsyncClient", _ErrorClient)
    assert await notifier.send_text("x") is False


def test_format_message_helpers_cover_optional_branches() -> None:
    """分支：title存在/缺失、last非dict兜底、默认值拼接。"""
    alert = format_alert_message(
        alerts=[{"title": "高延迟", "message": "P95超标"}, {"message": "仅消息"}],
        sla={"first_reply_p95_ms": 321, "quote_success_rate": 0.98, "quote_fallback_rate": 0.01},
        workflow={"jobs": {"a": 1}, "states": {"new": 2}},
    )
    assert "- 高延迟: P95超标" in alert
    assert "- 仅消息" in alert

    recovery = format_recovery_message(
        sla={"first_reply_p95_ms": 123, "quote_success_rate": 1.0, "quote_fallback_rate": 0.0},
        workflow={"jobs": {}, "states": {"closed": 1}},
    )
    assert "告警恢复" in recovery
    assert "states={'closed': 1}" in recovery

    start = format_start_message(1.5, dry_run=True)
    assert "poll_interval=1.5s" in start
    assert "dry_run=True" in start

    hb = format_heartbeat_message(last="not-dict", loops=2)
    assert "心跳 loops=2" in hb
    assert "首响P95=0ms" in hb

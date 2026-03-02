from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import src.modules.messages.ws_live as ws_live
from src.core.error_handler import BrowserError
from src.dashboard_server import MimicOps, ModuleConsole
from src.modules.messages.ws_live import GoofishWsTransport, extract_chat_event


@pytest.fixture
def ws_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ws_live, "websockets", object())


def _transport(config: dict | None = None) -> GoofishWsTransport:
    cfg = {
        "queue_wait_seconds": 0.01,
        "message_expire_ms": 1000,
        "cookie_watch_interval_seconds": 1,
        "token_max_attempts": 1,
    }
    if config:
        cfg.update(config)
    return GoofishWsTransport(
        cookie_text="unb=10001; _m_h5_tk=token_a_123; cookie2=a; _tb_token_=t; sgcookie=s",
        config=cfg,
    )


def test_extract_chat_event_guards_for_non_dict_body_and_missing_fields() -> None:
    assert extract_chat_event({"1": "not-dict"}) is None

    missing_required = {
        "1": {
            "2": "chat123@goofish",
            "10": {"reminderContent": "", "senderUserId": "u1"},
        }
    }
    assert extract_chat_event(missing_required) is None


@pytest.mark.asyncio
async def test_wait_for_cookie_update_forever_sleeps_then_stops(ws_enabled: None, monkeypatch: pytest.MonkeyPatch) -> None:
    t = _transport({"cookie_watch_interval_seconds": 1})
    t.cookie_supplier = lambda: t.cookie_text

    sleep_calls = {"n": 0}

    async def fake_sleep(_seconds: float) -> None:
        sleep_calls["n"] += 1
        t._stop_event.set()

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    changed = await t._wait_for_cookie_update_forever()
    assert changed is False
    assert sleep_calls["n"] == 1


@pytest.mark.asyncio
async def test_fetch_token_auth_fail_logs_preflight_retry_error(ws_enabled: None, monkeypatch: pytest.MonkeyPatch) -> None:
    t = _transport({"token_max_attempts": 1})

    async def fake_preflight() -> bool:
        raise RuntimeError("preflight-broken")

    class _Resp:
        def json(self):
            return {"ret": ["FAIL_SYS_USER_VALIDATE::risk"]}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return _Resp()

    debug_messages: list[str] = []

    async def no_sleep(*_args, **_kwargs):
        return None

    monkeypatch.setattr(t, "_preflight_has_login", fake_preflight)
    monkeypatch.setattr(ws_live.httpx, "AsyncClient", lambda *a, **k: _Client())
    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    t.logger = SimpleNamespace(info=lambda *_a, **_k: None, warning=lambda *_a, **_k: None, debug=debug_messages.append)

    with pytest.raises(BrowserError, match="Token API failed"):
        await t._fetch_token()

    assert any("hasLogin retry failed: preflight-broken" in msg for msg in debug_messages)


@pytest.mark.asyncio
async def test_stop_handles_cancelled_run_task(ws_enabled: None) -> None:
    t = _transport()

    async def cancelled_task() -> None:
        raise asyncio.CancelledError

    t._run_task = asyncio.create_task(cancelled_task())
    await t.stop()

    assert t._run_task is None
    assert t._stop_event.is_set() is True


def test_apply_cookie_text_rejects_empty_cookie(ws_enabled: None) -> None:
    with pytest.raises(BrowserError, match="Missing cookie text"):
        GoofishWsTransport(cookie_text="", config={})


def test_maybe_auto_recover_double_check_sets_waiting_reconnect(temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))

    target_cookie = "unb=20001; _m_h5_tk=new_1; cookie2=a"
    target_fp = ops._cookie_fingerprint(target_cookie)

    class _RaceLock:
        def __enter__(self):
            # 模拟并发：进入锁后已被其他线程标记为同 cookie 已恢复。
            ops._last_auto_recover_cookie_fp = target_fp

        def __exit__(self, *_args):
            return False

    ops._recover_lock = _RaceLock()  # type: ignore[assignment]
    ops._last_token_error = "FAIL_SYS_USER_VALIDATE"
    ops._last_cookie_fp = "old-fp"
    ops._last_auto_recover_cookie_fp = "another-fp"
    ops.module_console = Mock()

    out = ops._maybe_auto_recover_presales(
        service_status="running",
        token_error="FAIL_SYS_USER_VALIDATE",
        cookie_text=target_cookie,
    )

    assert out["stage"] == "waiting_reconnect"
    assert out["reason"] == "same_cookie_already_recovered"
    ops.module_console.control.assert_not_called()


def test_service_status_handles_non_dict_modules_and_suspended_state(temp_dir, monkeypatch: pytest.MonkeyPatch) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))
    ops._service_state["suspended"] = True

    monkeypatch.setattr(
        ops.module_console,
        "status",
        lambda **_k: {"modules": ["bad"], "alive_count": 0, "total_modules": 3},
    )
    monkeypatch.setattr(ops, "get_cookie", lambda: {"success": True, "cookie": "unb=30001; cookie2=a"})
    monkeypatch.setattr(ops, "route_stats", lambda: {"stats": {"courier_details": {}}})
    monkeypatch.setattr(ops, "_risk_control_status_from_logs", lambda **_k: {"level": "normal", "signals": []})
    monkeypatch.setattr(
        ops,
        "_query_message_stats_from_workflow",
        lambda: {
            "total_replied": 0,
            "today_replied": 0,
            "recent_replied": 0,
            "total_conversations": 0,
            "total_messages": 0,
            "hourly_replies": {},
            "daily_replies": {},
        },
    )

    payload = ops.service_status()

    assert payload["service_status"] == "suspended"
    assert payload["alive_count"] == 0
    assert payload["module"]["modules"] == ["bad"]
    assert payload["xianyu_connected"] is False

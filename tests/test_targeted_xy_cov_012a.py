import asyncio
import base64
import json

import pytest

import src.dashboard_server as ds
from src.modules.messages import ws_live


class _DummyConsole(ds.ModuleConsole):
    def __init__(self):
        super().__init__(project_root=".")
        self.calls = []

    def _run_module_cli(self, action, target, extra_args=None, timeout_seconds=120):
        self.calls.append((action, target, list(extra_args or []), timeout_seconds))
        return {"ok": True}


def test_module_console_control_validation_and_args():
    c = _DummyConsole()

    bad_action = c.control("noop", "all")
    assert "Unsupported module action" in bad_action["error"]

    bad_target = c.control("start", "unknown")
    assert "Unsupported module target" in bad_target["error"]

    c.control("start", "all")
    c.control("restart", "presales")
    c.control("recover", "operations")
    c.control("stop", "aftersales")

    start = c.calls[0]
    assert start[0] == "start"
    assert "--background" in start[2]

    restart = c.calls[1]
    assert restart[0] == "restart"
    assert "--stop-timeout" in restart[2]

    recover = c.calls[2]
    assert recover[0] == "recover"
    assert "--stop-timeout" in recover[2]

    stop = c.calls[3]
    assert stop[0] == "stop"
    assert stop[2] == ["--stop-timeout", "6"]


def test_cookie_domain_filter_and_recovery_advice_paths(tmp_path):
    ops = ds.MimicOps(project_root=tmp_path, module_console=ds.ModuleConsole(project_root=tmp_path))

    raw = """# Netscape
.bad.com\tTRUE\t/\tFALSE\t0\ta\t1
.goofish.com\tTRUE\t/\tFALSE\t0\tb\t2
{"cookies":[{"name":"x","value":"1","domain":".evil.example"}]}
"""
    stat = ops._cookie_domain_filter_stats(raw)
    assert stat["checked"] >= 2
    assert stat["rejected"] >= 1
    assert any("bad.com" in s or "evil.example" in s for s in stat["rejected_samples"])

    assert ops._recovery_stage_label("healthy") == "链路正常"
    assert ops._recovery_stage_label("unknown-stage") == "状态未知"

    assert "等待 5-20 秒" in ops._recovery_advice("recover_triggered")
    assert "重新登录" in ops._recovery_advice("waiting_cookie_update", "FAIL_SYS_USER_VALIDATE")
    assert "连接通道异常" in ops._recovery_advice("token_error", "WS_HTTP_400")


def test_ws_live_decode_urlsafe_and_extract_create_time_fallback(monkeypatch):
    payload = {"a": 1, "b": [2, 3]}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")

    def boom(_txt):
        raise ValueError("boom")

    monkeypatch.setattr(ws_live.base64, "b64decode", boom)
    monkeypatch.setattr(ws_live.base64, "urlsafe_b64decode", lambda _txt: json.dumps(payload).encode())
    assert ws_live.decode_sync_payload(encoded) == payload

    event = ws_live.extract_chat_event(
        {
            "1": {
                "2": "cid-001@goofish",
                "5": "bad-int",
                "10": {"text": "hello", "senderUserId": "u-1", "senderNick": "A"},
            }
        }
    )
    assert event is not None
    assert event["chat_id"] == "cid-001"
    assert event["sender_user_id"] == "u-1"
    assert event["text"] == "hello"
    assert isinstance(event["create_time"], int)


@pytest.mark.asyncio
async def test_ws_live_wait_and_reconnect_delay_paths(monkeypatch):
    monkeypatch.setattr(ws_live, "websockets", object())
    t = ws_live.GoofishWsTransport(
        cookie_text="unb=1001; _m_h5_tk=tk_1; cookie2=c2",
        config={
            "reconnect_delay_seconds": 1,
            "max_reconnect_delay_seconds": 3,
            "auth_failure_backoff_seconds": 17,
            "cookie_watch_interval_seconds": 0.01,
        },
    )

    t._connect_failures = 9
    assert t._next_reconnect_delay(auth_error=False) == 5
    assert t._next_reconnect_delay(auth_error=True) == 17

    ok = await t._wait_for_cookie_update(timeout_seconds=0.05)
    assert ok is False

    calls = {"n": 0}

    def supplier():
        calls["n"] += 1
        return "unb=1001; _m_h5_tk=tk_2; cookie2=c2"

    t.cookie_supplier = supplier
    ok2 = await t._wait_for_cookie_update(timeout_seconds=0.2)
    assert ok2 is True
    assert calls["n"] >= 1

    ev = asyncio.Event()
    hit = await t._wait_event_with_timeout(ev, timeout=0.01)
    assert hit is False


def test_messagepack_unknown_byte_raises():
    dec = ws_live.MessagePackDecoder(b"\xc1")
    with pytest.raises(ValueError, match="Unknown MessagePack byte"):
        dec.decode()

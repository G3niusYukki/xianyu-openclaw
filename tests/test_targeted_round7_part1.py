# ISSUES FOUND:
# - src.modules.messages.ws_live.get_unread_sessions/send_text uses `await asyncio.wait_for(self._ready.wait(), ...)`.
#   If tests monkeypatch Event.wait with plain coroutine object incorrectly, RuntimeWarning appears.

from __future__ import annotations

import argparse
import asyncio
import json

import pytest

from src import cli
from src.core.browser_client import BrowserClient
from src.modules.messages.ws_live import GoofishWsTransport
from src.lite.msgpack import MessagePackDecoder, decrypt_payload
from src.lite.ws_client import LiteWsClient


class _Resp:
    def __init__(self, status_code=200, payload=None, text="", is_success=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.content = b""
        self.is_success = (200 <= status_code < 300) if is_success is None else is_success

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_cli_cmd_module_status_stop_restart_logs_and_main_keyboard(monkeypatch):
    out = []
    monkeypatch.setattr("src.cli._json_out", lambda d: out.append(d))
    monkeypatch.setattr("src.cli._module_process_status", lambda _t: {"alive": True})

    class _Store:
        def __init__(self, db_path=None):
            self.db_path = db_path

        def get_workflow_summary(self):
            return {"ok": 1}

        def get_sla_summary(self, window_minutes=0):
            return {"window": window_minutes}

    class _Orders:
        def __init__(self, db_path=None):
            self.db_path = db_path

        def list_orders(self, **_k):
            return [{"order_id": "o1", "session_id": "s1", "manual_takeover": False, "updated_at": "now"}]

        def get_summary(self):
            return {"total": 1}

    class _Scheduler:
        def get_scheduler_status(self):
            return {"running": True}

    monkeypatch.setattr("src.modules.messages.workflow.WorkflowStore", _Store)
    monkeypatch.setattr("src.modules.orders.service.OrderFulfillmentService", _Orders)
    monkeypatch.setattr("src.modules.accounts.scheduler.Scheduler", _Scheduler)

    await cli.cmd_module(argparse.Namespace(action="status", target="all", workflow_db="w.db", window_minutes=12, orders_db="o.db", limit=1))
    assert out[-1]["alive_count"] == 3

    monkeypatch.setattr("src.cli._stop_background_module", lambda target, timeout_seconds=6.0: {"target": target, "stopped": True, "t": timeout_seconds})
    await cli.cmd_module(argparse.Namespace(action="stop", target="presales", stop_timeout=3.2))
    assert out[-1]["stopped"] is True

    monkeypatch.setattr("src.cli._start_background_module", lambda target, args: {"target": target, "started": True, "mode": args.mode})
    await cli.cmd_module(argparse.Namespace(action="restart", target="all", stop_timeout=2.5, mode="daemon"))
    assert set(out[-1]["modules"].keys()) == {"presales", "operations", "aftersales"}

    monkeypatch.setattr("src.cli._module_logs", lambda target, tail_lines=80: {"target": target, "tail_lines": tail_lines})
    await cli.cmd_module(argparse.Namespace(action="logs", target="all", tail_lines=21))
    assert out[-1]["modules"]["operations"]["tail_lines"] == 21



@pytest.mark.asyncio
async def test_browser_client_connect_error_and_misc_branches(monkeypatch):
    c = BrowserClient({"retry_times": 1, "delay_min": 0.0, "delay_max": 0.0})

    class C1:
        async def get(self, *_a, **_k):
            raise RuntimeError("down")

        async def post(self, *_a, **_k):
            return _Resp(200, {})

        async def delete(self, *_a, **_k):
            return _Resp(200, {})

        async def aclose(self):
            return None

    monkeypatch.setattr("src.core.browser_client.httpx.AsyncClient", lambda **_k: C1())
    assert await c.connect() is False

    c._client = C1()
    c.state = c.state.CONNECTED

    async def focus(_p):
        return None

    async def act(*_a, **_k):
        return {"text": "t", "value": "v"}

    c._focus_tab = focus
    c._act = act

    assert await c.get_text("p", "#a") == "t"
    assert await c.get_value("p", "#a") == "v"

    async def act_fail(*_a, **_k):
        raise RuntimeError("x")

    c._act = act_fail
    assert await c.double_click("p", "#a") is False
    assert await c.select_option("p", "#a", "1") is False
    assert await c.check("p", "#a") is False


@pytest.mark.asyncio
async def test_ws_live_fetch_token_success_and_run_typeerror_connect(monkeypatch):
    t = GoofishWsTransport(cookie_text="unb=10001; _m_h5_tk=tk_1; cookie2=a", config={"token_max_attempts": 2, "auth_hold_until_cookie_update": False})
    t._maybe_reload_cookie = lambda **_k: False

    async def ok_preflight():
        return True

    t._preflight_has_login = ok_preflight

    class CM:
        async def __aenter__(self):
            class C:
                async def post(self, *_a, **_k):
                    class R:
                        def json(self):
                            return {"ret": ["SUCCESS::调用成功"], "data": {"accessToken": "AT"}}

                    return R()

            return C()

        async def __aexit__(self, *_a):
            return False

    monkeypatch.setattr("src.modules.messages.ws_live.httpx.AsyncClient", lambda **_k: CM())
    assert await t._fetch_token() == "AT"

    calls = {"n": 0}

    class WS:
        async def recv(self):
            t._stop_event.set()
            return json.dumps({"code": 200, "headers": {"mid": "m"}})

        async def send(self, _x):
            return None

        async def close(self):
            return None

    async def connect(*_a, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1 and "extra_headers" in kwargs:
            raise TypeError("extra_headers")
        return WS()

    monkeypatch.setattr("src.modules.messages.ws_live.websockets.connect", connect)

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(t, "_send_reg", _noop)
    monkeypatch.setattr(t, "_ack_packet", _noop)
    monkeypatch.setattr(t, "_handle_sync", _noop)
    monkeypatch.setattr("src.modules.messages.ws_live.asyncio.sleep", _noop)

    await t._run()
    assert calls["n"] >= 2


def test_lite_msgpack_remaining_tags_and_decrypt_hex_fallback():
    assert MessagePackDecoder(bytes([0xCA, 0x3F, 0x80, 0x00, 0x00])).decode() == pytest.approx(1.0)
    assert MessagePackDecoder(bytes([0xCB, 0x3F, 0xF0, 0, 0, 0, 0, 0, 0])).decode() == pytest.approx(1.0)
    assert MessagePackDecoder(bytes([0xCC, 0xFE])).decode() == 254
    assert MessagePackDecoder(bytes([0xCD, 0x01, 0x02])).decode() == 258
    assert MessagePackDecoder(bytes([0xCE, 0, 0, 1, 0])).decode() == 256
    assert MessagePackDecoder(bytes([0xCF, 0, 0, 0, 0, 0, 0, 0, 1])).decode() == 1
    assert MessagePackDecoder(bytes([0xD0, 0xFF])).decode() == -1
    assert MessagePackDecoder(bytes([0xD1, 0xFF, 0xFE])).decode() == -2
    assert MessagePackDecoder(bytes([0xD2, 0xFF, 0xFF, 0xFF, 0xFD])).decode() == -3
    assert MessagePackDecoder(bytes([0xD3, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFC])).decode() == -4
    assert MessagePackDecoder(bytes([0xD9, 0x01, ord("a")])).decode() == "a"
    assert MessagePackDecoder(bytes([0xDA, 0x00, 0x01, ord("b")])).decode() == "b"
    assert MessagePackDecoder(bytes([0xDB, 0, 0, 0, 1, ord("c")])).decode() == "c"
    assert MessagePackDecoder(bytes([0xDC, 0x00, 0x01, 0x01])).decode() == [1]
    assert MessagePackDecoder(bytes([0xDD, 0, 0, 0, 1, 0x01])).decode() == [1]
    assert MessagePackDecoder(bytes([0xDE, 0x00, 0x01, 0xA1, ord("k"), 0x01])).decode() == {"k": 1}
    assert MessagePackDecoder(bytes([0xDF, 0, 0, 0, 1, 0xA1, ord("k"), 0x01])).decode() == {"k": 1}
    assert decrypt_payload("@@@") is None


@pytest.mark.asyncio
async def test_lite_ws_client_run_forever_typeerror_and_send_fail(monkeypatch):
    async def token_provider():
        return "tk"

    c = LiteWsClient(ws_url="wss://x", cookie="a=1", device_id="d", my_user_id="me", token_provider=token_provider, heartbeat_interval=0, heartbeat_timeout=1)

    class WS:
        def __init__(self):
            self.sent = 0

        async def send(self, _p):
            self.sent += 1
            if self.sent > 3:
                raise RuntimeError("send fail")

        async def recv(self):
            await asyncio.sleep(0)
            return json.dumps({"code": 200, "headers": {"mid": "m1"}})

        async def close(self):
            return None

    calls = {"n": 0}

    async def connect(*_a, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1 and "extra_headers" in kwargs:
            raise TypeError("extra_headers")
        return WS()

    monkeypatch.setattr("src.lite.ws_client.websockets.connect", connect)

    async def stop_soon():
        await asyncio.sleep(0.05)
        await c.stop()

    task = asyncio.create_task(c.run_forever())
    await stop_soon()
    await task

    assert calls["n"] >= 2
    assert await c.send_text("chat", "u1", "hello") is False


def test_main_keyboardinterrupt_path(monkeypatch):
    class P:
        def parse_args(self):
            return argparse.Namespace(command="publish")

        def print_help(self):
            return None

    monkeypatch.setattr("src.cli.build_parser", lambda: P())
    monkeypatch.setattr("src.cli.cmd_publish", lambda _args: None)
    monkeypatch.setattr("src.cli.asyncio.run", lambda _obj: (_ for _ in ()).throw(KeyboardInterrupt()))
    cli.main()

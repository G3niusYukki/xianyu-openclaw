from __future__ import annotations

import asyncio
import json

import pytest

from src.core.error_handler import BrowserError
from src.modules.messages.ws_live import GoofishWsTransport


@pytest.fixture
def ws_enabled(monkeypatch):
    class WSModule:
        async def connect(self, *_a, **_k):
            raise RuntimeError("stub")

    monkeypatch.setattr("src.modules.messages.ws_live.websockets", WSModule())


def _transport():
    return GoofishWsTransport(cookie_text="unb=10001; _m_h5_tk=token_a_123; cookie2=a", config={"token_max_attempts": 1})


@pytest.mark.asyncio
async def test_fetch_token_missing_and_risk_break(ws_enabled, monkeypatch):
    t = _transport()

    async def _ok():
        return True

    t._preflight_has_login = _ok
    t._maybe_reload_cookie = lambda **_k: False
    t.cookies = {"unb": "10001"}

    with pytest.raises(BrowserError):
        await t._fetch_token()

    t.cookies = {"unb": "10001", "_m_h5_tk": "token_x_1"}

    class CM:
        async def __aenter__(self):
            class C:
                async def post(self, *_a, **_k):
                    class R:
                        def json(self):
                            return {"ret": ["FAIL_SYS_USER_VALIDATE::risk"]}

                    return R()

            return C()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr("src.modules.messages.ws_live.httpx.AsyncClient", lambda **_k: CM())
    with pytest.raises(BrowserError):
        await t._fetch_token()


@pytest.mark.asyncio
async def test_fetch_token_request_exception(ws_enabled, monkeypatch):
    t = _transport()

    async def _ok():
        return True

    t._preflight_has_login = _ok
    t.cookies = {"unb": "10001", "_m_h5_tk": "token_x_1"}

    class CM:
        async def __aenter__(self):
            class C:
                async def post(self, *_a, **_k):
                    raise RuntimeError("network")

            return C()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr("src.modules.messages.ws_live.httpx.AsyncClient", lambda **_k: CM())
    with pytest.raises(BrowserError):
        await t._fetch_token()


@pytest.mark.asyncio
async def test_run_reconnect_auth_hold_and_close(ws_enabled, monkeypatch):
    t = _transport()
    calls = {"connect": 0, "wait": 0}

    class WSError(Exception):
        pass

    async def fake_connect(*_a, **_k):
        calls["connect"] += 1
        if calls["connect"] == 1:
            raise WSError("HTTP 401 forbidden")

        class WS:
            async def recv(self):
                t._stop_event.set()
                return json.dumps({"code": 200, "headers": {"mid": "m1"}})

            async def send(self, _x):
                return None

            async def close(self):
                return None

        return WS()

    monkeypatch.setattr("src.modules.messages.ws_live.websockets.connect", fake_connect)

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(t, "_send_reg", _noop)
    monkeypatch.setattr(t, "_ack_packet", _noop)
    monkeypatch.setattr(t, "_handle_sync", _noop)

    async def fake_wait_forever():
        calls["wait"] += 1
        return True

    monkeypatch.setattr(t, "_wait_for_cookie_update_forever", fake_wait_forever)

    async def fake_sleep(*_a, **_k):
        return None

    monkeypatch.setattr("src.modules.messages.ws_live.asyncio.sleep", fake_sleep)

    await t._run()
    assert calls["wait"] == 1
    assert calls["connect"] >= 2


@pytest.mark.asyncio
async def test_get_unread_and_send_text_timeout_paths(ws_enabled, monkeypatch):
    t = _transport()

    async def fake_start():
        return None

    t.start = fake_start
    t._ready.clear()

    async def raise_timeout(*_a, **_k):
        raise asyncio.TimeoutError

    monkeypatch.setattr("src.modules.messages.ws_live.asyncio.wait_for", raise_timeout)
    assert await t.get_unread_sessions(limit=2) == []
    assert await t.send_text("s", "x") is False


@pytest.mark.asyncio
async def test_ack_packet_and_handle_sync_guards(ws_enabled):
    t = _transport()

    class WS:
        def __init__(self):
            self.sent = []

        async def send(self, p):
            self.sent.append(p)

    ws = WS()
    t._ws = ws

    await t._ack_packet({"headers": "bad"})
    await t._ack_packet({"headers": {}})
    assert ws.sent == []

    await t._handle_sync({"body": "bad"})
    await t._handle_sync({"body": {"syncPushPackage": "bad"}})
    await t._handle_sync({"body": {"syncPushPackage": {"data": "bad"}}})

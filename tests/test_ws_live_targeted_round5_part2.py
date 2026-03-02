from __future__ import annotations

import asyncio
import json

import pytest

from src.core.error_handler import BrowserError
from src.modules.messages import ws_live
from src.modules.messages.ws_live import GoofishWsTransport, MessagePackDecoder, decode_sync_payload, extract_chat_event


@pytest.fixture
def ws_enabled(monkeypatch):
    monkeypatch.setattr("src.modules.messages.ws_live.websockets", object())


def _transport(config: dict | None = None) -> GoofishWsTransport:
    base = {
        "queue_wait_seconds": 0.01,
        "message_expire_ms": 500,
        "heartbeat_interval_seconds": 1,
        "heartbeat_timeout_seconds": 1,
        "reconnect_delay_seconds": 0.2,
    }
    if config:
        base.update(config)
    return GoofishWsTransport(cookie_text="unb=10001; _m_h5_tk=token_a_123; cookie2=a", config=base)


def test_messagepack_decoder_more_paths() -> None:
    assert MessagePackDecoder(bytes([0xE0])).decode() == -32
    assert MessagePackDecoder(bytes([0xCC, 0x7F])).decode() == 127
    assert MessagePackDecoder(bytes([0xD0, 0xFF])).decode() == -1
    assert MessagePackDecoder(bytes([0xCA, 0x3F, 0x80, 0x00, 0x00])).decode() == 1.0
    assert MessagePackDecoder(bytes([0xD9, 0x03, 0x61, 0x62, 0x63])).decode() == "abc"
    assert MessagePackDecoder(bytes([0xDC, 0x00, 0x01, 0x01])).decode() == [1]

    with pytest.raises(ValueError, match="Unknown MessagePack byte"):
        MessagePackDecoder(bytes([0xC1])).decode()

    with pytest.raises(ValueError, match="Unexpected end of data"):
        MessagePackDecoder(bytes([0xC5, 0x00])).decode()


def test_decode_sync_payload_decode_fail_branches(monkeypatch) -> None:
    monkeypatch.setattr("src.modules.messages.ws_live.base64.b64decode", lambda _x: (_ for _ in ()).throw(ValueError("bad")))
    monkeypatch.setattr(
        "src.modules.messages.ws_live.base64.urlsafe_b64decode",
        lambda _x: (_ for _ in ()).throw(ValueError("bad2")),
    )
    assert decode_sync_payload("abcd") is None


def test_extract_chat_event_more_branches() -> None:
    assert extract_chat_event({"1": "bad"}) is None
    assert extract_chat_event({"1": {"10": "bad"}}) is None
    assert extract_chat_event({"1": {"2": "c1", "10": {"content": "x", "senderId": ""}}}) is None

    event = extract_chat_event(
        {
            "1": {
                "chatId": "c2",
                "createTime": "not-int",
                "10": {"text": "hi", "senderId": "u2", "url": "https://x.test?a=1&itemId=77"},
            }
        }
    )
    assert event is not None
    assert event["chat_id"] == "c2"
    assert event["sender_name"] == "买家"
    assert event["item_id"] == "77"
    assert isinstance(event["create_time"], int)


def test_constructor_requires_websockets(monkeypatch) -> None:
    monkeypatch.setattr("src.modules.messages.ws_live.websockets", None)
    with pytest.raises(BrowserError, match="requires `websockets`"):
        GoofishWsTransport(cookie_text="unb=1", config={})


@pytest.mark.asyncio
async def test_reload_cookie_edge_cases(ws_enabled, monkeypatch) -> None:
    t = _transport()
    t.cookie_supplier = lambda: "unb=10001; _m_h5_tk=token_a_123; cookie2=a"
    assert t._maybe_reload_cookie(reason="same") is False

    t.cookie_supplier = lambda: ""
    assert t._maybe_reload_cookie(reason="empty") is False

    def raise_supplier():
        raise RuntimeError("boom")

    t.cookie_supplier = raise_supplier
    assert t._maybe_reload_cookie(reason="err") is False

    monkeypatch.setattr(t, "_apply_cookie_text", lambda *_a, **_k: (_ for _ in ()).throw(BrowserError("bad cookie")))
    t.cookie_supplier = lambda: "unb=10001; _m_h5_tk=token_b_123; cookie2=a"
    assert t._maybe_reload_cookie(reason="bad") is False


@pytest.mark.asyncio
async def test_wait_cookie_update_forever_stop_and_delay(ws_enabled) -> None:
    t = _transport()
    t._stop_event.set()
    assert await t._wait_for_cookie_update_forever() is False

    t2 = _transport({"reconnect_delay_seconds": 2.0, "max_reconnect_delay_seconds": 3.0})
    t2._connect_failures = 10
    assert t2._next_reconnect_delay(auth_error=False) == 5.0


@pytest.mark.asyncio
async def test_preflight_has_login_paths(ws_enabled, monkeypatch) -> None:
    t = _transport()

    class _JarItem:
        def __init__(self, name: str, value: str):
            self.name = name
            self.value = value

    class _Client:
        def __init__(self, payload, jar):
            self._payload = payload
            self.cookies = type("C", (), {"jar": jar})

        async def post(self, *_a, **_k):
            class _Resp:
                def __init__(self, payload):
                    self._payload = payload

                def json(self):
                    if self._payload == "raise":
                        raise ValueError("bad json")
                    return self._payload

            return _Resp(self._payload)

    class _CM:
        def __init__(self, payload, jar):
            self.client = _Client(payload, jar)

        async def __aenter__(self):
            return self.client

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr("src.modules.messages.ws_live.httpx.AsyncClient", lambda **_k: _CM("raise", []))
    assert await t._preflight_has_login() is False

    monkeypatch.setattr("src.modules.messages.ws_live.httpx.AsyncClient", lambda **_k: _CM({"content": {"success": True}}, []))
    assert await t._preflight_has_login() is True

    applied = {"called": False}

    def _apply(text: str, reason: str = ""):
        applied["called"] = True
        assert reason == "has_login_refresh"
        assert "_m_h5_tk=new_token_2" in text
        return True

    monkeypatch.setattr(t, "_apply_cookie_text", _apply)
    monkeypatch.setattr(
        "src.modules.messages.ws_live.httpx.AsyncClient",
        lambda **_k: _CM({"content": {"success": True}}, [_JarItem("_m_h5_tk", "new_token_2")]),
    )
    assert await t._preflight_has_login() is True
    assert applied["called"] is True


@pytest.mark.asyncio
async def test_fetch_token_cached_and_missing_access_token_retry(ws_enabled, monkeypatch) -> None:
    t = _transport({"token_max_attempts": 2})
    t._token = "cached"
    t._token_ts = ws_live.time.time()

    async def _preflight_ok():
        return True

    t._preflight_has_login = _preflight_ok
    assert await t._fetch_token() == "cached"

    t._token = ""
    t.cookies = {"unb": "10001", "_m_h5_tk": "seed_x_1"}

    async def _fast_sleep(*_a, **_k):
        return None

    monkeypatch.setattr("src.modules.messages.ws_live.asyncio.sleep", _fast_sleep)

    class _CM:
        async def __aenter__(self):
            class _C:
                async def post(self, *_a, **_k):
                    class _R:
                        def json(self):
                            return {"ret": ["SUCCESS::调用成功"], "data": {"accessToken": ""}}

                    return _R()

            return _C()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr("src.modules.messages.ws_live.httpx.AsyncClient", lambda **_k: _CM())
    with pytest.raises(BrowserError, match="accessToken missing"):
        await t._fetch_token()


@pytest.mark.asyncio
async def test_send_reg_heartbeat_ack_and_stop_paths(ws_enabled, monkeypatch) -> None:
    t = _transport()

    with pytest.raises(BrowserError, match="not connected"):
        await t._send_reg()

    sent: list[dict] = []

    class _WS:
        async def send(self, payload: str):
            sent.append(json.loads(payload))

        async def close(self):
            raise RuntimeError("close failed")

    t._ws = _WS()

    async def _fetch_token():
        return "token123"

    async def _fast_sleep(*_a, **_k):
        return None

    monkeypatch.setattr(t, "_fetch_token", _fetch_token)
    monkeypatch.setattr("src.modules.messages.ws_live.asyncio.sleep", _fast_sleep)

    await t._send_reg()
    assert sent[0]["lwp"] == "/reg"
    assert sent[1]["lwp"] == "/r/SyncStatus/ackDiff"

    await t._send_heartbeat()
    assert sent[-1]["lwp"] == "/!"

    await t._ack_packet({"headers": {"mid": "m1", "sid": "s1", "app-key": "ak", "ua": "ua", "dt": "j"}})
    ack = sent[-1]
    assert ack["code"] == 200
    assert ack["headers"]["mid"] == "m1"
    assert ack["headers"]["sid"] == "s1"
    assert ack["headers"]["app-key"] == "ak"

    t._run_task = asyncio.create_task(asyncio.sleep(0.01))
    await t.stop()
    assert t._ws is None
    assert t._run_task is None


@pytest.mark.asyncio
async def test_push_event_and_get_unread_dedupe_paths(ws_enabled) -> None:
    t = _transport({"max_queue_size": 10})
    t.my_user_id = "mine"

    await t._push_event({"chat_id": "", "sender_user_id": "u", "text": "x"})
    assert t._queue.qsize() == 0

    await t._push_event({"chat_id": "c", "sender_user_id": "mine", "text": "x"})
    assert t._queue.qsize() == 0

    await t._push_event({"chat_id": "c", "sender_user_id": "u", "text": "x", "create_time": 1})
    assert t._queue.qsize() == 0

    now_ms = int(ws_live.time.time() * 1000)
    await t._push_event({"chat_id": "c1", "sender_user_id": "u1", "text": "new", "create_time": now_ms})
    await t._push_event({"chat_id": "c2", "sender_user_id": "u2", "text": "new2", "create_time": now_ms})
    assert t._queue.qsize() == 2

    async def _start_noop():
        return None

    t.start = _start_noop
    t._ready.set()
    rows = await t.get_unread_sessions(limit=1)
    assert len(rows) == 1
    assert rows[0]["session_id"] in {"c1", "c2"}

    t._seen_event = {"k1": ws_live.time.time() - 1000.0}
    t._cleanup_seen()
    assert t._seen_event == {}


@pytest.mark.asyncio
async def test_send_text_error_branch(ws_enabled) -> None:
    t = _transport()

    class _WS:
        async def send(self, _x):
            raise RuntimeError("send failed")

    async def _start_noop():
        return None

    t.start = _start_noop
    t._ready.set()
    t._ws = _WS()
    t._session_peer["s1"] = "u1"
    assert await t.send_text("s1", "hello") is False

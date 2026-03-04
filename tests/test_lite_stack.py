import asyncio
import base64
import json

import pytest

from src.lite import LiteConfig
from src.lite.__main__ import _process_loop, _try_parse_quote_request, main as lite_main
from src.lite.config import load_lite_config
from src.lite.dedup import DualLayerDedup
from src.lite.msgpack import MessagePackDecoder, decrypt_payload
from src.lite.ws_client import LiteWsClient, generate_mid, generate_uuid
from src.lite.xianyu_api import XianyuApiClient, generate_device_id, generate_sign, parse_cookie_string


def test_lite_package_imports():
    cfg = LiteConfig(cookie="c", ai_key="")
    assert cfg.cookie == "c"


def test_load_lite_config_success_and_defaults(monkeypatch):
    monkeypatch.setenv("LITE_COOKIE", "  c1=v1; unb=u1  ")
    monkeypatch.setenv("OPENAI_API_KEY", " k ")
    monkeypatch.setenv("LITE_HEARTBEAT_INTERVAL", "3")
    monkeypatch.setenv("LITE_RECONNECT_MAX_DELAY", "5")

    cfg = load_lite_config()
    assert cfg.cookie == "c1=v1; unb=u1"
    assert cfg.ai_key == "k"
    assert cfg.heartbeat_interval == 3
    assert cfg.reconnect_max_delay == 5.0


def test_load_lite_config_missing_cookie(monkeypatch):
    monkeypatch.setenv("LITE_COOKIE", "")
    monkeypatch.setenv("XIANYU_COOKIE_1", "")
    monkeypatch.setenv("COOKIES_STR", "")
    with pytest.raises(ValueError):
        load_lite_config()


@pytest.mark.asyncio
async def test_dedup_init_seen_and_cleanup(tmp_path):
    db = tmp_path / "dedup.db"
    dedup = DualLayerDedup(str(db), exact_days=1, content_hours=1)
    await dedup.init()

    assert await dedup.seen_exact("chat", 1, "hi") is False
    assert await dedup.seen_exact("chat", 1, "hi") is True
    assert await dedup.seen_content("chat", "a   b") is False
    assert await dedup.seen_content("chat", "a b") is True

    await dedup.cleanup()


@pytest.mark.asyncio
async def test_dedup_exact_is_atomic_under_100_concurrency(tmp_path):
    db = tmp_path / "dedup_race.db"
    dedup = DualLayerDedup(str(db), exact_days=1, content_hours=1)
    await dedup.init()

    tasks = [dedup.seen_exact("chat", 123, "same-msg") for _ in range(100)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    exceptions = [r for r in results if isinstance(r, Exception)]
    assert exceptions == []

    bool_results = [r for r in results if isinstance(r, bool)]
    # Exactly one first-writer (False), all others are duplicates (True)
    assert bool_results.count(False) == 1
    assert bool_results.count(True) == 99


def test_msgpack_decoder_variants_and_errors():
    assert MessagePackDecoder(b"\x01").decode() == 1
    assert MessagePackDecoder(b"\xa2hi").decode() == "hi"
    assert MessagePackDecoder(b"\xc0").decode() is None
    assert MessagePackDecoder(b"\xc2").decode() is False
    assert MessagePackDecoder(b"\xc3").decode() is True
    assert MessagePackDecoder(b"\x92\x01\x02").decode() == [1, 2]
    assert MessagePackDecoder(b"\x81\xa1k\x01").decode() == {"k": 1}
    assert MessagePackDecoder(b"\xd0\xff").decode() == -1
    with pytest.raises(ValueError):
        MessagePackDecoder(b"").decode()
    with pytest.raises(ValueError):
        MessagePackDecoder(b"\xc1").decode()


def test_decrypt_payload_json_msgpack_and_fallback():
    raw_json = base64.b64encode(json.dumps({"a": 1}).encode()).decode()
    assert decrypt_payload(raw_json) == {"a": 1}

    raw_mp = base64.b64encode(b"\x81\xa1a\x01").decode()
    assert decrypt_payload(raw_mp) == {"a": 1}

    raw_bytes = base64.b64encode(b"\xc1").decode()
    assert decrypt_payload(raw_bytes) == {"hex": "c1"}
    assert decrypt_payload("!!!") is None


class DummyWS:
    def __init__(self, recv_values=None, fail_send=False):
        self.sent = []
        self.closed = False
        self._recv_values = list(recv_values or [])
        self.fail_send = fail_send

    async def send(self, payload):
        if self.fail_send:
            raise RuntimeError("boom")
        self.sent.append(payload)

    async def recv(self):
        if self._recv_values:
            val = self._recv_values.pop(0)
            if isinstance(val, Exception):
                raise val
            return val
        await asyncio.sleep(0)
        return json.dumps({"code": 200, "headers": {"mid": "x"}})

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_ws_client_extract_and_send(monkeypatch):
    async def tp():
        return "tok"

    c = LiteWsClient(
        ws_url="ws://x",
        cookie="k=v",
        device_id="d",
        my_user_id="me",
        token_provider=tp,
        heartbeat_interval=999,
    )

    hs = c._headers()
    assert hs["cookie"] == "k=v"

    await c._ack_packet({})

    c._ws = DummyWS()
    await c._send_heartbeat()
    assert c._last_heartbeat_send > 0

    await c._ack_packet({"headers": {"mid": "m1", "sid": "s1", "app-key": "a", "ua": "u", "dt": "j"}})
    assert any('"mid": "m1"' in x for x in c._ws.sent)

    event = c._extract_event({"1": {"2": "cid@goofish", "5": 9999999999999, "10": {"text": "hello", "senderId": "u1"}}})
    assert event and event["chat_id"] == "cid"

    assert c._extract_event({"1": {"2": "cid@goofish", "10": {"text": "x", "senderId": "me"}}}) is None
    assert c._extract_event({"x": 1}) is None

    monkeypatch.setattr("src.lite.ws_client.decrypt_payload", lambda _: {"1": {"2": "c@goofish", "5": 9999999999999, "10": {"text": "t", "senderId": "u"}}})
    await c._handle_sync({"body": {"syncPushPackage": {"data": [{"data": "raw"}]}}})
    got = await c.next_event()
    assert got["chat_id"] == "c"

    ok = await c.send_text("c", "u", "hi")
    assert ok is True

    c._ws = DummyWS(fail_send=True)
    assert await c.send_text("c", "u", "hi") is False

    await c.stop()
    assert c._stop.is_set()


@pytest.mark.asyncio
async def test_ws_client_register_and_run_forever_branches(monkeypatch):
    async def tp():
        return "tok"

    client = LiteWsClient(ws_url="ws://x", cookie="c", device_id="d", my_user_id="me", token_provider=tp)
    ws = DummyWS(recv_values=[json.dumps({"code": 200, "headers": {"mid": "m1"}})])

    with pytest.raises(RuntimeError):
        await LiteWsClient(ws_url="x", cookie="c", device_id="d", my_user_id="m", token_provider=tp)._register()

    client._ws = ws
    orig_sleep = asyncio.sleep

    async def fast_sleep(_):
        await orig_sleep(0)

    monkeypatch.setattr("asyncio.sleep", fast_sleep)
    await client._register()
    assert len(ws.sent) >= 2

    calls = {"n": 0}

    async def fake_connect(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TypeError("old sig")
        return ws

    monkeypatch.setattr("src.lite.ws_client.websockets.connect", fake_connect)

    async def fake_wait_for(coro, timeout=1.0):
        if hasattr(coro, "close"):
            coro.close()
        client._stop.set()
        return json.dumps({"code": 200, "headers": {"mid": "x"}})

    monkeypatch.setattr("asyncio.wait_for", fake_wait_for)
    await client.run_forever()
    assert calls["n"] >= 2


def test_helpers_and_quote_parser():
    assert generate_mid().endswith(" 0")
    assert generate_uuid().startswith("-")
    q = _try_parse_quote_request("上海到北京 2kg")
    assert q and q.weight == 2.0
    q2 = _try_parse_quote_request("上海到北京 2斤")
    assert q2 and q2.weight == 1.0
    assert _try_parse_quote_request("无效") is None


@pytest.mark.asyncio
async def test_process_loop_and_lite_main(monkeypatch):
    class Dedup:
        def __init__(self):
            self.n = 0

        async def cleanup(self):
            return None

        async def seen_exact(self, *a):
            self.n += 1
            return self.n == 2

        async def seen_content(self, *a):
            return False

    class WS:
        def __init__(self):
            self.events = [
                {"chat_id": "c", "sender_user_id": "u", "text": "上海到北京 2kg", "item_id": "it", "create_time": 1},
                {"chat_id": "", "sender_user_id": "u", "text": "x", "item_id": "", "create_time": 1},
            ]
            self.sent = []

        async def next_event(self):
            if self.events:
                return self.events.pop(0)
            raise asyncio.CancelledError

        async def send_text(self, c, u, t):
            self.sent.append((c, u, t))
            return True

        async def run_forever(self):
            raise asyncio.CancelledError

        async def stop(self):
            return None

    class RE:
        def generate_reply(self, **kwargs):
            return "fallback"

    class QR:
        def compose_reply(self):
            return "quote"

    class QE:
        async def get_quote(self, req):
            return QR()

    class Guard:
        def check_content(self, *a):
            return True, []

    monkeypatch.setattr("src.lite.__main__.get_compliance_guard", lambda: Guard())
    ws = WS()
    with pytest.raises(asyncio.CancelledError):
        await _process_loop(ws, Dedup(), RE(), QE())
    assert ws.sent

    class Cfg:
        cookie = "unb=1;_m_h5_tk=tok_1"
        dedup_db_path = "/tmp/x.db"
        dedup_exact_days = 1
        dedup_content_hours = 1
        default_reply = "d"
        virtual_default_reply = "v"
        ws_url = "ws://x"
        heartbeat_interval = 1
        heartbeat_timeout = 1
        reconnect_base_delay = 0.01
        reconnect_backoff = 1.0
        reconnect_max_delay = 0.02
        message_expire_ms = 999

    class API:
        def __init__(self, c):
            self.device_id = "d"
            self.user_id = "u"

        async def has_login(self):
            return True

        async def get_token(self, **kwargs):
            return "tok"

    class DD:
        def __init__(self, *a, **k):
            pass

        async def init(self):
            return None

    monkeypatch.setattr("src.lite.__main__.load_lite_config", lambda: Cfg())
    monkeypatch.setattr("src.lite.__main__.XianyuApiClient", API)
    monkeypatch.setattr("src.lite.__main__.DualLayerDedup", DD)
    monkeypatch.setattr("src.lite.__main__.LiteWsClient", lambda **kwargs: ws)

    async def fake_gather(*tasks):
        for t in tasks:
            t.cancel()
        raise asyncio.CancelledError

    monkeypatch.setattr("asyncio.gather", fake_gather)
    with pytest.raises(asyncio.CancelledError):
        await __import__("src.lite.__main__", fromlist=["_amain"])._amain()

    def _fake_run(coro):
        coro.close()
        return None

    monkeypatch.setattr("asyncio.run", _fake_run)
    lite_main()


class DummyResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class DummyClient:
    def __init__(self, responses=None, raises=None, **kwargs):
        self.responses = list(responses or [])
        self.raises = list(raises or [])

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        if self.raises:
            raise self.raises.pop(0)
        return DummyResp(self.responses.pop(0))


@pytest.mark.asyncio
async def test_xianyu_api_client_all_branches(monkeypatch):
    assert parse_cookie_string("a=1; b=2; bad") == {"a": "1", "b": "2"}
    assert len(generate_device_id("u")) > 36
    assert len(generate_sign("1", "t", "{}")) == 32

    c = XianyuApiClient("unb=u1; _m_h5_tk=tk_1; XSRF-TOKEN=x")
    with pytest.raises(ValueError):
        XianyuApiClient("k=v")

    c.update_cookie("unb=u2; _m_h5_tk=tk_1")
    assert c.user_id == "u2"
    with pytest.raises(ValueError):
        c.update_cookie("a=1")

    monkeypatch.setattr(
        "src.lite.xianyu_api.httpx.AsyncClient",
        lambda **kwargs: DummyClient(responses=[{"content": {"success": True}}]),
    )
    assert await XianyuApiClient("unb=u1; _m_h5_tk=tk_1").has_login() is True

    c2 = XianyuApiClient("unb=u1; _m_h5_tk=tk_1")
    state = {"n": 0}

    def _client_factory(**kwargs):
        state["n"] += 1
        if state["n"] == 1:
            return DummyClient(responses=[{"ret": ["FAIL"]}])
        return DummyClient(responses=[{"ret": ["SUCCESS::调用成功"], "data": {"accessToken": "A"}}])

    monkeypatch.setattr("src.lite.xianyu_api.httpx.AsyncClient", _client_factory)
    assert await c2.get_token(max_attempts=2) == "A"
    assert await c2.get_token() == "A"

    c3 = XianyuApiClient("unb=u1; _m_h5_tk=tk_1")
    monkeypatch.setattr(
        "src.lite.xianyu_api.httpx.AsyncClient",
        lambda **kwargs: DummyClient(responses=[{"ret": ["SUCCESS::调用成功"], "data": {}}]),
    )
    with pytest.raises(ValueError):
        await c3.get_token(max_attempts=1)

    c4 = XianyuApiClient("unb=u1; _m_h5_tk=tk_1")
    monkeypatch.setattr(
        "src.lite.xianyu_api.httpx.AsyncClient",
        lambda **kwargs: DummyClient(raises=[RuntimeError("x")]),
    )
    with pytest.raises(RuntimeError):
        await c4.get_token(max_attempts=1)

    c5 = XianyuApiClient("unb=u1; _m_h5_tk=tk_1")
    monkeypatch.setattr(
        "src.lite.xianyu_api.httpx.AsyncClient",
        lambda **kwargs: DummyClient(responses=[{"ret": ["SUCCESS::调用成功"], "data": {"k": 1}}]),
    )
    assert await c5.get_item_info("1")

    monkeypatch.setattr(
        "src.lite.xianyu_api.httpx.AsyncClient",
        lambda **kwargs: DummyClient(responses=[{"ret": ["FAIL"]}]),
    )
    with pytest.raises(ValueError):
        await c5.get_item_info("1", max_attempts=1)

    with pytest.raises(ValueError):
        await XianyuApiClient("unb=u1").get_item_info("1", max_attempts=1)


@pytest.mark.asyncio
async def test_process_loop_covers_dedup_and_fallback_and_compliance_block(monkeypatch):
    class WS:
        def __init__(self):
            self.events = [
                {"chat_id": "c", "sender_user_id": "u", "text": "上海到北京 2kg", "item_id": "it", "create_time": 1},
                {"chat_id": "c", "sender_user_id": "u", "text": "上海到北京 2kg", "item_id": "it", "create_time": 2},
                {"chat_id": "c", "sender_user_id": "u", "text": "上海到北京 2kg", "item_id": "it", "create_time": 3},
            ]
            self.sent = []

        async def next_event(self):
            if self.events:
                return self.events.pop(0)
            raise asyncio.CancelledError

        async def send_text(self, c, u, t):
            self.sent.append((c, u, t))
            return True

    class Dedup:
        def __init__(self):
            self.i = 0

        async def cleanup(self):
            return None

        async def seen_exact(self, *a):
            self.i += 1
            return self.i == 1

        async def seen_content(self, *a):
            return self.i == 2

    class RE:
        def generate_reply(self, **kwargs):
            return "fallback"

    class QE:
        async def get_quote(self, req):
            raise RuntimeError("quote failed")

    class Logger:
        def warning(self, *_a, **_k):
            return None

        def info(self, *_a, **_k):
            return None

    class Guard:
        def check_content(self, *_a, **_k):
            return False, ["risk"]

    monkeypatch.setattr("src.lite.__main__.get_logger", lambda: Logger())
    monkeypatch.setattr("src.lite.__main__.get_compliance_guard", lambda: Guard())

    ws = WS()
    with pytest.raises(asyncio.CancelledError):
        await _process_loop(ws, Dedup(), RE(), QE())
    assert ws.sent == []


@pytest.mark.asyncio
async def test_process_loop_uses_reply_engine_for_non_quote(monkeypatch):
    class WS:
        def __init__(self):
            self.sent = []
            self._done = False

        async def next_event(self):
            if self._done:
                raise asyncio.CancelledError
            self._done = True
            return {"chat_id": "c", "sender_user_id": "u", "text": "你好", "item_id": "it", "create_time": 1}

        async def send_text(self, c, u, t):
            self.sent.append((c, u, t))
            return True

    class Dedup:
        async def cleanup(self):
            return None

        async def seen_exact(self, *a):
            return False

        async def seen_content(self, *a):
            return False

    class RE:
        def generate_reply(self, **kwargs):
            return "fallback-reply"

    class QE:
        async def get_quote(self, req):
            raise AssertionError("should not be called")

    class Guard:
        def check_content(self, *_a, **_k):
            return True, []

    monkeypatch.setattr("src.lite.__main__.get_compliance_guard", lambda: Guard())
    ws = WS()
    with pytest.raises(asyncio.CancelledError):
        await _process_loop(ws, Dedup(), RE(), QE())
    assert ws.sent and ws.sent[0][2] == "fallback-reply"

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import time
import types
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.error_handler import BrowserError
from src.lite.msgpack import MessagePackDecoder as LiteMsgPackDecoder
from src.lite.msgpack import decrypt_payload
from src.lite.ws_client import LiteWsClient
from src.lite.xianyu_api import XianyuApiClient
from src.modules.messages.service import MessagesService
from src.modules.messages.ws_live import GoofishWsTransport, MessagePackDecoder, decode_sync_payload
from src.modules.quote.cache import QuoteCacheEntry
from src.modules.quote.cost_table import CostRecord, CostTableRepository, normalize_courier_name
from src.modules.quote.engine import AutoQuoteEngine
from src.modules.quote.models import QuoteRequest, QuoteResult
from src.modules.quote.providers import (
    ApiCostMarkupQuoteProvider,
    CostTableMarkupQuoteProvider,
    QuoteProviderError,
    RemoteQuoteProvider,
    RuleTableQuoteProvider,
    _derive_volume_weight_kg,
    _normalize_markup_rules,
    _parse_cost_api_response,
    _to_float,
)
from src.modules.quote.route import normalize_request_route


@pytest.fixture
def ws_enabled(monkeypatch):
    monkeypatch.setattr("src.modules.messages.ws_live.websockets", object())


def _make_messages_service(monkeypatch, tmp_path, *, transport="auto", controller=None) -> MessagesService:
    cfg = SimpleNamespace(
        browser={"delay": {"min": 0.0, "max": 0.0}},
        accounts=[{"enabled": True, "cookie": "unb=10001; _m_h5_tk=tk_1"}],
    )

    def get_section(name, default=None):
        if name == "messages":
            return {
                "transport": transport,
                "ws": {},
                "quote": {"preferred_couriers": ["圆通", "中通"]},
                "strict_format_reply_enabled": False,
                "context_memory_enabled": True,
                "send_confirm_delay_seconds": [0.0, 0.0],
            }
        if name == "quote":
            return {}
        if name == "content":
            return {"templates": {"path": str(tmp_path)}}
        return default or {}

    cfg.get_section = get_section

    class Guard:
        def evaluate_content(self, _text):
            return {"blocked": False}

    monkeypatch.setattr("src.modules.messages.service.get_config", lambda: cfg)
    monkeypatch.setattr("src.modules.messages.service.get_compliance_guard", lambda: Guard())
    return MessagesService(controller=controller, config={})


def _quote_result(provider="rule_table") -> QuoteResult:
    return QuoteResult(provider=provider, base_fee=1.0, surcharges={}, total_fee=1.0, eta_minutes=60)


@pytest.mark.asyncio
async def test_ws_live_extra_helper_paths(ws_enabled, monkeypatch):
    assert abs(MessagePackDecoder(b"\xca?\x80\x00\x00").decode() - 1.0) < 1e-6
    assert MessagePackDecoder(b"\xcf\x00\x00\x00\x00\x00\x00\x00\x02").decode() == 2
    assert decode_sync_payload("@@@") is None

    payload = {"ok": True}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
    assert decode_sync_payload(encoded) == payload

    t = GoofishWsTransport(
        cookie_text="unb=10001; _m_h5_tk=tk_1; cookie2=c2",
        config={"cookie_watch_interval_seconds": 0.1},
        cookie_supplier=lambda: "unb=10001; _m_h5_tk=tk_1; cookie2=c2",
    )

    t.cookie_supplier = lambda: (_ for _ in ()).throw(RuntimeError("bad supplier"))
    assert t._maybe_reload_cookie(reason="err") is False

    t.cookie_supplier = lambda: ""
    assert t._maybe_reload_cookie(reason="empty") is False

    t.cookie_supplier = lambda: "unb=10001; _m_h5_tk=tk_1; cookie2=c2"
    assert t._maybe_reload_cookie(reason="same") is False

    t.cookie_supplier = lambda: "invalid_cookie"
    assert t._maybe_reload_cookie(reason="invalid") is False

    async def fake_sleep(_delay):
        return None

    monkeypatch.setattr("src.modules.messages.ws_live.asyncio.sleep", fake_sleep)
    assert await t._wait_for_cookie_update(timeout_seconds=1.0) is False

    t._stop_event.set()
    assert await t._wait_for_cookie_update_forever() is False


@pytest.mark.asyncio
async def test_ws_live_queue_wait_and_send_edge_paths(ws_enabled, monkeypatch):
    t = GoofishWsTransport(
        cookie_text="unb=10001; _m_h5_tk=tk_1; cookie2=c2",
        config={"queue_wait_seconds": 0.01, "message_expire_ms": 1},
    )

    await t._send_heartbeat()
    await t._ack_packet({"headers": "not-dict"})

    t._seen_event = {"old": time.time() - 9999}
    t._cleanup_seen()
    assert "old" not in t._seen_event

    await t._push_event({"chat_id": "", "sender_user_id": "u", "text": "x", "create_time": int(time.time() * 1000)})
    t.my_user_id = "mine"
    await t._push_event({"chat_id": "c", "sender_user_id": "mine", "text": "x", "create_time": int(time.time() * 1000)})
    await t._push_event({"chat_id": "c", "sender_user_id": "u", "text": "x", "create_time": 1})
    assert t._queue.qsize() == 0

    await t._handle_sync({"body": {"syncPushPackage": {"data": ["bad", {"x": 1}, {"data": ""}]}}})
    assert t._queue.qsize() == 0

    running = asyncio.create_task(asyncio.sleep(1))
    t._run_task = running
    await t.start()
    assert t._run_task is running
    running.cancel()

    fut = asyncio.get_running_loop().create_future()
    fut.set_exception(RuntimeError("boom"))
    t._run_task = fut
    await t.stop()
    assert t._run_task is None
    assert t.is_ready() is False

    async def timeout_wait_for(coro, timeout):
        if hasattr(coro, "close"):
            coro.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr("src.modules.messages.ws_live.asyncio.wait_for", timeout_wait_for)
    t._ready.clear()
    assert await t.get_unread_sessions(limit=2) == []

    t._ready.set()
    assert await t.get_unread_sessions(limit=2) == []

    now_ms = int(time.time() * 1000)
    await t._queue.put({"session_id": "s1", "sender_user_id": "u1", "text": "a", "create_time": now_ms})
    await t._queue.put({"session_id": "s1", "sender_user_id": "u2", "text": "b", "create_time": now_ms})
    rows = await t.get_unread_sessions(limit=5)
    assert len(rows) == 1

    t._ws = None
    t._ready.set()
    t.start = AsyncMock(return_value=None)
    assert await t.send_text("s1", "hi") is False

    class BadWS:
        async def send(self, _x):
            raise RuntimeError("send failed")

    t._session_peer["s1"] = "u1"
    t._ws = BadWS()
    assert await t.send_text("s1", "hi") is False


@pytest.mark.asyncio
async def test_messages_service_ws_quote_and_send_branches(monkeypatch, tmp_path):
    controller = SimpleNamespace(
        new_page=AsyncMock(return_value="p"),
        close_page=AsyncMock(return_value=True),
        execute_script=AsyncMock(return_value=True),
        navigate=AsyncMock(return_value=True),
    )
    s = _make_messages_service(monkeypatch, tmp_path, transport="auto", controller=controller)

    s.transport_mode = "ws"
    s._ws_unavailable_reason = "blocked"
    with pytest.raises(BrowserError):
        await s._ensure_ws_transport()

    s.transport_mode = "auto"
    assert await s._ensure_ws_transport() is None

    class WsNotReady:
        async def get_unread_sessions(self, limit=20):
            return []

        def is_ready(self):
            return False

    s._ensure_ws_transport = AsyncMock(return_value=WsNotReady())
    s._get_unread_sessions_dom = AsyncMock(return_value=[{"session_id": "dom"}])
    assert await s.get_unread_sessions(limit=2) == [{"session_id": "dom"}]

    class WsReady:
        async def get_unread_sessions(self, limit=20):
            return []

        def is_ready(self):
            return True

    s._ensure_ws_transport = AsyncMock(return_value=WsReady())
    assert await s.get_unread_sessions(limit=2) == [{"session_id": "dom"}]

    s.controller = None
    assert await s.get_unread_sessions(limit=2) == []
    s.controller = controller

    s.context_memory_ttl_seconds = 0.0
    s._quote_context_memory = {"sid": {"updated_at": 0.0, "origin": "杭州"}}
    s._prune_quote_context_memory()
    assert s._quote_context_memory == {}

    assert s._extract_single_location("abc123") is None
    assert "按格式发送" in s._build_available_couriers_hint({})

    s.courier_lock_template = "{bad-template"
    reply, matched = s._build_courier_lock_reply(
        {"courier_choice": "圆通", "last_quote_rows": [{"courier": "圆通", "total_fee": "bad", "eta_days": "2天"}]}
    )
    assert matched is True and "已为你锁定" in reply

    assert s._sanitize_reply("vx 加我") == s.safe_fallback_reply

    s.compliance_guard = SimpleNamespace(evaluate_content=lambda _text: {"blocked": True})
    assert s._sanitize_reply("正常文本") == s.safe_fallback_reply

    s.compliance_guard = SimpleNamespace(evaluate_content=lambda _text: {"blocked": False})
    s._get_quote_context = lambda sid: {"courier_choice": "圆通"}
    s._has_quote_context = lambda sid: True
    reply1, meta1 = await s._generate_reply_with_quote("我要下单", session_id="sid")
    assert meta1["quote_need_info"] is True and meta1["is_quote"] is True

    s.strict_format_reply_enabled = True
    s._is_quote_request = lambda _t: False
    s._is_standard_format_trigger = lambda _t: False
    s._build_quote_request_with_context = lambda *_a, **_k: (None, ["origin"], {}, False)
    _, meta2 = await s._generate_reply_with_quote("hello", session_id="sid")
    assert meta2["format_enforced"] is True and meta2["format_enforced_reason"] == "strict_mode"

    s.strict_format_reply_enabled = False
    s._is_quote_request = lambda _t: True
    s._build_quote_request_with_context = lambda *_a, **_k: (None, [], {}, False)
    _, meta3 = await s._generate_reply_with_quote("询价", session_id="sid")
    assert meta3["quote_missing_fields"] == ["origin", "destination", "weight"]

    req = QuoteRequest(origin="杭州", destination="上海", weight=1.0)
    s._build_quote_request_with_context = lambda *_a, **_k: (req, [], {}, False)

    async def raise_provider_error(_req):
        raise QuoteProviderError("x")

    s.quote_engine = SimpleNamespace(get_quote=raise_provider_error)
    _, meta4 = await s._generate_reply_with_quote("询价", session_id="sid")
    assert meta4["quote_success"] is False and meta4["quote_fallback"] is True

    s.reply_engine = SimpleNamespace(generate_reply=lambda **_k: "vx")
    assert s.generate_reply("hi") == s.safe_fallback_reply

    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr("src.modules.messages.service.asyncio.sleep", fake_sleep)
    assert await s._send_reply_on_page("p", "sid", "hello") is True
    assert sleeps

    class WsTransport:
        async def send_text(self, session_id, text):
            return False

    s.transport_mode = "ws"
    s._ensure_ws_transport = AsyncMock(return_value=WsTransport())
    assert await s.reply_to_session("sid", "text") is False

    s.transport_mode = "auto"
    s.controller = None
    s._ensure_ws_transport = AsyncMock(return_value=None)
    with pytest.raises(BrowserError):
        await s.reply_to_session("sid", "text")

    s2 = _make_messages_service(monkeypatch, tmp_path, transport="auto", controller=controller)
    s2.fast_reply_enabled = True
    s2.reuse_message_page = True
    s2.get_unread_sessions = AsyncMock(return_value=[{"session_id": "sid", "last_message": "m", "peer_name": "p"}])
    s2.process_session = AsyncMock(
        return_value={
            "within_target": True,
            "is_quote": True,
            "quote_need_info": False,
            "quote_success": True,
            "quote_fallback": True,
            "quote_latency_ms": 5,
            "sent": True,
        }
    )
    report = await s2.auto_reply_unread(limit=1, dry_run=False)
    assert report["success"] == 1
    controller.close_page.assert_awaited()


@pytest.mark.asyncio
async def test_quote_engine_and_provider_extra_branches(monkeypatch, tmp_path):
    req = QuoteRequest(origin="杭州", destination="上海", weight=1.0, service_level="standard")

    engine = AutoQuoteEngine({"mode": "rule_only", "analytics_log_enabled": False, "ttl_seconds": 1, "max_stale_seconds": 10})
    key = normalize_request_route(req).cache_key()
    engine.cache._entries[key] = QuoteCacheEntry(value=_quote_result(), expires_at=time.time() - 2, stale_until=time.time() + 30)

    def fake_create_task(coro):
        coro.close()
        fut = asyncio.get_running_loop().create_future()
        fut.set_result(None)
        return fut

    original_create_task = asyncio.create_task
    monkeypatch.setattr("src.modules.quote.engine.asyncio.create_task", fake_create_task)
    stale = await engine.get_quote(req)
    assert stale.stale is True
    monkeypatch.setattr("src.modules.quote.engine.asyncio.create_task", original_create_task)

    engine2 = AutoQuoteEngine({"mode": "cost_table_plus_markup", "analytics_log_enabled": False})
    monkeypatch.setattr(engine2.cost_table_provider, "get_quote", AsyncMock(side_effect=RuntimeError("table")))
    monkeypatch.setattr(engine2.rule_provider, "get_quote", AsyncMock(return_value=_quote_result()))
    fallback = await engine2._quote_with_fallback(req)
    assert fallback.fallback_used is True and fallback.explain["fallback_source"] == "rule"

    engine3 = AutoQuoteEngine({"mode": "remote_only", "analytics_log_enabled": False})
    engine3._circuit_open_until = time.time() + 20
    with pytest.raises(QuoteProviderError):
        await engine3._quote_with_fallback(req)

    engine4 = AutoQuoteEngine({"mode": "remote_then_rule", "analytics_log_enabled": False})
    monkeypatch.setattr(engine4.remote_provider, "get_quote", AsyncMock(return_value=_quote_result("remote_mock")))
    remote_ok = await engine4._quote_with_fallback(req)
    assert remote_ok.provider == "remote_mock"

    engine5 = AutoQuoteEngine({"mode": "api_cost_plus_markup", "analytics_log_enabled": False, "api_fallback_to_table_parallel": False})
    monkeypatch.setattr(engine5.api_cost_provider, "get_quote", AsyncMock(side_effect=RuntimeError("api")))
    monkeypatch.setattr(engine5.cost_table_provider, "get_quote", AsyncMock(side_effect=RuntimeError("table")))
    monkeypatch.setattr(engine5.rule_provider, "get_quote", AsyncMock(return_value=_quote_result()))
    api_fallback = await engine5._quote_api_cost_plus_markup(req)
    assert api_fallback.explain["fallback_source"] == "rule"

    engine6 = AutoQuoteEngine({"mode": "api_cost_plus_markup", "analytics_log_enabled": False, "api_prefer_max_wait_seconds": 1.0})
    monkeypatch.setattr(engine6.api_cost_provider, "get_quote", AsyncMock(return_value=_quote_result("api")))
    monkeypatch.setattr(engine6.cost_table_provider, "get_quote", AsyncMock(return_value=_quote_result("table")))
    api_first = await engine6._quote_api_cost_plus_markup(req)
    assert api_first.provider == "api"

    engine7 = AutoQuoteEngine({"mode": "api_cost_plus_markup", "analytics_log_enabled": False, "api_prefer_max_wait_seconds": 0.01})

    async def slow_api(*_a, **_k):
        try:
            await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            raise RuntimeError("cancelled")
        return _quote_result("api")

    monkeypatch.setattr(engine7.api_cost_provider, "get_quote", slow_api)
    monkeypatch.setattr(engine7.cost_table_provider, "get_quote", AsyncMock(return_value=_quote_result("table")))
    table_first = await engine7._quote_api_cost_plus_markup(req)
    assert table_first.provider == "table" and table_first.explain["fallback_source"] == "cost_table"

    engine8 = AutoQuoteEngine({"mode": "rule_only", "analytics_log_enabled": False})
    monkeypatch.setattr(engine8, "_quote_with_fallback", AsyncMock(return_value=_quote_result()))
    await engine8._refresh_cache_in_background(req, "k")
    assert engine8.cache.get("k")[0] is not None

    health = await engine8.health_check()
    assert set(health) == {"rule_provider", "cost_table_provider", "api_cost_provider", "remote_provider"}

    assert AutoQuoteEngine._classify_failure(RuntimeError("x")) == "provider_error"

    csv_path = tmp_path / "cost.csv"
    csv_path.write_text("快递公司,始发地,目的地,首重1KG,续重1KG\n圆通,浙江,广东,3,2\n", encoding="utf-8")
    repo = CostTableRepository(table_dir=csv_path, include_patterns=["*.csv"])
    assert repo._collect_files() == [csv_path]
    assert normalize_courier_name("") == ""
    assert repo._cell_text([], 0) == ""
    assert repo._cell_float([], 0) is None

    header_map = repo._resolve_header_map(["快递公司", "始发地", "目的地", "首重1KG", "续重1KG"])
    assert header_map["first_cost"] == 3 and header_map["extra_cost"] == 4

    assert repo._rows_to_records([["only", "header"]], source_file="x", source_sheet="y") == []

    xlsx = tmp_path / "empty.xlsx"
    with zipfile.ZipFile(xlsx, "w") as zf:
        zf.writestr("noop.txt", "x")
    with zipfile.ZipFile(xlsx) as zf:
        assert repo._read_sheet_paths(zf) == []
        assert repo._read_shared_strings(zf) == []

    xml = '<c xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" t="s"><v>99</v></c>'
    from xml.etree import ElementTree as ET

    assert repo._read_cell_value(ET.fromstring(xml), ["a"]) == ""

    rule = RuleTableQuoteProvider()
    remote_quote = await rule.get_quote(QuoteRequest(origin="新疆", destination="西藏", weight=1.0, service_level="standard"))
    assert "remote" in remote_quote.surcharges

    provider = CostTableMarkupQuoteProvider(table_dir=str(tmp_path), include_patterns=["none.csv"])
    with pytest.raises(QuoteProviderError):
        await provider.get_quote(req)

    monkeypatch.setattr(provider.repo, "get_stats", lambda max_files=10: {"total_records": 0})
    assert await provider.health_check() is False

    captured = {}

    class Resp:
        status_code = 200

        def json(self):
            return {"data": {"provider": "p", "total_cost": 10, "billable_weight": 2}}

    class Client:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, _url, json=None, headers=None):
            captured["headers"] = headers
            return Resp()

    monkeypatch.setattr("httpx.AsyncClient", Client)
    monkeypatch.setenv("QUOTE_KEY", "abc")
    api_provider = ApiCostMarkupQuoteProvider(api_url="http://x", api_key_env="QUOTE_KEY")
    api_quote = await api_provider.get_quote(req)
    assert api_quote.provider == "p"
    assert captured["headers"]["X-API-Key"] == "abc"
    assert await api_provider.health_check() is True

    remote_provider = RemoteQuoteProvider(enabled=True, simulated_latency_ms=0, failure_rate=0.0)
    urgent_quote = await remote_provider.get_quote(QuoteRequest(origin="A", destination="B", weight=1.0, service_level="urgent"))
    assert urgent_quote.base_fee == 16.0
    assert await remote_provider.health_check() is True

    assert "default" in _normalize_markup_rules({"x": "bad"})
    assert _to_float(" ") is None
    assert _parse_cost_api_response(["bad"])["provider"] is None
    assert _derive_volume_weight_kg(100.0, 3.0, 0) == 3.0


@pytest.mark.asyncio
async def test_lite_msgpack_ws_and_api_extra_paths(monkeypatch):
    assert LiteMsgPackDecoder(b"\xff").decode() == -1

    padded = "eyJvayI6dHJ1ZX0"
    assert decrypt_payload(padded) == {"ok": True}

    payload = base64.urlsafe_b64encode(json.dumps({"x": 1}).encode()).decode().rstrip("=")
    assert decrypt_payload(payload) == {"x": 1}

    async def token_provider():
        return "tok"

    client = LiteWsClient(ws_url="ws://x", cookie="k=v", device_id="d", my_user_id="mine", token_provider=token_provider)
    await client._send_heartbeat()
    await client._ack_packet({"headers": "x"})

    assert client._extract_event({"1": {"2": "cid@goofish", "10": {"text": "", "senderId": "u"}}}) is None
    assert client._extract_event({"1": {"2": "cid@goofish", "5": "bad", "10": {"text": "x", "senderId": "u"}}}) is not None
    assert (
        client._extract_event(
            {"1": {"2": "cid@goofish", "5": 1, "10": {"text": "x", "senderId": "u"}}}
        )
        is None
    )

    await client._handle_sync({"body": {"syncPushPackage": {"data": "bad"}}})

    client._event_queue = asyncio.Queue(maxsize=1)
    await client._event_queue.put({"chat_id": "old"})

    monkeypatch.setattr(
        "src.lite.ws_client.decrypt_payload",
        lambda _raw: {"1": {"2": "new@goofish", "5": int(time.time() * 1000), "10": {"text": "hi", "senderId": "u"}}},
    )
    await client._handle_sync({"body": {"syncPushPackage": {"data": [{"data": "raw"}]}}})
    got = await client.next_event()
    assert got["chat_id"] == "new"

    with pytest.raises(ValueError):
        await XianyuApiClient("unb=u1").get_token(max_attempts=1)

    c = XianyuApiClient("unb=u1; _m_h5_tk=tk_1")

    class FailClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            return SimpleNamespace(json=lambda: {"ret": ["FAIL"]})

    monkeypatch.setattr("src.lite.xianyu_api.httpx.AsyncClient", lambda **kwargs: FailClient())
    with pytest.raises(ValueError):
        await c.get_token(max_attempts=1)

    class RetryClient:
        def __init__(self):
            self.calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            self.calls += 1
            raise RuntimeError("net")

    monkeypatch.setattr("src.lite.xianyu_api.httpx.AsyncClient", lambda **kwargs: RetryClient())
    with pytest.raises(RuntimeError):
        await c.get_item_info("1", max_attempts=1)

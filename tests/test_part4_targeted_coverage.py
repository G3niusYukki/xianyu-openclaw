from __future__ import annotations

import argparse
import json
from unittest.mock import AsyncMock

import pytest

from src.core.error_handler import BrowserError
from src.core import browser_client as bc
from src.modules.messages.ws_live import GoofishWsTransport
from src.modules.quote.models import QuoteRequest
from src.modules.quote.route import contains_match, normalize_location, normalize_request_route, route_candidates
from src.modules.quote.setup import QuoteSetupService


class _Resp:
    def __init__(self, status_code=200, payload=None, text="", content=b"", is_success=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.content = content
        self.is_success = (200 <= status_code < 300) if is_success is None else is_success

    def json(self):
        return self._payload


class _Client:
    def __init__(self):
        self.get = AsyncMock(return_value=_Resp(200, {}))
        self.post = AsyncMock(return_value=_Resp(200, {}))
        self.delete = AsyncMock(return_value=_Resp(200, {}))
        self.aclose = AsyncMock()


@pytest.mark.asyncio
async def test_browser_helpers_and_runtime_resolution(monkeypatch):
    c = bc.BrowserClient({"delay_min": 0.0, "delay_max": 0.0})
    c._client = _Client()
    c._focus_tab = AsyncMock()

    c._act = AsyncMock(return_value={"text": "hello", "value": "v"})
    assert await c.type_text("p", "#i", "abc", clear=False) is True
    assert await c.double_click("p", "#i") is True
    assert await c.select_option("p", "#i", "1") is True
    assert await c.check("p", "#i", checked=False) is True
    assert await c.get_text("p", "#i") == "hello"
    assert await c.get_value("p", "#i") == "v"
    assert await c.scroll_to_element("p", "#i") is True
    assert await c.go_back("p") is True
    assert await c.go_forward("p") is True
    assert await c.handle_dialog("p", accept=False, text="x") is True

    c._act = AsyncMock(side_effect=RuntimeError("x"))
    assert await c.type_text("p", "#i", "abc") is False
    assert await c.double_click("p", "#i") is False
    assert await c.select_option("p", "#i", "1") is False
    assert await c.check("p", "#i", checked=True) is False
    assert await c.get_text("p", "#i") is None
    assert await c.get_value("p", "#i") is None
    assert await c.scroll_to_element("p", "#i") is False
    assert await c.go_back("p") is False
    assert await c.go_forward("p") is False

    c.execute_script = AsyncMock(return_value=True)
    assert await c.scroll_to_top("p") is True
    assert await c.scroll_to_bottom("p") is True
    assert await c.scroll_by("p", 1, 2) is True

    monkeypatch.setenv("OPENCLAW_RUNTIME", "lite")
    assert bc._resolve_runtime({}) == "lite"
    monkeypatch.setenv("OPENCLAW_RUNTIME", "pro")
    assert bc._resolve_runtime({}) == "pro"


@pytest.mark.asyncio
async def test_probe_gateway_available(monkeypatch):
    class CM:
        def __init__(self, code):
            self.code = code

        async def __aenter__(self):
            code = self.code

            class C:
                async def get(self, *_a, **_k):
                    return _Resp(status_code=code)

            return C()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr("src.core.browser_client.httpx.AsyncClient", lambda **_: CM(401))
    assert await bc._probe_gateway_available({}) is True

    monkeypatch.setattr("src.core.browser_client.httpx.AsyncClient", lambda **_: CM(500))
    assert await bc._probe_gateway_available({}) is False


@pytest.mark.asyncio
async def test_ws_fetch_token_paths(monkeypatch):
    monkeypatch.setattr("src.modules.messages.ws_live.websockets", object())
    t = GoofishWsTransport(cookie_text="unb=10001; _m_h5_tk=token_a_123", config={"token_max_attempts": 1})
    t._preflight_has_login = AsyncMock(return_value=True)
    t._maybe_reload_cookie = lambda **_k: False

    t._token = "cached"
    import time as _t
    t._token_ts = _t.time()
    assert await t._fetch_token() == "cached"

    t._token = ""
    t.cookies = {"unb": "10001"}
    with pytest.raises(BrowserError):
        await t._fetch_token()


@pytest.mark.asyncio
async def test_ws_send_reg_ack_and_queue_behaviors(monkeypatch):
    monkeypatch.setattr("src.modules.messages.ws_live.websockets", object())
    t = GoofishWsTransport(cookie_text="unb=10001; _m_h5_tk=token_a_123", config={"max_queue_size": 1})
    import asyncio
    t._queue = asyncio.Queue(maxsize=1)

    class WS:
        def __init__(self):
            self.sent = []

        async def send(self, payload):
            self.sent.append(json.loads(payload))

    ws = WS()
    t._ws = ws
    t._fetch_token = AsyncMock(return_value="tok")
    monkeypatch.setattr("src.modules.messages.ws_live.asyncio.sleep", AsyncMock())

    await t._send_reg()
    assert ws.sent[0]["lwp"] == "/reg"
    assert ws.sent[1]["lwp"].endswith("ackDiff")

    await t._ack_packet({"headers": {"mid": "m1", "sid": "s", "app-key": "a", "ua": "u", "dt": "j"}})
    assert ws.sent[-1]["headers"]["mid"] == "m1"

    now_ms = 2000000000000
    monkeypatch.setattr("src.modules.messages.ws_live.time.time", lambda: now_ms / 1000)
    t.my_user_id = "me"
    await t._push_event({"chat_id": "c0", "sender_user_id": "u0", "text": "a", "create_time": now_ms})
    await t._push_event({"chat_id": "c1", "sender_user_id": "u1", "text": "b", "create_time": now_ms})
    assert t._queue.qsize() == 1


def test_quote_route_and_setup(tmp_path):
    assert normalize_location("北京") == "北京市"
    req = QuoteRequest(origin="北京", destination="上海", weight=1.2, courier="AUTO", service_level="STANDARD")
    out = normalize_request_route(req)
    assert out.origin == "北京市"
    assert out.courier == "auto"
    assert contains_match("北京市", "上海市", "北京", "上海") is True
    assert isinstance(route_candidates("北京", "上海"), list)

    cfg = tmp_path / "config.yaml"
    svc = QuoteSetupService(str(cfg))
    with pytest.raises(ValueError):
        svc.apply(mode="bad", origin_city=None, pricing_profile="normal", cost_table_dir=str(tmp_path))
    with pytest.raises(ValueError):
        svc.apply(mode="rule_only", origin_city=None, pricing_profile="x", cost_table_dir=str(tmp_path))

    (tmp_path / "tables").mkdir()
    (tmp_path / "tables" / "a.csv").write_text("x", encoding="utf-8")
    r = svc.apply(
        mode="api_cost_plus_markup",
        origin_city="杭州",
        pricing_profile="member",
        cost_table_dir=str(tmp_path / "tables"),
        api_cost_url="https://api.example",
        cost_api_key_env="KEY",
    )
    assert r["success"] is True
    assert r["quote"]["cost_api_url"] == "https://api.example"


@pytest.mark.asyncio
async def test_cli_messages_list_branch(monkeypatch):
    from src import cli

    out = []
    monkeypatch.setattr("src.cli._json_out", lambda d: out.append(d))

    class S:
        async def get_unread_sessions(self, limit=20):
            return []

        async def close(self):
            return None

    monkeypatch.setattr("src.cli._messages_requires_browser_runtime", lambda: False)
    monkeypatch.setattr("src.modules.messages.service.MessagesService", lambda controller=None: S())
    await cli.cmd_messages(argparse.Namespace(action="list-unread", limit=1))
    assert out[-1]["total"] == 0

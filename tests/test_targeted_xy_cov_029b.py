from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.error_handler import BrowserError
from src.modules.messages.service import MessagesService
from src.modules.messages.ws_live import GoofishWsTransport


@pytest.fixture
def msg_service(monkeypatch, tmp_path):
    cfg = SimpleNamespace(browser={"delay": {"min": 0.0, "max": 0.0}}, accounts=[])

    def get_section(name, default=None):
        if name == "messages":
            return {"transport": "auto", "ws": {}, "quote": {}}
        if name == "quote":
            return {}
        if name == "content":
            return {"templates": {"path": str(tmp_path)}}
        return default or {}

    cfg.get_section = get_section
    monkeypatch.setattr("src.modules.messages.service.get_config", lambda: cfg)

    class Guard:
        def evaluate_content(self, _text):
            return {"blocked": False}

    monkeypatch.setattr("src.modules.messages.service.get_compliance_guard", lambda: Guard())

    return MessagesService(controller=None, config={})


def test_extract_chat_event_hits_inner_pick_non_dict(monkeypatch):
    monkeypatch.setattr("src.modules.messages.ws_live.websockets", object())
    from src.modules.messages.ws_live import extract_chat_event

    assert extract_chat_event({"1": "scalar-body"}) is None


@pytest.mark.asyncio
async def test_fetch_token_non_success_break_and_default_fail(monkeypatch):
    monkeypatch.setattr("src.modules.messages.ws_live.websockets", object())
    t = GoofishWsTransport(cookie_text="unb=10001; _m_h5_tk=seed_1; cookie2=a", config={"token_max_attempts": 1})

    async def _preflight_ok():
        return True

    t._preflight_has_login = _preflight_ok

    class _CM:
        async def __aenter__(self):
            class _C:
                async def post(self, *_a, **_k):
                    class _R:
                        def json(self):
                            return {"ret": ["FAIL_BIZ::plain"]}

                    return _R()

            return _C()

        async def __aexit__(self, *_a):
            return False

    monkeypatch.setattr("src.modules.messages.ws_live.httpx.AsyncClient", lambda **_k: _CM())

    with pytest.raises(BrowserError, match="Token API failed"):
        await t._fetch_token()

    monkeypatch.setattr("src.modules.messages.ws_live.max", lambda *_a, **_k: 0, raising=False)
    with pytest.raises(BrowserError, match="Token fetch failed"):
        await t._fetch_token()


@pytest.mark.asyncio
async def test_service_remaining_missing_branches(msg_service, monkeypatch):
    s = msg_service

    # first call (for _should_use_ws_transport) returns non-empty; second call (actual cookie fetch) returns empty
    cookie_calls = iter(["unb=1; _m_h5_tk=t_1", ""])
    monkeypatch.setattr(s, "_resolve_ws_cookie", lambda: next(cookie_calls))
    assert await s._ensure_ws_transport() is None
    assert "WebSocket transport requires XIANYU_COOKIE_1" in s._ws_unavailable_reason

    class Ctl:
        async def new_page(self):
            return "p1"

        async def navigate(self, _pid, _url):
            return None

        async def execute_script(self, _pid, _script):
            return [{"session_id": "dom-1"}]

        async def close_page(self, _pid):
            return None

    s.controller = Ctl()
    monkeypatch.setattr("src.modules.messages.service.asyncio.sleep", AsyncMock())
    dom_rows = await s._get_unread_sessions_dom(limit=1)
    assert dom_rows == [{"session_id": "dom-1"}]

    class WsReadyRaises:
        async def get_unread_sessions(self, limit=20):
            assert limit == 2
            return []

        def is_ready(self):
            raise RuntimeError("boom")

    s.transport_mode = "ws"
    s._ensure_ws_transport = AsyncMock(return_value=WsReadyRaises())
    assert await s.get_unread_sessions(limit=2) == []

    class WsNotReady:
        async def get_unread_sessions(self, limit=20):
            return []

        def is_ready(self):
            return False

    s._ensure_ws_transport = AsyncMock(return_value=WsNotReady())
    assert await s.get_unread_sessions(limit=2) == []

    class WsReady:
        async def get_unread_sessions(self, limit=20):
            return []

        def is_ready(self):
            return True

    s._ensure_ws_transport = AsyncMock(return_value=WsReady())
    assert await s.get_unread_sessions(limit=2) == []

    assert s._is_quote_request("") is False

    s._quote_context_memory["sid"] = {
        "updated_at": 10**10,
        "origin": "杭州",
        "destination": "上海",
        "weight": 1.0,
        "volume": 123.0,
    }
    req, missing, fields, hit = s._build_quote_request_with_context("", session_id="sid")
    assert req is not None
    assert missing == []
    assert fields["volume"] == 123.0
    assert hit is True

    assert s._is_quote_followup_candidate("选顺丰!") is True
    assert s._is_quote_followup_candidate("ok,付款") is True

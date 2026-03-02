from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.error_handler import BrowserError
from src.modules.messages.service import MessagesService
from src.modules.quote.models import QuoteRequest


@pytest.fixture
def cfg(monkeypatch, tmp_path):
    c = SimpleNamespace(
        browser={"delay": {"min": 0.0, "max": 0.0}},
        accounts=[{"enabled": False, "cookie": ""}, {"enabled": True, "cookie": "acc_cookie=v"}],
    )

    def get_section(name, default=None):
        if name == "messages":
            return {"transport": "auto", "ws": {}, "quote": {"preferred_couriers": ["A", "A", "B"]}}
        if name == "quote":
            return {}
        if name == "content":
            return {"templates": {"path": str(tmp_path)}}
        return default or {}

    c.get_section = get_section
    monkeypatch.setattr("src.modules.messages.service.get_config", lambda: c)
    monkeypatch.setattr("src.modules.messages.service.get_compliance_guard", lambda: object())


def _make_service(cfg):
    return MessagesService(controller=None, config={})


def test_resolve_ws_cookie_from_accounts(cfg, monkeypatch):
    monkeypatch.delenv("XIANYU_COOKIE_1", raising=False)
    s = _make_service(cfg)
    assert s._resolve_ws_cookie() == "acc_cookie=v"


@pytest.mark.asyncio
async def test_ensure_ws_transport_paths(cfg, monkeypatch):
    s = _make_service(cfg)
    s.transport_mode = "ws"

    monkeypatch.setattr(s, "_resolve_ws_cookie", lambda: "")
    with pytest.raises(BrowserError):
        await s._ensure_ws_transport()

    s.transport_mode = "auto"
    got = await s._ensure_ws_transport()
    assert got is None

    class T:
        async def start(self):
            return None

        async def stop(self):
            return None

    monkeypatch.setattr(s, "_resolve_ws_cookie", lambda: "unb=1; _m_h5_tk=t_1")
    monkeypatch.setattr("src.modules.messages.ws_live.GoofishWsTransport", lambda **_k: T())
    t = await s._ensure_ws_transport()
    assert t is not None
    await s.close()


def test_quote_candidate_couriers_and_compose(cfg):
    s = _make_service(cfg)

    class Row:
        def __init__(self, courier):
            self.courier = courier

    class Repo:
        def find_candidates(self, **_kwargs):
            return [Row("B"), Row("C"), Row("C")]

    s.quote_engine = SimpleNamespace(cost_table_provider=SimpleNamespace(repo=Repo()))
    req = QuoteRequest(origin="杭州", destination="上海", weight=1.0)
    couriers = s._resolve_quote_candidate_couriers(req)
    assert couriers[:3] == ["A", "B", "C"]

    q1 = SimpleNamespace(total_fee=10.0, eta_minutes=1440, explain={"matched_origin": "杭州", "matched_destination": "上海"})
    q2 = SimpleNamespace(total_fee=12.0, eta_minutes=2880, explain={})
    text = s._compose_multi_courier_quote_reply([("圆通", q1), ("中通", q2)])
    assert "可选快递报价" in text and "圆通" in text


@pytest.mark.asyncio
async def test_quote_all_couriers_and_random_range(cfg):
    s = _make_service(cfg)
    s._resolve_quote_candidate_couriers = lambda _r: ["A", "B"]

    async def get_quote(req):
        if req.courier == "A":
            return SimpleNamespace(total_fee=8.5)
        raise RuntimeError("bad")

    s.quote_engine = SimpleNamespace(get_quote=get_quote)

    rows = await s._quote_all_couriers(QuoteRequest(origin="a", destination="b", weight=1.0))
    assert len(rows) == 1
    assert rows[0][0] == "A"

    assert MessagesService._random_range((5, 1), (0.1, 0.2)) >= 1


@pytest.mark.asyncio
async def test_close_ws_transport_swallow_exception(cfg):
    s = _make_service(cfg)

    class T:
        async def stop(self):
            raise RuntimeError("x")

    s._ws_transport = T()
    await s.close()
    assert s._ws_transport is None

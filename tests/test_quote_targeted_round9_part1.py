from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.modules.quote.cost_table import CostRecord, CostTableRepository, normalize_courier_name, normalize_location_name, region_of_location
from src.modules.quote.engine import AutoQuoteEngine
from src.modules.quote.models import QuoteRequest
from src.modules.quote.providers import (
    ApiCostMarkupQuoteProvider,
    QuoteProviderError,
    RemoteQuoteProvider,
    _derive_volume_weight_kg,
    _eta_by_service_level,
    _first_positive,
    _normalize_markup_rules,
    _parse_cost_api_response,
    _profile_markup,
    _requested_courier,
    _resolve_markup,
    _to_float,
)


def test_provider_helper_functions():
    assert _requested_courier("auto") is None
    rules = _normalize_markup_rules({"圆通快递": {"normal_first_add": 1.2}})
    assert "圆通" in rules
    assert _resolve_markup(rules, "圆通")["normal_first_add"] == 1.2
    assert _profile_markup(rules["default"], "member")[0] >= 0
    assert _eta_by_service_level("urgent") == 12 * 60
    assert _to_float("x") is None
    assert _first_positive(None, -1, 0, 2.5) == 2.5
    assert _derive_volume_weight_kg(12000, 0, 6000) == 2.0


@pytest.mark.asyncio
async def test_remote_provider_edges(monkeypatch):
    req = QuoteRequest(origin="A", destination="B", weight=1.0, service_level="standard")
    p = RemoteQuoteProvider(enabled=False)
    with pytest.raises(QuoteProviderError):
        await p.get_quote(req)

    p2 = RemoteQuoteProvider(enabled=True, simulated_latency_ms=500, failure_rate=0)
    with pytest.raises(QuoteProviderError):
        await p2.get_quote(req, timeout_ms=50)

    monkeypatch.setattr("random.random", lambda: 0.0)
    p3 = RemoteQuoteProvider(enabled=True, simulated_latency_ms=1, failure_rate=1.0)
    with pytest.raises(QuoteProviderError):
        await p3.get_quote(req, timeout_ms=100)


@pytest.mark.asyncio
async def test_api_provider_paths(monkeypatch):
    req = QuoteRequest(origin="杭州", destination="广州", weight=2.0, service_level="express", volume=6000)

    provider = ApiCostMarkupQuoteProvider(api_url="", api_key_env="")
    with pytest.raises(QuoteProviderError):
        await provider.get_quote(req)

    class Resp:
        def __init__(self, status_code=200, body=None, raise_json=False):
            self.status_code = status_code
            self._body = body or {}
            self._raise_json = raise_json

        def json(self):
            if self._raise_json:
                raise ValueError("bad")
            return self._body

    class Client:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def post(self, *_a, **_k):
            return Resp(status_code=500)

    monkeypatch.setattr("httpx.AsyncClient", Client)
    provider = ApiCostMarkupQuoteProvider(api_url="http://x", api_key_env="")
    with pytest.raises(QuoteProviderError):
        await provider.get_quote(req)

    class ClientBadJson(Client):
        async def post(self, *_a, **_k):
            return Resp(status_code=200, raise_json=True)

    monkeypatch.setattr("httpx.AsyncClient", ClientBadJson)
    with pytest.raises(QuoteProviderError):
        await provider.get_quote(req)

    class ClientMissing(Client):
        async def post(self, *_a, **_k):
            return Resp(status_code=200, body={"data": {"courier": "圆通"}})

    monkeypatch.setattr("httpx.AsyncClient", ClientMissing)
    with pytest.raises(QuoteProviderError):
        await provider.get_quote(req)

    class ClientOk(Client):
        async def post(self, *_a, **_k):
            return Resp(status_code=200, body={"data": {"provider": "p", "first_cost": 3, "extra_cost": 2, "billable_weight": 2.5}})

    monkeypatch.setattr("httpx.AsyncClient", ClientOk)
    r = await provider.get_quote(req)
    assert r.provider == "p"
    assert r.total_fee >= r.base_fee


@pytest.mark.asyncio
async def test_engine_internal_branches(monkeypatch):
    assert AutoQuoteEngine._normalize_mode("provider_only") == "remote_only"
    assert AutoQuoteEngine._normalize_mode("???") == "rule_only"
    assert AutoQuoteEngine._resolve_api_key_env_name({"cost_api_key": "${MY_KEY}"}) == "MY_KEY"
    assert AutoQuoteEngine._classify_failure(RuntimeError("temporary down")) == "transient"

    eng = AutoQuoteEngine({"enabled": False})
    with pytest.raises(QuoteProviderError):
        await eng.get_quote(QuoteRequest(origin="A", destination="B", weight=1, service_level="standard"))

    eng = AutoQuoteEngine({"mode": "rule_only", "analytics_log_enabled": True})

    class A:
        async def log_operation(self, **_kwargs):
            raise RuntimeError("log failed")

    eng._analytics = A()
    r = await eng.get_quote(QuoteRequest(origin="A", destination="B", weight=1, service_level="standard"))
    assert r.provider == "rule_table"


@pytest.mark.asyncio
async def test_engine_api_parallel_fallback_rule(monkeypatch):
    eng = AutoQuoteEngine({"mode": "api_cost_plus_markup", "analytics_log_enabled": False, "api_prefer_max_wait_seconds": 0.01})
    req = QuoteRequest(origin="浙江", destination="广东", weight=1.0, service_level="standard")

    async def slow_api(*_a, **_k):
        await asyncio.sleep(0.05)
        raise QuoteProviderError("api down")

    async def bad_table(*_a, **_k):
        raise QuoteProviderError("table down")

    async def rule(*_a, **_k):
        from src.modules.quote.models import QuoteResult

        return QuoteResult(provider="rule_table", base_fee=1, total_fee=1, eta_minutes=1)

    monkeypatch.setattr(eng.api_cost_provider, "get_quote", slow_api)
    monkeypatch.setattr(eng.cost_table_provider, "get_quote", bad_table)
    monkeypatch.setattr(eng.rule_provider, "get_quote", rule)

    result = await eng._quote_api_cost_plus_markup(req)
    assert result.provider == "rule_table"
    assert result.fallback_used is True


@pytest.mark.asyncio
async def test_engine_remote_only_and_fallback_fail(monkeypatch):
    req = QuoteRequest(origin="A", destination="B", weight=1.0, service_level="standard")
    eng = AutoQuoteEngine({"mode": "remote_only", "retry_times": 1, "circuit_fail_threshold": 1, "analytics_log_enabled": False})

    async def bad_remote(*_a, **_k):
        raise RuntimeError("broken")

    monkeypatch.setattr(eng.remote_provider, "get_quote", bad_remote)
    with pytest.raises(QuoteProviderError):
        await eng._quote_with_fallback(req)

    eng2 = AutoQuoteEngine({"mode": "remote_then_rule", "analytics_log_enabled": False})

    async def bad_rule(*_a, **_k):
        raise RuntimeError("rule broken")

    monkeypatch.setattr(eng2.remote_provider, "get_quote", bad_remote)
    monkeypatch.setattr(eng2.rule_provider, "get_quote", bad_rule)
    with pytest.raises(QuoteProviderError):
        await eng2._quote_with_fallback(req)


def test_cost_table_more_branches(tmp_path: Path):
    assert normalize_courier_name("京东物流") == "京东"
    assert normalize_location_name(" 上海市 ") == "上海"
    assert region_of_location("杭州市") == "浙江"

    repo = CostTableRepository(table_dir=tmp_path, include_patterns=["*.csv"])
    assert repo.get_stats()["total_records"] == 0

    csv_path = tmp_path / "x.csv"
    csv_path.write_text("快递公司,始发地,目的地,首重1KG,续重1KG,抛比\n圆通快递,浙江省,广东省,3.0,2.0,6000\n", encoding="utf-8")
    stats = repo.get_stats()
    assert stats["total_records"] == 1

    rows = repo.find_candidates("杭州", "广州", courier="圆通", limit=1)
    assert rows and rows[0].throw_ratio == 6000

    assert repo._to_float("¥12.5") == 12.5
    assert repo._to_float("bad") is None
    assert repo._excel_col_to_index("AA") == 27

    # direct coverage helpers
    from xml.etree import ElementTree as ET
    assert repo._read_cell_value(ET.fromstring('<c xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" t="inlineStr"><is><t>x</t></is></c>'), []) == "x"
    parsed = _parse_cost_api_response([{"carrier": "圆通", "base_price": 2, "continue_cost": 1}])
    assert parsed["courier"] == "圆通"

    ranked = repo._rank_by_origin_similarity([CostRecord(courier="圆通", origin="浙江", destination="广东", first_cost=3, extra_cost=2)], "杭州")
    assert ranked

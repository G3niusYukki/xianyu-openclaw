"""自动报价引擎测试。"""

from pathlib import Path

import pytest

from src.modules.quote.engine import AutoQuoteEngine
from src.modules.quote.models import QuoteRequest


@pytest.mark.asyncio
async def test_quote_engine_rule_mode_returns_explainable_result() -> None:
    engine = AutoQuoteEngine({"mode": "rule_only", "analytics_log_enabled": False})
    req = QuoteRequest(origin="上海", destination="北京", weight=2.0, service_level="express")

    result = await engine.get_quote(req)

    assert result.provider == "rule_table"
    assert result.total_fee >= result.base_fee
    assert "service_level" in result.explain


@pytest.mark.asyncio
async def test_quote_engine_remote_failure_falls_back_to_rule_provider() -> None:
    engine = AutoQuoteEngine(
        {
            "mode": "hybrid",
            "analytics_log_enabled": False,
            "providers": {"remote": {"enabled": True, "simulated_latency_ms": 1, "failure_rate": 1.0}},
        }
    )
    req = QuoteRequest(origin="杭州", destination="深圳", weight=1.3, service_level="standard")

    result = await engine.get_quote(req)

    assert result.provider == "rule_table"
    assert result.fallback_used is True


@pytest.mark.asyncio
async def test_quote_engine_cache_hit() -> None:
    engine = AutoQuoteEngine({"mode": "rule_only", "analytics_log_enabled": False, "ttl_seconds": 600})
    req = QuoteRequest(origin="南京", destination="苏州", weight=1.0, service_level="standard")

    first = await engine.get_quote(req)
    second = await engine.get_quote(req)

    assert first.cache_hit is False
    assert second.cache_hit is True


@pytest.mark.asyncio
async def test_quote_engine_route_normalization_uses_same_cache_key() -> None:
    engine = AutoQuoteEngine({"mode": "rule_only", "analytics_log_enabled": False, "ttl_seconds": 600})
    req1 = QuoteRequest(origin="北京", destination="上海", weight=1.0, service_level="standard")
    req2 = QuoteRequest(origin="北京市", destination="上海市", weight=1.02, service_level="standard")

    first = await engine.get_quote(req1)
    second = await engine.get_quote(req2)

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.explain["normalized_origin"] == "北京市"
    assert second.explain["normalized_destination"] == "上海市"


@pytest.mark.asyncio
async def test_quote_engine_circuit_breaker_opens_after_failures() -> None:
    engine = AutoQuoteEngine(
        {
            "mode": "hybrid",
            "analytics_log_enabled": False,
            "retry_times": 1,
            "circuit_fail_threshold": 1,
            "circuit_open_seconds": 120,
            "providers": {"remote": {"enabled": True, "simulated_latency_ms": 1, "failure_rate": 1.0}},
        }
    )
    req = QuoteRequest(origin="杭州", destination="深圳", weight=1.3, service_level="standard")
    req2 = QuoteRequest(origin="杭州", destination="深圳", weight=2.2, service_level="standard")

    first = await engine.get_quote(req)
    second = await engine.get_quote(req2)

    assert first.fallback_used is True
    assert first.snapshot is not None
    assert first.snapshot.fallback_reason in {"Remote provider temporary failure", "Remote provider timeout"}
    assert second.fallback_used is True
    assert second.snapshot is not None
    assert "circuit_open" in second.snapshot.fallback_reason or "remote_circuit_open" in second.snapshot.fallback_reason
    assert second.snapshot.provider_chain == ["hot_cache_miss", "cost_table"]


def _prepare_cost_table(tmp_path: Path) -> Path:
    csv_path = tmp_path / "cost.csv"
    csv_path.write_text(
        "快递公司,始发地,目的地,首重,续重\n圆通,浙江,广东,3.00,2.00\n",
        encoding="utf-8",
    )
    return csv_path


@pytest.mark.asyncio
async def test_quote_engine_cost_table_plus_markup_mode_works(tmp_path: Path) -> None:
    _prepare_cost_table(tmp_path)
    engine = AutoQuoteEngine(
        {
            "mode": "cost_table_plus_markup",
            "analytics_log_enabled": False,
            "cost_table_dir": str(tmp_path),
            "cost_table_patterns": ["*.csv"],
            "pricing_profile": "normal",
            "markup_rules": {
                "default": {
                    "normal_first_add": 1.0,
                    "member_first_add": 0.2,
                    "normal_extra_add": 0.5,
                    "member_extra_add": 0.1,
                }
            },
        }
    )
    req = QuoteRequest(origin="浙江", destination="广东", weight=2.0, service_level="standard", courier="圆通")

    result = await engine.get_quote(req)

    assert result.provider == "cost_table_markup"
    assert result.base_fee == 4.0
    assert result.total_fee == 6.5
    assert result.fallback_used is False


@pytest.mark.asyncio
async def test_quote_engine_api_cost_plus_markup_fallbacks_to_table(tmp_path: Path) -> None:
    _prepare_cost_table(tmp_path)
    engine = AutoQuoteEngine(
        {
            "mode": "api_cost_plus_markup",
            "analytics_log_enabled": False,
            "timeout_ms": 180,
            "api_fallback_to_table_parallel": False,
            "cost_api_url": "http://127.0.0.1:9/quote",
            "cost_table_dir": str(tmp_path),
            "cost_table_patterns": ["*.csv"],
            "pricing_profile": "normal",
            "markup_rules": {"default": {"normal_first_add": 0.5, "normal_extra_add": 0.3}},
        }
    )
    req = QuoteRequest(origin="浙江", destination="广东", weight=2.0, service_level="express", courier="圆通")

    result = await engine.get_quote(req)

    assert result.provider == "cost_table_markup"
    assert result.fallback_used is True
    assert result.explain.get("fallback_source") == "cost_table"

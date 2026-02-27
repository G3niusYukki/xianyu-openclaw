"""自动报价引擎测试。"""

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

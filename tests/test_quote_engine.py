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
async def test_quote_engine_rule_mode_uses_max_of_actual_and_volume_weight(tmp_path) -> None:
    engine = AutoQuoteEngine(
        {
            "mode": "rule_only",
            "analytics_log_enabled": False,
            "volume_divisor_default": 6000,
            "cost_table_dir": str(tmp_path),
            "cost_table_patterns": ["*.csv"],
        }
    )
    req = QuoteRequest(origin="上海", destination="上海", weight=1.0, volume=18000.0, service_level="standard")

    result = await engine.get_quote(req)

    assert result.provider == "rule_table"
    assert result.surcharges.get("weight") == 4.0
    assert result.total_fee == 12.0
    assert result.explain.get("actual_weight_kg") == 1.0
    assert result.explain.get("volume_weight_kg") == 3.0
    assert result.explain.get("billing_weight_kg") == 3.0
    assert result.explain.get("volume_divisor") == 6000.0


@pytest.mark.asyncio
async def test_quote_engine_rule_mode_prefers_throw_ratio_from_cost_table(tmp_path) -> None:
    csv_path = tmp_path / "rule_throw.csv"
    csv_path.write_text(
        "快递公司,始发地,目的地,首重,续重,抛比\n圆通,上海,上海,3.00,2.00,12000\n",
        encoding="utf-8",
    )
    engine = AutoQuoteEngine(
        {
            "mode": "rule_only",
            "analytics_log_enabled": False,
            "volume_divisor_default": 6000,
            "cost_table_dir": str(tmp_path),
            "cost_table_patterns": ["*.csv"],
        }
    )
    req = QuoteRequest(origin="上海", destination="上海", weight=1.0, volume=18000.0, courier="圆通")

    result = await engine.get_quote(req)

    assert result.provider == "rule_table"
    assert result.surcharges.get("weight") == 1.0
    assert result.total_fee == 9.0
    assert result.explain.get("volume_weight_kg") == 1.5
    assert result.explain.get("billing_weight_kg") == 1.5
    assert result.explain.get("volume_divisor") == 12000.0


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
    assert first.explain["failure_class"] in {"transient", "provider_error"}
    assert second.fallback_used is True
    assert second.explain["fallback_reason"] == "remote_circuit_open"
    assert second.explain["failure_class"] == "unavailable"


def _prepare_cost_table(tmp_path: Path) -> Path:
    csv_path = tmp_path / "cost.csv"
    csv_path.write_text(
        "快递公司,始发地,目的地,首重,续重\n圆通,浙江,广东,3.00,2.00\n",
        encoding="utf-8",
    )
    return csv_path


def _prepare_cost_table_with_throw_ratio(tmp_path: Path) -> Path:
    csv_path = tmp_path / "cost_throw.csv"
    csv_path.write_text(
        "快递公司,始发地,目的地,首重,续重,抛比\n圆通,浙江,广东,3.00,2.00,6000\n",
        encoding="utf-8",
    )
    return csv_path


@pytest.mark.asyncio
async def test_quote_engine_cost_table_plus_markup_mode_works(tmp_path) -> None:
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
async def test_quote_engine_cost_table_uses_volume_weight_when_higher(tmp_path) -> None:
    _prepare_cost_table_with_throw_ratio(tmp_path)
    engine = AutoQuoteEngine(
        {
            "mode": "cost_table_plus_markup",
            "analytics_log_enabled": False,
            "cost_table_dir": str(tmp_path),
            "cost_table_patterns": ["*.csv"],
            "pricing_profile": "normal",
            "markup_rules": {"default": {"normal_first_add": 0.0, "normal_extra_add": 0.0}},
            "volume_divisor_default": 6000,
        }
    )
    req = QuoteRequest(
        origin="浙江",
        destination="广东",
        weight=1.0,
        volume=12000.0,
        service_level="standard",
        courier="圆通",
    )

    result = await engine.get_quote(req)

    assert result.provider == "cost_table_markup"
    assert result.total_fee == 5.0
    assert result.explain.get("billing_weight_kg") == 2.0
    assert result.fallback_used is False


@pytest.mark.asyncio
async def test_quote_engine_cost_table_city_to_province_route_fallback(tmp_path) -> None:
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
                    "normal_first_add": 0.5,
                    "member_first_add": 0.2,
                    "normal_extra_add": 0.3,
                    "member_extra_add": 0.1,
                }
            },
        }
    )
    req = QuoteRequest(origin="杭州", destination="广州", weight=2.0, service_level="standard", courier="圆通")

    result = await engine.get_quote(req)

    assert result.provider == "cost_table_markup"
    assert result.fallback_used is False
    assert result.explain.get("matched_origin") == "浙江"
    assert result.explain.get("matched_destination") == "广东"


@pytest.mark.asyncio
async def test_quote_engine_api_cost_plus_markup_fallbacks_to_table(tmp_path) -> None:
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

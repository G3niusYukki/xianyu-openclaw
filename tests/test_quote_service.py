"""自动报价与双阶段回复测试。"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.modules.messages.service import MessagesService
from src.modules.quote.cost_table import CostRecord
from src.modules.quote.service import QuoteService


def test_quote_service_parse_complete_request() -> None:
    service = QuoteService(config={"origin_city": "杭州"})
    parsed = service.parse_quote_request("寄到上海 2kg 加急，麻烦报个价")

    assert parsed.is_quote_intent is True
    assert parsed.request.destination_city == "上海"
    assert parsed.request.weight_kg == 2.0
    assert parsed.request.urgency is True
    assert parsed.missing_fields == []


def test_quote_service_parse_missing_fields() -> None:
    service = QuoteService(config={"origin_city": "杭州"})
    parsed = service.parse_quote_request("快递报价怎么收")

    assert parsed.is_quote_intent is True
    assert "destination_city" in parsed.missing_fields
    assert "weight_kg" in parsed.missing_fields
    first_reply = service.build_first_reply(parsed)
    assert "请补充" in first_reply


def test_quote_service_parse_route_and_courier_profile() -> None:
    service = QuoteService(config={"origin_city": "杭州", "pricing_profile": "normal"})
    parsed = service.parse_quote_request("从安徽寄到上海 圆通 2kg 会员报价")

    assert parsed.request.origin_city == "安徽"
    assert parsed.request.destination_city == "上海"
    assert parsed.request.courier == "圆通"
    assert parsed.request.profile == "member"


@pytest.mark.asyncio
async def test_quote_service_compute_rule_quote() -> None:
    service = QuoteService(
        config={
            "mode": "rule_only",
            "origin_city": "杭州",
            "first_weight_kg": 1.0,
            "first_price": 8.0,
            "extra_per_kg": 2.0,
            "service_fee": 1.0,
            "inter_city_extra": 2.0,
            "eta_same_city_minutes": 60,
            "eta_inter_city_minutes": 240,
        }
    )

    parsed = service.parse_quote_request("寄到上海 2.3kg，报价")
    quote, source = await service.compute_quote(parsed)

    assert quote is not None
    assert source == "rule"
    assert quote.total_fee > 0
    assert quote.provider == "rule_engine"


@pytest.mark.asyncio
async def test_quote_service_compute_cost_table_plus_markup(tmp_path: Path) -> None:
    cost_file = tmp_path / "cost.csv"
    cost_file.write_text(
        "快递公司,始发地,目的地,首重,续重,抛比\n"
        "圆通快递,安徽,上海,3.49,1.60,8000\n"
        "韵达快递,安徽,上海,3.20,2.80,8000\n",
        encoding="utf-8",
    )
    service = QuoteService(
        config={
            "mode": "cost_table_plus_markup",
            "origin_city": "安徽",
            "pricing_profile": "normal",
            "cost_table_dir": str(tmp_path),
            "cost_table_patterns": ["*.csv"],
            "service_fee": 1.0,
            "first_weight_kg": 1.0,
            "markup_rules": {
                "default": {"normal_first_add": 0.5, "normal_extra_add": 0.3},
                "圆通": {"normal_first_add": 0.56, "normal_extra_add": 0.5},
            },
        }
    )

    parsed = service.parse_quote_request("寄到上海 2kg 圆通 报价")
    quote, source = await service.compute_quote(parsed)

    assert quote is not None
    assert source == "cost_table"
    assert quote.courier == "圆通"
    assert quote.total_fee == pytest.approx(7.15, abs=0.01)


@pytest.mark.asyncio
async def test_quote_service_compute_api_cost_plus_markup_fallback_table(tmp_path: Path) -> None:
    cost_file = tmp_path / "cost.csv"
    cost_file.write_text(
        "快递公司,始发地,目的地,首重,续重\n"
        "圆通快递,安徽,上海,3.49,1.60\n",
        encoding="utf-8",
    )
    service = QuoteService(
        config={
            "mode": "api_cost_plus_markup",
            "origin_city": "安徽",
            "pricing_profile": "normal",
            "cost_table_dir": str(tmp_path),
            "cost_table_patterns": ["*.csv"],
            "cost_api_url": "https://example.com/cost",
            "service_fee": 1.0,
            "first_weight_kg": 1.0,
            "markup_rules": {
                "default": {"normal_first_add": 0.5, "normal_extra_add": 0.3},
                "圆通": {"normal_first_add": 0.56, "normal_extra_add": 0.5},
            },
        }
    )
    service._fetch_remote_cost_candidates = AsyncMock(return_value=[])

    parsed = service.parse_quote_request("寄到上海 2kg 圆通 报价")
    quote, source = await service.compute_quote(parsed)

    assert quote is not None
    assert source == "fallback_cost_table"
    assert quote.courier == "圆通"


@pytest.mark.asyncio
async def test_quote_service_compute_api_cost_plus_markup_success() -> None:
    service = QuoteService(
        config={
            "mode": "api_cost_plus_markup",
            "origin_city": "安徽",
            "pricing_profile": "normal",
            "cost_api_url": "https://example.com/cost",
            "service_fee": 1.0,
            "first_weight_kg": 1.0,
            "markup_rules": {
                "default": {"normal_first_add": 0.5, "normal_extra_add": 0.3},
                "韵达": {"normal_first_add": 0.87, "normal_extra_add": 0.4},
            },
        }
    )
    service._fetch_remote_cost_candidates = AsyncMock(
        return_value=[
            CostRecord(
                courier="韵达",
                origin="安徽",
                destination="上海",
                first_cost=3.2,
                extra_cost=2.8,
                throw_ratio=8000,
                source_file="api",
                source_sheet="cost",
            )
        ]
    )

    parsed = service.parse_quote_request("寄到上海 2kg 韵达 报价")
    quote, source = await service.compute_quote(parsed)

    assert quote is not None
    assert source == "api_cost_markup"
    assert quote.courier == "韵达"
    assert quote.total_fee == pytest.approx(8.27, abs=0.01)


@pytest.mark.asyncio
async def test_quote_service_compute_api_cost_plus_markup_fast_fallback_on_timeout(tmp_path: Path) -> None:
    cost_file = tmp_path / "cost.csv"
    cost_file.write_text(
        "快递公司,始发地,目的地,首重,续重\n"
        "圆通快递,安徽,上海,3.49,1.60\n",
        encoding="utf-8",
    )
    service = QuoteService(
        config={
            "mode": "api_cost_plus_markup",
            "origin_city": "安徽",
            "pricing_profile": "normal",
            "cost_table_dir": str(tmp_path),
            "cost_table_patterns": ["*.csv"],
            "cost_api_url": "https://example.com/cost",
            "service_fee": 1.0,
            "first_weight_kg": 1.0,
            "api_fallback_to_table_parallel": True,
            "api_prefer_max_wait_seconds": 0.1,
            "markup_rules": {
                "default": {"normal_first_add": 0.5, "normal_extra_add": 0.3},
                "圆通": {"normal_first_add": 0.56, "normal_extra_add": 0.5},
            },
        }
    )

    async def _slow_api(_: object) -> list[CostRecord]:
        await asyncio.sleep(0.2)
        return [
            CostRecord(
                courier="圆通",
                origin="安徽",
                destination="上海",
                first_cost=3.2,
                extra_cost=1.5,
                throw_ratio=8000,
                source_file="api",
                source_sheet="cost",
            )
        ]

    service._fetch_remote_cost_candidates = _slow_api  # type: ignore[method-assign]

    parsed = service.parse_quote_request("寄到上海 2kg 圆通 报价")
    quote, source = await service.compute_quote(parsed)

    assert quote is not None
    assert source == "fallback_cost_table_fast"
    assert quote.courier == "圆通"


@pytest.mark.asyncio
async def test_messages_auto_reply_quote_two_stage_dry_run(mock_controller) -> None:
    service = MessagesService(
        controller=mock_controller,
        config={
            "max_replies_per_run": 5,
            "followup_quote_enabled": True,
        },
    )
    service.get_unread_sessions = AsyncMock(
        return_value=[
            {
                "session_id": "s1",
                "peer_name": "买家A",
                "item_title": "同城快递",
                "last_message": "寄到上海 2kg 多少钱",
                "unread_count": 1,
            }
        ]
    )

    result = await service.auto_reply_unread(limit=10, dry_run=True)

    assert result["total"] == 1
    assert result["success"] == 1
    assert result["quote_followup_total"] == 1
    assert result["quote_followup_success"] == 1
    assert result["details"][0]["is_quote_intent"] is True
    assert "报价结果" in result["details"][0]["quote_reply"]


@pytest.mark.asyncio
async def test_messages_skip_quote_followup_when_first_reply_not_sent(mock_controller) -> None:
    service = MessagesService(
        controller=mock_controller,
        config={
            "max_replies_per_run": 5,
            "followup_quote_enabled": True,
            "outbound_compliance_enabled": True,
            "outbound_block_keywords": ["收到"],
        },
    )
    service.get_unread_sessions = AsyncMock(
        return_value=[
            {
                "session_id": "s1",
                "peer_name": "买家A",
                "item_title": "同城快递",
                "last_message": "寄到上海 2kg 多少钱",
                "unread_count": 1,
            }
        ]
    )

    result = await service.auto_reply_unread(limit=10, dry_run=False)

    assert result["total"] == 1
    assert result["success"] == 0
    assert result["quote_followup_total"] == 1
    assert result["quote_followup_success"] == 0
    assert result["details"][0]["first_reply_sent"] is False
    assert result["details"][0]["quote_source"] == "skipped_first_reply_failed"
    assert result["details"][0]["quote_sent"] is False

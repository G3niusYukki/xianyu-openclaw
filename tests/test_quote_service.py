"""自动报价与双阶段回复测试。"""

from unittest.mock import AsyncMock

import pytest

from src.modules.messages.service import MessagesService
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

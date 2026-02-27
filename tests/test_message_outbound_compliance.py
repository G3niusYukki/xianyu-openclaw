"""消息外发合规策略测试。"""

import pytest

from src.modules.messages.outbound_compliance import OutboundCompliancePolicy
from src.modules.messages.service import MessagesService


def test_outbound_compliance_policy_blocks_keyword() -> None:
    policy = OutboundCompliancePolicy(
        {
            "outbound_compliance_enabled": True,
            "outbound_block_keywords": ["微信"],
        }
    )
    allowed, reason = policy.evaluate("s1", "可以加我微信聊", {}, now_ts=1000.0)
    assert allowed is False
    assert reason == "blocked_keyword"


def test_outbound_compliance_policy_blocks_by_interval_and_rate() -> None:
    policy = OutboundCompliancePolicy(
        {
            "outbound_compliance_enabled": True,
            "outbound_min_interval_seconds": 10,
            "outbound_max_per_session_hour": 2,
            "outbound_max_per_session_day": 3,
        }
    )

    state_interval = {"compliance_last_sent_at": 995.0, "compliance_outbound_timestamps": [900.0]}
    allowed, reason = policy.evaluate("s1", "在的", state_interval, now_ts=1000.0)
    assert allowed is False
    assert reason == "min_interval_not_met"

    state_rate = {"compliance_last_sent_at": 900.0, "compliance_outbound_timestamps": [100.0, 800.0, 900.0]}
    allowed, reason = policy.evaluate("s1", "在的", state_rate, now_ts=1000.0)
    assert allowed is False
    assert reason == "max_per_session_hour_reached"


@pytest.mark.asyncio
async def test_messages_reply_blocked_by_outbound_compliance(mock_controller, tmp_path) -> None:
    service = MessagesService(
        controller=mock_controller,
        config={
            "followup_state_path": str(tmp_path / "followup_state.json"),
            "outbound_compliance_enabled": True,
            "outbound_block_keywords": ["微信"],
        },
    )

    sent = await service.reply_to_session("s-block", "支持微信联系")

    assert sent is False
    assert mock_controller.execute_script.await_count == 0
    state = service.followup_store.get("s-block")
    assert state.get("compliance_last_decision") == "blocked_keyword"


@pytest.mark.asyncio
async def test_messages_reply_records_outbound_compliance_state(mock_controller, tmp_path) -> None:
    service = MessagesService(
        controller=mock_controller,
        config={
            "followup_state_path": str(tmp_path / "followup_state.json"),
            "outbound_compliance_enabled": True,
            "outbound_block_keywords": ["微信"],
            "outbound_min_interval_seconds": 0,
        },
    )

    sent = await service.reply_to_session("s-ok", "您好，宝贝在的")

    assert sent is True
    state = service.followup_store.get("s-ok")
    assert state.get("compliance_last_decision") == "allowed"
    assert isinstance(state.get("compliance_outbound_timestamps"), list)
    assert len(state.get("compliance_outbound_timestamps", [])) == 1

"""订单履约确认流程测试。"""

from unittest.mock import AsyncMock

import pytest

from src.modules.messages.fulfillment import FulfillmentHelper
from src.modules.messages.service import MessagesService
from src.modules.messages.workflow_state import WorkflowStage


def test_fulfillment_helper_detects_order_intent() -> None:
    helper = FulfillmentHelper({"fulfillment_confirm_enabled": True})
    assert helper.is_order_intent("我已经拍下了，麻烦处理") is True
    assert helper.is_order_intent("快递怎么收费") is False


@pytest.mark.asyncio
async def test_messages_auto_reply_handles_order_intent_and_sets_ordered(mock_controller, tmp_path) -> None:
    service = MessagesService(
        controller=mock_controller,
        config={
            "reuse_message_page": False,
            "max_replies_per_run": 5,
            "followup_quote_enabled": True,
            "fulfillment_confirm_enabled": True,
            "followup_state_path": str(tmp_path / "followup_state.json"),
            "workflow_state_enabled": True,
            "workflow_state_path": str(tmp_path / "workflow_state.json"),
        },
    )

    service.get_unread_sessions = AsyncMock(
        return_value=[
            {
                "session_id": "o1",
                "peer_name": "买家A",
                "item_title": "快递代发",
                "last_message": "我已付款，麻烦安排",
                "unread_count": 1,
            }
        ]
    )
    service.reply_to_session = AsyncMock(return_value=True)

    result = await service.auto_reply_unread(limit=10, dry_run=False)

    assert result["success"] == 1
    detail = result["details"][0]
    assert detail["is_order_intent"] is True
    assert detail["is_quote_intent"] is False

    state = service.workflow_state_store.get("o1") if service.workflow_state_store else {}
    assert state.get("stage") == WorkflowStage.ORDERED


def test_messages_manual_transition_workflow_stage(tmp_path) -> None:
    service = MessagesService(
        controller=None,
        config={
            "workflow_state_enabled": True,
            "workflow_state_path": str(tmp_path / "workflow_state.json"),
        },
    )

    first = service.transition_workflow_stage("s_manual", "REPLIED")
    assert first["success"] is True

    invalid = service.transition_workflow_stage("s_manual", "NEW")
    assert invalid["success"] is False

    forced = service.transition_workflow_stage("s_manual", "NEW", force=True)
    assert forced["success"] is True

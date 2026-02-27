"""已读未回跟进流程测试。"""

import time
from unittest.mock import AsyncMock

import pytest

from src.modules.messages.followup_policy import ReadNoReplyFollowupPolicy
from src.modules.messages.service import MessagesService


def test_read_no_reply_policy_respects_timing_and_max_count() -> None:
    now = time.time()
    policy = ReadNoReplyFollowupPolicy(
        {
            "read_no_reply_followup_enabled": True,
            "read_no_reply_min_elapsed_seconds": 300,
            "read_no_reply_min_interval_seconds": 1800,
            "read_no_reply_max_per_session": 1,
        }
    )

    session = {"session_id": "s1", "last_message": "好的"}
    too_soon_state = {"first_reply_at": now - 120, "followup_sent_count": 0}
    allow, reason = policy.evaluate(session, too_soon_state, now_ts=now)
    assert allow is False
    assert reason == "too_soon_after_first_reply"

    maxed_state = {"first_reply_at": now - 3600, "followup_sent_count": 1}
    allow, reason = policy.evaluate(session, maxed_state, now_ts=now)
    assert allow is False
    assert reason == "max_followups_reached"


@pytest.mark.asyncio
async def test_messages_auto_followup_read_no_reply_dry_run(mock_controller, tmp_path) -> None:
    state_path = tmp_path / "followup_state.json"
    service = MessagesService(
        controller=mock_controller,
        config={
            "reuse_message_page": False,
            "read_no_reply_followup_enabled": True,
            "read_no_reply_min_elapsed_seconds": 30,
            "read_no_reply_min_interval_seconds": 30,
            "read_no_reply_max_per_session": 1,
            "followup_state_path": str(state_path),
        },
    )
    service.get_read_no_reply_sessions = AsyncMock(
        return_value=[
            {
                "session_id": "s1",
                "peer_name": "买家A",
                "item_title": "同城快递",
                "last_message": "已读",
                "unread_count": 0,
                "has_read_marker": True,
            }
        ]
    )
    service.reply_to_session = AsyncMock(return_value=True)
    service.followup_store.upsert("s1", {"first_reply_at": time.time() - 3600, "followup_sent_count": 0})

    result = await service.auto_followup_read_no_reply(limit=10, dry_run=True)

    assert result["enabled"] is True
    assert result["total"] == 1
    assert result["eligible"] == 1
    assert result["success"] == 1
    assert result["details"][0]["decision"] == "eligible"
    assert result["details"][0]["followup_text"]
    service.reply_to_session.assert_not_called()


@pytest.mark.asyncio
async def test_messages_auto_followup_read_no_reply_respects_max_per_session(mock_controller, tmp_path) -> None:
    state_path = tmp_path / "followup_state.json"
    service = MessagesService(
        controller=mock_controller,
        config={
            "reuse_message_page": False,
            "read_no_reply_followup_enabled": True,
            "read_no_reply_min_elapsed_seconds": 30,
            "read_no_reply_min_interval_seconds": 30,
            "read_no_reply_max_per_session": 1,
            "followup_state_path": str(state_path),
        },
    )
    service.get_read_no_reply_sessions = AsyncMock(
        return_value=[
            {
                "session_id": "s2",
                "peer_name": "买家B",
                "item_title": "跨省快递",
                "last_message": "看下",
                "unread_count": 0,
                "has_read_marker": True,
            }
        ]
    )
    service.reply_to_session = AsyncMock(return_value=True)
    service.followup_store.upsert("s2", {"first_reply_at": time.time() - 3600, "followup_sent_count": 1})

    result = await service.auto_followup_read_no_reply(limit=10, dry_run=False)

    assert result["enabled"] is True
    assert result["eligible"] == 0
    assert result["success"] == 0
    assert result["details"][0]["decision"] == "max_followups_reached"
    service.reply_to_session.assert_not_called()


@pytest.mark.asyncio
async def test_messages_auto_reply_unread_records_followup_state(mock_controller, tmp_path) -> None:
    state_path = tmp_path / "followup_state.json"
    service = MessagesService(
        controller=mock_controller,
        config={
            "reuse_message_page": False,
            "max_replies_per_run": 5,
            "followup_quote_enabled": False,
            "followup_state_path": str(state_path),
        },
    )
    service.get_unread_sessions = AsyncMock(
        return_value=[
            {
                "session_id": "s3",
                "peer_name": "买家C",
                "item_title": "江浙沪快递",
                "last_message": "在吗？",
                "unread_count": 1,
            }
        ]
    )
    service.reply_to_session = AsyncMock(return_value=True)

    result = await service.auto_reply_unread(limit=10, dry_run=False)
    state = service.followup_store.get("s3")

    assert result["success"] == 1
    assert state["last_inbound_message"] == "在吗？"
    assert float(state["first_reply_at"]) > 0
    assert int(state["followup_sent_count"]) == 0


@pytest.mark.asyncio
async def test_messages_auto_workflow_aggregates_stage_results(mock_controller) -> None:
    service = MessagesService(controller=mock_controller, config={"reuse_message_page": False})
    service.auto_reply_unread = AsyncMock(return_value={"success": 2, "quote_followup_success": 1})
    service.auto_followup_read_no_reply = AsyncMock(return_value={"success": 1})

    result = await service.auto_workflow(limit=20, dry_run=True)

    assert result["summary"]["replied_sessions"] == 2
    assert result["summary"]["quote_followup_success"] == 1
    assert result["summary"]["read_no_reply_followup_success"] == 1

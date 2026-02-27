"""会话状态机测试。"""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.modules.messages.service import MessagesService
from src.modules.messages.workflow_state import WorkflowStage, WorkflowStateStore


def test_workflow_state_store_valid_and_invalid_transition(tmp_path: Path) -> None:
    store = WorkflowStateStore(path=str(tmp_path / "workflow.json"), max_sessions=100)

    ok, reason, record = store.transition("s1", WorkflowStage.REPLIED, metadata={"event": "first_reply"})
    assert ok is True
    assert reason == "ok"
    assert record["stage"] == WorkflowStage.REPLIED

    ok, reason, _ = store.transition("s1", WorkflowStage.NEW)
    assert ok is False
    assert reason == "invalid_transition:REPLIED->NEW"


@pytest.mark.asyncio
async def test_messages_service_updates_workflow_stage_on_reply(mock_controller, tmp_path: Path) -> None:
    service = MessagesService(
        controller=mock_controller,
        config={
            "reuse_message_page": False,
            "max_replies_per_run": 5,
            "followup_quote_enabled": False,
            "followup_state_path": str(tmp_path / "followup_state.json"),
            "workflow_state_enabled": True,
            "workflow_state_path": str(tmp_path / "workflow_state.json"),
        },
    )
    service.get_unread_sessions = AsyncMock(
        return_value=[
            {
                "session_id": "s1",
                "peer_name": "买家A",
                "item_title": "快递服务",
                "last_message": "在吗",
                "unread_count": 1,
            }
        ]
    )
    service.reply_to_session = AsyncMock(return_value=True)

    result = await service.auto_reply_unread(limit=10, dry_run=False)

    assert result["success"] == 1
    state = service.workflow_state_store.get("s1") if service.workflow_state_store else {}
    assert state.get("stage") == WorkflowStage.REPLIED


@pytest.mark.asyncio
async def test_messages_service_updates_workflow_stage_on_followup(mock_controller, tmp_path: Path) -> None:
    service = MessagesService(
        controller=mock_controller,
        config={
            "reuse_message_page": False,
            "read_no_reply_followup_enabled": True,
            "read_no_reply_min_elapsed_seconds": 30,
            "read_no_reply_min_interval_seconds": 30,
            "read_no_reply_max_per_session": 1,
            "followup_state_path": str(tmp_path / "followup_state.json"),
            "workflow_state_enabled": True,
            "workflow_state_path": str(tmp_path / "workflow_state.json"),
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
    service.followup_store.upsert("s2", {"first_reply_at": 100000.0, "followup_sent_count": 0})
    if service.workflow_state_store is not None:
        service.workflow_state_store.transition("s2", WorkflowStage.REPLIED, force=True)

    await service.auto_followup_read_no_reply(limit=10, dry_run=False)

    state = service.workflow_state_store.get("s2") if service.workflow_state_store else {}
    assert state.get("stage") == WorkflowStage.FOLLOWED

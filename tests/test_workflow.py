"""消息 workflow 状态机与 worker 测试。"""

import pytest

from src.modules.messages.workflow import WorkflowState, WorkflowStore, WorkflowWorker


class DummyMessageService:
    def __init__(self, sessions, detail):
        self._sessions = sessions
        self._detail = detail

    async def get_unread_sessions(self, limit=20):
        return self._sessions[:limit]

    async def process_session(self, session, dry_run=False, page_id=None, actor=None):
        _ = (session, dry_run, page_id, actor)
        return self._detail


def test_workflow_state_machine_and_illegal_transition(temp_dir) -> None:
    store = WorkflowStore(db_path=str(temp_dir / "workflow.db"))
    store.ensure_session({"session_id": "s1", "last_message": "hello"})

    ok = store.transition_state("s1", WorkflowState.REPLIED, reason="test")
    reject = store.transition_state("s1", WorkflowState.NEW, reason="bad")

    assert ok is True
    assert reject is False

    transitions = store.get_transitions("s1")
    assert transitions[0]["status"] == "rejected"
    assert transitions[0]["error"] == "illegal_transition"


def test_workflow_job_dedupe_and_retry_to_dead(temp_dir) -> None:
    store = WorkflowStore(db_path=str(temp_dir / "workflow.db"))
    session = {"session_id": "s2", "last_message": "报价", "peer_name": "A", "item_title": "快递"}

    assert store.enqueue_job(session) is True
    assert store.enqueue_job(session) is False

    jobs = store.claim_jobs(limit=10, lease_seconds=1)
    assert len(jobs) == 1

    store.fail_job(jobs[0].id, error="boom", max_attempts=2, base_backoff_seconds=0)
    jobs_retry = store.claim_jobs(limit=10, lease_seconds=1)
    assert len(jobs_retry) == 1

    store.fail_job(jobs_retry[0].id, error="boom2", max_attempts=2, base_backoff_seconds=0)
    summary = store.get_workflow_summary()

    assert summary["jobs"].get("dead", 0) == 1


@pytest.mark.asyncio
async def test_workflow_worker_run_once_updates_state_and_sla(temp_dir) -> None:
    store = WorkflowStore(db_path=str(temp_dir / "workflow.db"))
    service = DummyMessageService(
        sessions=[
            {
                "session_id": "s3",
                "last_message": "从上海寄到杭州2kg多少钱",
                "peer_name": "B",
                "item_title": "快递",
            }
        ],
        detail={"sent": True, "is_quote": True, "quote_success": True, "quote_fallback": False},
    )
    worker = WorkflowWorker(message_service=service, store=store, config={"scan_limit": 5, "claim_limit": 5})

    result = await worker.run_once(dry_run=True)

    assert result["success"] == 1
    assert result["failed"] == 0
    assert result["workflow"]["states"].get("QUOTED", 0) == 1
    assert result["sla"]["quote_total"] == 1
    assert result["sla"]["quote_success_rate"] == 1.0


@pytest.mark.asyncio
async def test_workflow_worker_skips_manual_takeover(temp_dir) -> None:
    store = WorkflowStore(db_path=str(temp_dir / "workflow.db"))
    session = {"session_id": "s4", "last_message": "还在吗", "peer_name": "C", "item_title": "商品"}
    store.ensure_session(session)
    store.enqueue_job(session)
    store.set_manual_takeover("s4", True)

    service = DummyMessageService(
        sessions=[],
        detail={"sent": True, "is_quote": False, "quote_success": False, "quote_fallback": False},
    )
    worker = WorkflowWorker(message_service=service, store=store, config={"claim_limit": 5})

    result = await worker.run_once(dry_run=True)

    assert result["skipped_manual"] == 1
    assert result["success"] == 0

"""消息 workflow worker 测试。"""

import json
from pathlib import Path

import pytest

from src.modules.messages.worker import WorkflowWorker


class _SuccessService:
    def __init__(self) -> None:
        self.calls = 0

    async def auto_workflow(self, *, limit: int, dry_run: bool) -> dict:
        self.calls += 1
        return {
            "summary": {
                "replied_sessions": 1,
                "quote_followup_success": 1,
                "read_no_reply_followup_success": 0,
            },
            "limit": limit,
            "dry_run": dry_run,
        }


class _FailService:
    async def auto_workflow(self, *, limit: int, dry_run: bool) -> dict:
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_workflow_worker_runs_with_max_cycles_and_writes_state(tmp_path: Path) -> None:
    state_path = tmp_path / "worker_state.json"
    service = _SuccessService()
    worker = WorkflowWorker(
        messages_service=service,  # type: ignore[arg-type]
        config={
            "worker_interval_seconds": 0.01,
            "worker_jitter_seconds": 0,
            "worker_backoff_seconds": 0.01,
            "worker_max_backoff_seconds": 0.05,
            "worker_state_path": str(state_path),
        },
    )

    result = await worker.run(limit=10, dry_run=True, max_cycles=2, max_runtime_seconds=2)

    assert result["action"] == "run_worker"
    assert result["cycles_total"] == 2
    assert result["cycles_success"] == 2
    assert result["cycles_failed"] == 0
    assert service.calls == 2

    assert state_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == "stopped"
    assert state["cycles_total"] == 2


@pytest.mark.asyncio
async def test_workflow_worker_records_failures(tmp_path: Path) -> None:
    state_path = tmp_path / "worker_state_fail.json"
    worker = WorkflowWorker(
        messages_service=_FailService(),  # type: ignore[arg-type]
        config={
            "worker_interval_seconds": 0.01,
            "worker_jitter_seconds": 0,
            "worker_backoff_seconds": 0.01,
            "worker_max_backoff_seconds": 0.05,
            "worker_state_path": str(state_path),
        },
    )

    result = await worker.run(limit=10, dry_run=True, max_cycles=1, max_runtime_seconds=2)

    assert result["cycles_total"] == 1
    assert result["cycles_success"] == 0
    assert result["cycles_failed"] == 1
    assert result["last_error"] == "boom"

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == "stopped"
    assert state["last_error"] == "boom"

"""
消息工作流状态机
Message workflow state machine
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Lock
from typing import Any


class WorkflowStage:
    NEW = "NEW"
    REPLIED = "REPLIED"
    QUOTED = "QUOTED"
    FOLLOWED = "FOLLOWED"
    ORDERED = "ORDERED"
    CLOSED = "CLOSED"


VALID_TRANSITIONS: dict[str, set[str]] = {
    WorkflowStage.NEW: {WorkflowStage.REPLIED, WorkflowStage.CLOSED},
    WorkflowStage.REPLIED: {WorkflowStage.QUOTED, WorkflowStage.FOLLOWED, WorkflowStage.ORDERED, WorkflowStage.CLOSED},
    WorkflowStage.QUOTED: {WorkflowStage.FOLLOWED, WorkflowStage.ORDERED, WorkflowStage.CLOSED},
    WorkflowStage.FOLLOWED: {WorkflowStage.ORDERED, WorkflowStage.CLOSED},
    WorkflowStage.ORDERED: {WorkflowStage.CLOSED},
    WorkflowStage.CLOSED: set(),
}


class WorkflowStateStore:
    """会话状态持久化与迁移校验。"""

    def __init__(self, path: str = "data/message_workflow_state.json", max_sessions: int = 5000):
        self.path = Path(path)
        self.max_sessions = int(max_sessions) if int(max_sessions) > 0 else 5000
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def get(self, session_id: str) -> dict[str, Any]:
        sid = str(session_id).strip()
        if not sid:
            return {}
        with self._lock:
            data = self._load_all()
            record = data.get(sid, {})
            return dict(record) if isinstance(record, dict) else {}

    def transition(
        self,
        session_id: str,
        to_stage: str,
        *,
        metadata: dict[str, Any] | None = None,
        force: bool = False,
    ) -> tuple[bool, str, dict[str, Any]]:
        sid = str(session_id).strip()
        target = str(to_stage or "").strip().upper()
        if not sid:
            return False, "missing_session_id", {}
        if target not in VALID_TRANSITIONS:
            return False, "invalid_target_stage", {}

        with self._lock:
            data = self._load_all()
            now = time.time()
            record = data.get(sid, {})
            if not isinstance(record, dict):
                record = {}

            current = str(record.get("stage") or "").strip().upper() or WorkflowStage.NEW
            if current not in VALID_TRANSITIONS:
                current = WorkflowStage.NEW

            if target == current:
                record["updated_at"] = now
                data[sid] = record
                self._save_all(self._prune_if_needed(data))
                return True, "noop_same_stage", dict(record)

            allowed = target in VALID_TRANSITIONS.get(current, set())
            if not allowed and not force:
                return False, f"invalid_transition:{current}->{target}", dict(record)

            history = record.get("history", [])
            if not isinstance(history, list):
                history = []
            history.append(
                {
                    "ts": now,
                    "from": current,
                    "to": target,
                    "metadata": metadata or {},
                }
            )

            record["stage"] = target
            record["updated_at"] = now
            record.setdefault("created_at", now)
            record["history"] = history[-100:]
            if metadata:
                record["last_metadata"] = metadata

            data[sid] = record
            self._save_all(self._prune_if_needed(data))
            return True, "ok", dict(record)

    def _load_all(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            raw = self.path.read_text(encoding="utf-8").strip()
            if not raw:
                return {}
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_all(self, data: dict[str, Any]) -> None:
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.path)

    def _prune_if_needed(self, data: dict[str, Any]) -> dict[str, Any]:
        if len(data) <= self.max_sessions:
            return data
        ordered = sorted(
            data.items(),
            key=lambda item: self._safe_float(item[1].get("updated_at")) if isinstance(item[1], dict) else 0.0,
            reverse=True,
        )
        keep = ordered[: self.max_sessions]
        return {session_id: record for session_id, record in keep}

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

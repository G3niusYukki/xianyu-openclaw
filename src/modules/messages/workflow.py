"""会话工作流：状态机、持久化 Worker 与 SLA 监控。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from src.core.config import get_config
from src.core.logger import get_logger


class WorkflowState(str, Enum):
    """会话任务状态。"""

    NEW = "NEW"
    REPLIED = "REPLIED"
    QUOTED = "QUOTED"
    FOLLOWED = "FOLLOWED"
    ORDERED = "ORDERED"
    CLOSED = "CLOSED"
    MANUAL = "MANUAL"


class SessionStateMachine:
    """会话状态迁移规则。"""

    ALLOWED_TRANSITIONS: dict[WorkflowState, set[WorkflowState]] = {
        WorkflowState.NEW: {WorkflowState.REPLIED, WorkflowState.QUOTED, WorkflowState.MANUAL, WorkflowState.CLOSED},
        WorkflowState.REPLIED: {
            WorkflowState.QUOTED,
            WorkflowState.FOLLOWED,
            WorkflowState.ORDERED,
            WorkflowState.MANUAL,
            WorkflowState.CLOSED,
        },
        WorkflowState.QUOTED: {
            WorkflowState.FOLLOWED,
            WorkflowState.ORDERED,
            WorkflowState.MANUAL,
            WorkflowState.CLOSED,
        },
        WorkflowState.FOLLOWED: {WorkflowState.ORDERED, WorkflowState.MANUAL, WorkflowState.CLOSED},
        WorkflowState.ORDERED: {WorkflowState.CLOSED, WorkflowState.MANUAL},
        WorkflowState.CLOSED: set(),
        WorkflowState.MANUAL: {
            WorkflowState.REPLIED,
            WorkflowState.QUOTED,
            WorkflowState.FOLLOWED,
            WorkflowState.ORDERED,
            WorkflowState.CLOSED,
        },
    }

    @classmethod
    def can_transition(cls, from_state: WorkflowState, to_state: WorkflowState) -> bool:
        return to_state in cls.ALLOWED_TRANSITIONS.get(from_state, set()) or from_state == to_state


@dataclass
class WorkflowJob:
    id: int
    session_id: str
    stage: str
    payload: dict[str, Any]
    attempts: int


class WorkflowStore:
    """基于 SQLite 的工作流持久化层。"""

    def __init__(self, db_path: str | None = None):
        config = get_config()
        workflow_cfg = config.get_section("messages", {}).get("workflow", {})
        default_path = workflow_cfg.get("db_path", "data/workflow.db")
        self.db_path = Path(db_path or default_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = get_logger()
        self._init_schema()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _ts_after(seconds: int) -> str:
        return (datetime.now(UTC) + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS session_tasks (
                    session_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    manual_takeover INTEGER NOT NULL DEFAULT 0,
                    last_message_hash TEXT,
                    last_peer_name TEXT,
                    last_item_title TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS session_state_transitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    from_state TEXT,
                    to_state TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT,
                    metadata TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_transitions_session_time
                ON session_state_transitions(session_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS workflow_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_run_at TEXT NOT NULL,
                    lease_until TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_workflow_jobs_pending
                ON workflow_jobs(status, next_run_at);

                CREATE TABLE IF NOT EXISTS sla_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    latency_ms INTEGER NOT NULL,
                    quote_fallback INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_sla_events_time
                ON sla_events(created_at DESC);

                CREATE TABLE IF NOT EXISTS sla_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                );
                """
            )

    def ensure_session(self, session: dict[str, Any]) -> None:
        session_id = str(session.get("session_id", ""))
        if not session_id:
            return

        last_message = str(session.get("last_message", ""))
        message_hash = hashlib.sha1(last_message.encode("utf-8")).hexdigest()
        now = self._now()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO session_tasks(
                    session_id, state, manual_takeover, last_message_hash, last_peer_name,
                    last_item_title, created_at, updated_at
                )
                VALUES(?, ?, 0, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    last_message_hash=excluded.last_message_hash,
                    last_peer_name=excluded.last_peer_name,
                    last_item_title=excluded.last_item_title,
                    updated_at=excluded.updated_at
                """,
                (
                    session_id,
                    WorkflowState.NEW.value,
                    message_hash,
                    str(session.get("peer_name", "")),
                    str(session.get("item_title", "")),
                    now,
                    now,
                ),
            )

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM session_tasks WHERE session_id=?", (session_id,)).fetchone()
            return dict(row) if row else None

    def set_manual_takeover(self, session_id: str, enabled: bool) -> bool:
        now = self._now()
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM session_tasks WHERE session_id=?", (session_id,)).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO session_tasks(session_id, state, manual_takeover, created_at, updated_at)
                    VALUES (?, ?, 0, ?, ?)
                    """,
                    (session_id, WorkflowState.NEW.value, now, now),
                )

            cur = conn.execute(
                "UPDATE session_tasks SET manual_takeover=?, state=?, updated_at=? WHERE session_id=?",
                (
                    1 if enabled else 0,
                    WorkflowState.MANUAL.value if enabled else WorkflowState.REPLIED.value,
                    now,
                    session_id,
                ),
            )
            return cur.rowcount > 0

    def transition_state(
        self,
        session_id: str,
        to_state: WorkflowState,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        now = self._now()
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)

        with self._connect() as conn:
            row = conn.execute("SELECT state FROM session_tasks WHERE session_id=?", (session_id,)).fetchone()
            from_state = WorkflowState.NEW.value if row is None else str(row["state"])

            if row is None:
                conn.execute(
                    """
                    INSERT INTO session_tasks(session_id, state, manual_takeover, created_at, updated_at)
                    VALUES (?, ?, 0, ?, ?)
                    """,
                    (session_id, WorkflowState.NEW.value, now, now),
                )

            from_state_enum = WorkflowState(from_state)
            allowed = SessionStateMachine.can_transition(from_state_enum, to_state)

            if allowed:
                conn.execute(
                    "UPDATE session_tasks SET state=?, updated_at=?, last_error=NULL WHERE session_id=?",
                    (to_state.value, now, session_id),
                )

            conn.execute(
                """
                INSERT INTO session_state_transitions(
                    session_id, from_state, to_state, status, reason, metadata, error, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    from_state,
                    to_state.value,
                    "success" if allowed else "rejected",
                    reason,
                    metadata_json,
                    None if allowed else "illegal_transition",
                    now,
                ),
            )

            if not allowed:
                conn.execute(
                    "UPDATE session_tasks SET last_error=?, updated_at=? WHERE session_id=?",
                    (f"illegal_transition:{from_state}->{to_state.value}", now, session_id),
                )
                return False

            return True

    def force_state(
        self,
        session_id: str,
        to_state: WorkflowState,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """强制写入会话状态（用于人工介入纠偏场景）。"""

        now = self._now()
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)

        with self._connect() as conn:
            row = conn.execute("SELECT state FROM session_tasks WHERE session_id=?", (session_id,)).fetchone()
            from_state = WorkflowState.NEW.value if row is None else str(row["state"])

            if row is None:
                conn.execute(
                    """
                    INSERT INTO session_tasks(session_id, state, manual_takeover, created_at, updated_at)
                    VALUES (?, ?, 0, ?, ?)
                    """,
                    (session_id, WorkflowState.NEW.value, now, now),
                )

            conn.execute(
                "UPDATE session_tasks SET state=?, updated_at=?, last_error=NULL WHERE session_id=?",
                (to_state.value, now, session_id),
            )

            conn.execute(
                """
                INSERT INTO session_state_transitions(
                    session_id, from_state, to_state, status, reason, metadata, error, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    from_state,
                    to_state.value,
                    "forced",
                    reason,
                    metadata_json,
                    None,
                    now,
                ),
            )

            return True

    def enqueue_job(self, session: dict[str, Any], stage: str = "reply") -> bool:
        session_id = str(session.get("session_id", ""))
        if not session_id:
            return False

        last_message = str(session.get("last_message", ""))
        last_hash = hashlib.sha1(last_message.encode("utf-8")).hexdigest()[:16]
        dedupe_key = f"{session_id}:{last_hash}:{stage}"
        payload_json = json.dumps(session, ensure_ascii=False)
        now = self._now()

        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO workflow_jobs(
                    dedupe_key, session_id, stage, payload_json, status, attempts,
                    next_run_at, lease_until, last_error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'pending', 0, ?, NULL, NULL, ?, ?)
                """,
                (dedupe_key, session_id, stage, payload_json, now, now, now),
            )
            return cur.rowcount > 0

    def recover_expired_jobs(self) -> int:
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE workflow_jobs
                SET status='pending', lease_until=NULL, updated_at=?
                WHERE status='running' AND lease_until IS NOT NULL AND lease_until < ?
                """,
                (now, now),
            )
            return cur.rowcount

    def claim_jobs(self, limit: int, lease_seconds: int) -> list[WorkflowJob]:
        now = self._now()
        lease_until = self._ts_after(lease_seconds)

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM workflow_jobs
                WHERE status='pending' AND next_run_at <= ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (now, max(1, limit)),
            ).fetchall()

            jobs: list[WorkflowJob] = []
            for row in rows:
                conn.execute(
                    "UPDATE workflow_jobs SET status='running', lease_until=?, updated_at=? WHERE id=?",
                    (lease_until, now, int(row["id"])),
                )
                jobs.append(
                    WorkflowJob(
                        id=int(row["id"]),
                        session_id=str(row["session_id"]),
                        stage=str(row["stage"]),
                        payload=json.loads(str(row["payload_json"])),
                        attempts=int(row["attempts"]),
                    )
                )
            return jobs

    def complete_job(self, job_id: int) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE workflow_jobs SET status='done', lease_until=NULL, updated_at=? WHERE id=?",
                (now, job_id),
            )

    def fail_job(self, job_id: int, error: str, max_attempts: int, base_backoff_seconds: int) -> None:
        now = self._now()
        with self._connect() as conn:
            row = conn.execute("SELECT attempts FROM workflow_jobs WHERE id=?", (job_id,)).fetchone()
            attempts = int(row["attempts"]) + 1 if row else 1
            if attempts >= max_attempts:
                conn.execute(
                    """
                    UPDATE workflow_jobs
                    SET status='dead', attempts=?, lease_until=NULL, last_error=?, updated_at=?
                    WHERE id=?
                    """,
                    (attempts, error[:500], now, job_id),
                )
                return

            wait_seconds = int(base_backoff_seconds * (2 ** (attempts - 1)))
            conn.execute(
                """
                UPDATE workflow_jobs
                SET status='pending', attempts=?, next_run_at=?, lease_until=NULL, last_error=?, updated_at=?
                WHERE id=?
                """,
                (attempts, self._ts_after(wait_seconds), error[:500], now, job_id),
            )

    def record_sla_event(
        self,
        session_id: str,
        stage: str,
        outcome: str,
        latency_ms: int,
        quote_fallback: bool = False,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sla_events(session_id, stage, outcome, latency_ms, quote_fallback, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, stage, outcome, max(latency_ms, 0), 1 if quote_fallback else 0, self._now()),
            )

    def _percentile(self, samples: list[int], p: float) -> int:
        if not samples:
            return 0
        ordered = sorted(samples)
        index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * p)))
        return ordered[index]

    def get_sla_summary(self, window_minutes: int = 1440) -> dict[str, Any]:
        cutoff = (datetime.now(UTC) - timedelta(minutes=max(1, window_minutes))).strftime("%Y-%m-%dT%H:%M:%SZ")

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT stage, outcome, latency_ms, quote_fallback FROM sla_events WHERE created_at >= ?",
                (cutoff,),
            ).fetchall()

        first_reply_samples = [int(r["latency_ms"]) for r in rows if str(r["stage"]) in {"reply", "quote"}]
        quote_rows = [r for r in rows if str(r["stage"]) == "quote"]
        quote_success = sum(1 for r in quote_rows if str(r["outcome"]) == "success")
        quote_fallback = sum(1 for r in quote_rows if int(r["quote_fallback"]) == 1)

        return {
            "window_minutes": window_minutes,
            "event_count": len(rows),
            "first_reply_p50_ms": self._percentile(first_reply_samples, 0.5),
            "first_reply_p95_ms": self._percentile(first_reply_samples, 0.95),
            "quote_total": len(quote_rows),
            "quote_success_rate": round((quote_success / len(quote_rows)) if quote_rows else 0.0, 4),
            "quote_fallback_rate": round((quote_fallback / len(quote_rows)) if quote_rows else 0.0, 4),
        }

    def _raise_alert_once(self, alert_type: str, title: str, message: str, cooldown_minutes: int = 30) -> bool:
        now = self._now()
        cutoff = (datetime.now(UTC) - timedelta(minutes=max(1, cooldown_minutes))).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._connect() as conn:
            existed = conn.execute(
                """
                SELECT 1 FROM sla_alerts
                WHERE alert_type=? AND status='active' AND created_at >= ?
                LIMIT 1
                """,
                (alert_type, cutoff),
            ).fetchone()
            if existed:
                return False

            conn.execute(
                """
                INSERT INTO sla_alerts(alert_type, title, message, status, created_at, resolved_at)
                VALUES (?, ?, ?, 'active', ?, NULL)
                """,
                (alert_type, title, message, now),
            )
        return True

    def evaluate_sla_alerts(self, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        cfg = config or {}
        window_minutes = int(cfg.get("window_minutes", 60))
        min_samples = int(cfg.get("min_samples", 5))
        reply_p95_threshold_ms = int(cfg.get("reply_p95_threshold_ms", 3000))
        quote_success_rate_threshold = float(cfg.get("quote_success_rate_threshold", 0.98))

        summary = self.get_sla_summary(window_minutes=window_minutes)
        alerts: list[dict[str, Any]] = []

        if summary["event_count"] >= min_samples and summary["first_reply_p95_ms"] > reply_p95_threshold_ms:
            title = "首响时延超阈值"
            message = f"P95={summary['first_reply_p95_ms']}ms，阈值={reply_p95_threshold_ms}ms"
            if self._raise_alert_once("reply_p95", title, message):
                alerts.append({"type": "reply_p95", "title": title, "message": message})

        if summary["quote_total"] >= min_samples and summary["quote_success_rate"] < quote_success_rate_threshold:
            title = "报价成功率低于阈值"
            message = f"当前={summary['quote_success_rate']}, 阈值={quote_success_rate_threshold}"
            if self._raise_alert_once("quote_success", title, message):
                alerts.append({"type": "quote_success", "title": title, "message": message})

        return alerts

    def get_workflow_summary(self) -> dict[str, Any]:
        with self._connect() as conn:
            job_rows = conn.execute("SELECT status, COUNT(*) AS c FROM workflow_jobs GROUP BY status").fetchall()
            state_rows = conn.execute("SELECT state, COUNT(*) AS c FROM session_tasks GROUP BY state").fetchall()
            manual = conn.execute("SELECT COUNT(*) AS c FROM session_tasks WHERE manual_takeover=1").fetchone()

        jobs = {str(r["status"]): int(r["c"]) for r in job_rows}
        states = {str(r["state"]): int(r["c"]) for r in state_rows}
        return {
            "jobs": jobs,
            "states": states,
            "manual_takeover_sessions": int(manual["c"]) if manual else 0,
        }

    def get_transitions(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM session_state_transitions
                WHERE session_id=?
                ORDER BY id DESC
                LIMIT 100
                """,
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]


class WorkflowWorker:
    """常驻工作流 Worker（轮询、去重、重试、崩溃恢复）。"""

    def __init__(self, message_service: Any, store: WorkflowStore | None = None, config: dict[str, Any] | None = None):
        self.message_service = message_service
        self.logger = get_logger()

        app_config = get_config()
        workflow_cfg = app_config.get_section("messages", {}).get("workflow", {})
        self.config = {**workflow_cfg, **(config or {})}

        db_path = self.config.get("db_path")
        self.store = store or WorkflowStore(db_path=db_path)

        self.scan_limit = int(self.config.get("scan_limit", 20))
        self.claim_limit = int(self.config.get("claim_limit", 10))
        self.lease_seconds = int(self.config.get("lease_seconds", 60))
        self.poll_interval_seconds = float(self.config.get("poll_interval_seconds", 5.0))
        self.max_attempts = int(self.config.get("max_attempts", 3))
        self.backoff_seconds = int(self.config.get("backoff_seconds", 2))
        self.sla_config = self.config.get("sla", {})

    async def run_once(self, dry_run: bool = False) -> dict[str, Any]:
        recovered = self.store.recover_expired_jobs()
        unread = await self.message_service.get_unread_sessions(limit=self.scan_limit)

        enqueued = 0
        for session in unread:
            self.store.ensure_session(session)
            if self.store.enqueue_job(session, stage="reply"):
                enqueued += 1

        claimed = self.store.claim_jobs(limit=self.claim_limit, lease_seconds=self.lease_seconds)

        success = 0
        failed = 0
        skipped_manual = 0

        for job in claimed:
            try:
                session = self.store.get_session(job.session_id)
                if session and int(session.get("manual_takeover", 0)) == 1:
                    skipped_manual += 1
                    self.store.complete_job(job.id)
                    continue

                start = time.perf_counter()
                detail = await self.message_service.process_session(
                    job.payload,
                    dry_run=dry_run,
                    actor="workflow_worker",
                )
                latency_ms = int((time.perf_counter() - start) * 1000)

                if not detail.get("sent", False):
                    raise RuntimeError("reply_not_sent")

                is_quote = bool(detail.get("is_quote", False))
                quote_success = bool(detail.get("quote_success", False))
                next_state = WorkflowState.QUOTED if (is_quote and quote_success) else WorkflowState.REPLIED
                self.store.transition_state(
                    session_id=job.session_id,
                    to_state=next_state,
                    reason="workflow_worker",
                    metadata={"quote": is_quote, "quote_success": quote_success},
                )

                self.store.record_sla_event(
                    session_id=job.session_id,
                    stage="quote" if is_quote else "reply",
                    outcome="success" if (not is_quote or quote_success) else "failed",
                    latency_ms=latency_ms,
                    quote_fallback=bool(detail.get("quote_fallback", False)),
                )

                self.store.complete_job(job.id)
                success += 1
            except Exception as exc:
                failed += 1
                self.store.fail_job(
                    job_id=job.id,
                    error=str(exc),
                    max_attempts=self.max_attempts,
                    base_backoff_seconds=self.backoff_seconds,
                )

        alerts = self.store.evaluate_sla_alerts(config=self.sla_config)
        summary = self.store.get_workflow_summary()
        sla_summary = self.store.get_sla_summary(window_minutes=int(self.sla_config.get("window_minutes", 60)))

        return {
            "action": "auto_workflow",
            "dry_run": dry_run,
            "recovered_jobs": recovered,
            "unread_sessions": len(unread),
            "enqueued": enqueued,
            "claimed": len(claimed),
            "success": success,
            "failed": failed,
            "skipped_manual": skipped_manual,
            "alerts": alerts,
            "workflow": summary,
            "sla": sla_summary,
        }

    async def run_forever(self, dry_run: bool = False, max_loops: int | None = None) -> dict[str, Any]:
        loops = 0
        last = {}

        while True:
            loops += 1
            last = await self.run_once(dry_run=dry_run)
            if max_loops and loops >= max_loops:
                break
            await asyncio.sleep(max(0.2, self.poll_interval_seconds))

        return {"loops": loops, "last": last}

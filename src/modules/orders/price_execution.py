"""议价改价执行链路：策略决策 -> 真实改价 -> 回写追溯 -> 失败告警。"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class PriceExecutionService:
    """改价执行闭环服务（SQLite 持久化 + 可回放）。"""

    def __init__(self, db_path: str = "data/orders.db", notifier: Any | None = None) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.notifier = notifier
        self._init_db()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS price_update_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    order_id TEXT,
                    product_id TEXT NOT NULL,
                    strategy_json TEXT NOT NULL,
                    from_price REAL NOT NULL,
                    buyer_offer_price REAL,
                    target_price REAL NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    result_json TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_price_jobs_status_time
                ON price_update_jobs(status, updated_at DESC);

                CREATE TABLE IF NOT EXISTS price_update_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    detail_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES price_update_jobs(id)
                );

                CREATE INDEX IF NOT EXISTS idx_price_events_job_time
                ON price_update_events(job_id, created_at ASC);
                """
            )

    @staticmethod
    def decide_target_price(*, from_price: float, buyer_offer_price: float, min_price: float) -> dict[str, Any]:
        """议价策略：不低于 min_price，尽量贴合买家出价。"""
        fp = round(float(from_price), 2)
        bp = round(float(buyer_offer_price), 2)
        mp = round(float(min_price), 2)

        if bp >= fp:
            target = fp
            reason = "buyer_offer_not_lower"
        else:
            target = max(bp, mp)
            reason = "respect_floor_price" if target == mp else "accept_offer"

        return {
            "from_price": fp,
            "buyer_offer_price": bp,
            "min_price": mp,
            "target_price": round(target, 2),
            "reason": reason,
        }

    def create_job(
        self,
        *,
        session_id: str,
        product_id: str,
        from_price: float,
        buyer_offer_price: float,
        min_price: float,
        order_id: str = "",
        strategy_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        decision = self.decide_target_price(
            from_price=from_price,
            buyer_offer_price=buyer_offer_price,
            min_price=min_price,
        )
        now = self._now()
        strategy_payload = {**decision, **(strategy_meta or {})}

        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO price_update_jobs(
                    session_id, order_id, product_id, strategy_json, from_price,
                    buyer_offer_price, target_price, status, attempts, result_json,
                    last_error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, NULL, NULL, ?, ?)
                """,
                (
                    session_id,
                    order_id,
                    product_id,
                    json.dumps(strategy_payload, ensure_ascii=False),
                    decision["from_price"],
                    decision["buyer_offer_price"],
                    decision["target_price"],
                    now,
                    now,
                ),
            )
            job_id = int(cur.lastrowid)
            self._append_event(
                conn,
                job_id=job_id,
                event_type="strategy_decided",
                status="pending",
                detail={"strategy": strategy_payload},
            )

        return self.get_job(job_id) or {}

    def _append_event(
        self,
        conn: sqlite3.Connection,
        *,
        job_id: int,
        event_type: str,
        status: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO price_update_events(job_id, event_type, status, detail_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (job_id, event_type, status, json.dumps(detail or {}, ensure_ascii=False), self._now()),
        )

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM price_update_jobs WHERE id=?", (int(job_id),)).fetchone()
            if not row:
                return None
            data = dict(row)
            data["strategy"] = json.loads(data.get("strategy_json") or "{}")
            data["result"] = json.loads(data.get("result_json") or "{}")
            return data

    async def execute_job(self, job_id: int, operations_service: Any) -> dict[str, Any]:
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        now = self._now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE price_update_jobs SET status='running', attempts=attempts+1, updated_at=? WHERE id=?",
                (now, int(job_id)),
            )
            self._append_event(conn, job_id=int(job_id), event_type="execution_started", status="running")

        try:
            result = await operations_service.update_price(
                product_id=str(job.get("product_id") or ""),
                new_price=float(job.get("target_price") or 0.0),
                original_price=float(job.get("from_price") or 0.0),
            )

            success = bool(result.get("success", False))
            final_status = "success" if success else "failed"
            error = "" if success else str(result.get("error") or "update_price_failed")

            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE price_update_jobs
                    SET status=?, result_json=?, last_error=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        final_status,
                        json.dumps(result, ensure_ascii=False),
                        error or None,
                        self._now(),
                        int(job_id),
                    ),
                )
                self._append_event(
                    conn,
                    job_id=int(job_id),
                    event_type="execution_finished",
                    status=final_status,
                    detail={"result": result, "error": error},
                )

            if not success:
                await self._notify_failure(job_id=int(job_id), job=job, error=error)

            return self.replay_job(job_id)
        except Exception as exc:
            err = str(exc)
            with self._connect() as conn:
                conn.execute(
                    "UPDATE price_update_jobs SET status='failed', last_error=?, updated_at=? WHERE id=?",
                    (err[:500], self._now(), int(job_id)),
                )
                self._append_event(
                    conn,
                    job_id=int(job_id),
                    event_type="execution_exception",
                    status="failed",
                    detail={"error": err},
                )
            await self._notify_failure(job_id=int(job_id), job=job, error=err)
            return self.replay_job(job_id)

    async def _notify_failure(self, *, job_id: int, job: dict[str, Any], error: str) -> None:
        notifier = self.notifier
        if notifier is None:
            return
        text = (
            "【改价执行失败】\n"
            f"job_id={job_id}\n"
            f"session_id={job.get('session_id', '')}\n"
            f"product_id={job.get('product_id', '')}\n"
            f"target_price={job.get('target_price', '')}\n"
            f"error={error}"
        )
        send_text = getattr(notifier, "send_text", None)
        if send_text is None:
            return
        try:
            result = send_text(text)
            if hasattr(result, "__await__"):
                await result
        except Exception:
            return

    def replay_job(self, job_id: int) -> dict[str, Any]:
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT event_type, status, detail_json, created_at FROM price_update_events WHERE job_id=? ORDER BY id ASC",
                (int(job_id),),
            ).fetchall()

        events = [
            {
                "event_type": str(r["event_type"]),
                "status": str(r["status"]),
                "detail": json.loads(str(r["detail_json"] or "{}")),
                "created_at": str(r["created_at"]),
            }
            for r in rows
        ]
        return {"job": job, "events": events}

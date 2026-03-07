"""议价改价执行链路：策略决策 -> 真实改价 -> 回写追溯 -> 失败告警。"""

from __future__ import annotations

import inspect
import json
import sqlite3
from datetime import datetime, timezone
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
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
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
        product_id: str = "",
        from_price: float,
        buyer_offer_price: float,
        min_price: float,
        order_id: str = "",
        price_scope: str | None = None,
        strategy_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        strategy_meta = dict(strategy_meta or {})
        resolved_scope = (
            str(price_scope or strategy_meta.get("price_scope") or ("order" if str(order_id).strip() else "product"))
            .strip()
            .lower()
        )
        if resolved_scope not in {"order", "product"}:
            raise ValueError(f"Unsupported price_scope: {resolved_scope}")
        if resolved_scope == "order" and not str(order_id).strip():
            raise ValueError("order_id is required for order price execution")
        if resolved_scope == "product" and not str(product_id).strip():
            raise ValueError("product_id is required for product price execution")

        decision = self.decide_target_price(
            from_price=from_price,
            buyer_offer_price=buyer_offer_price,
            min_price=min_price,
        )
        now = self._now()
        strategy_payload = {**decision, **strategy_meta, "price_scope": resolved_scope}

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

    @staticmethod
    def _price_scope_for(job: dict[str, Any]) -> str:
        strategy = job.get("strategy")
        if isinstance(strategy, dict):
            scope = str(strategy.get("price_scope") or "").strip().lower()
            if scope in {"order", "product"}:
                return scope
        if str(job.get("order_id") or "").strip():
            return "order"
        return "product"

    @staticmethod
    async def _await_if_needed(result: Any) -> Any:
        if hasattr(result, "__await__"):
            return await result
        return result

    async def _invoke_with_supported_kwargs(self, func: Any, variants: list[dict[str, Any]]) -> Any:
        try:
            signature = inspect.signature(func)
        except (TypeError, ValueError):
            return await self._await_if_needed(func(**variants[0]))

        accepts_var_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values())
        parameter_names = set(signature.parameters)

        for kwargs in variants:
            if accepts_var_kwargs or set(kwargs).issubset(parameter_names):
                return await self._await_if_needed(func(**kwargs))

        raise TypeError("No supported parameter combination for price execution")

    @staticmethod
    def _normalize_result(
        *,
        result: Any,
        price_scope: str,
        order_id: str,
        product_id: str,
    ) -> dict[str, Any]:
        out = dict(result or {})
        raw_channel = str(out.get("channel") or "").strip().lower()
        raw_action = str(out.get("action") or "").strip().lower()

        if price_scope == "order":
            if raw_channel == "product_price_api" or raw_action in {"price_update", "edit_product_price"}:
                return {
                    "success": False,
                    "order_id": order_id,
                    "product_id": product_id,
                    "action": "modify_order_price",
                    "channel": "order_price_api",
                    "error": "product_price_result_on_order_flow",
                }
            out.setdefault("success", True)
            out.setdefault("order_id", out.get("order_no") or order_id)
            out["action"] = "modify_order_price"
            out["channel"] = "dom" if raw_channel == "dom" else "order_price_api"
            return out

        if raw_channel == "order_price_api" or raw_action == "modify_order_price":
            return {
                "success": False,
                "order_id": order_id,
                "product_id": product_id,
                "action": "edit_product_price",
                "channel": "product_price_api",
                "error": "order_price_result_on_product_flow",
            }
        out.setdefault("success", True)
        out.setdefault("product_id", product_id)
        out["action"] = "edit_product_price"
        out["channel"] = "dom" if raw_channel == "dom" else "product_price_api"
        return out

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

        # CAS 门控：仅允许 pending -> running；其余状态直接幂等回放，避免重入。
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE price_update_jobs
                SET status='running', attempts=attempts+1, updated_at=?
                WHERE id=? AND status='pending'
                """,
                (now, int(job_id)),
            )
            claimed = int(cur.rowcount or 0) > 0
            if claimed:
                self._append_event(conn, job_id=int(job_id), event_type="execution_started", status="running")

        if not claimed:
            return self.replay_job(job_id)

        try:
            result = await self._execute_price_change(job=job, operations_service=operations_service)

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

    async def _execute_price_change(self, *, job: dict[str, Any], operations_service: Any) -> dict[str, Any]:
        price_scope = self._price_scope_for(job)
        order_no = str(job.get("order_id") or "").strip()
        product_id = str(job.get("product_id") or "").strip()
        target_price = float(job.get("target_price") or 0.0)
        from_price = float(job.get("from_price") or 0.0)
        target_price_cents = round(target_price * 100)

        if price_scope == "order":
            modify = getattr(operations_service, "modify_order_price", None) or getattr(
                operations_service, "update_order_price", None
            )
            if not callable(modify) or not order_no:
                return {
                    "success": False,
                    "order_id": order_no,
                    "product_id": product_id,
                    "action": "modify_order_price",
                    "channel": "order_price_api",
                    "error": "order_price_unsupported",
                }

            result = await self._invoke_with_supported_kwargs(
                modify,
                [
                    {"order_no": order_no, "order_price": target_price_cents},
                    {"order_id": order_no, "order_price": target_price_cents},
                    {"order_id": order_no, "new_price": target_price, "original_price": from_price},
                    {"order_no": order_no, "new_price": target_price, "original_price": from_price},
                ],
            )
            return self._normalize_result(
                result=result,
                price_scope=price_scope,
                order_id=order_no,
                product_id=product_id,
            )

        update = getattr(operations_service, "update_price", None)
        if not callable(update) or not product_id:
            return {
                "success": False,
                "order_id": order_no,
                "product_id": product_id,
                "action": "edit_product_price",
                "channel": "product_price_api",
                "error": "product_price_unsupported",
            }

        result = await self._invoke_with_supported_kwargs(
            update,
            [
                {"product_id": product_id, "new_price": target_price, "original_price": from_price},
                {"product_id": product_id, "price": target_price_cents, "original_price": round(from_price * 100)},
                {"pid": product_id, "new_price": target_price, "original_price": from_price},
                {"pid": product_id, "price": target_price, "original_price": from_price},
            ],
        )
        return self._normalize_result(
            result=result,
            price_scope=price_scope,
            order_id=order_no,
            product_id=product_id,
        )

    def replay_job(self, job_id: int) -> dict[str, Any]:
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        with self._connect() as conn:
            rows = conn.execute(
                (
                    "SELECT event_type, status, detail_json, created_at "
                    "FROM price_update_events WHERE job_id=? ORDER BY id ASC"
                ),
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

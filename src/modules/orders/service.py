"""订单履约服务：下单状态识别、交付、售后、追溯。"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class OrderFulfillmentService:
    """订单履约闭环最小实现。"""

    STATUS_MAP = {
        "待付款": "pending",
        "已付款": "paid",
        "待发货": "processing",
        "待处理": "processing",
        "待收货": "shipping",
        "已完成": "completed",
        "售后中": "after_sales",
        "退款中": "after_sales",
        "已关闭": "closed",
        "已取消": "closed",
    }

    AFTER_SALES_TEMPLATES = {
        "delay": "抱歉让您久等了，我这边已加急核查并优先处理，预计很快给您明确进度。",
        "refund": "已收到您的退款诉求，我会按平台流程尽快处理，请放心。",
        "quality": "非常抱歉给您带来不便，我这边会先登记问题并提供处理方案（补发/退款/协商）。",
    }

    def __init__(self, db_path: str = "data/orders.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
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
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    quote_snapshot_json TEXT,
                    item_type TEXT NOT NULL DEFAULT 'virtual',
                    status TEXT NOT NULL,
                    manual_takeover INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS order_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    status TEXT,
                    detail_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_order_events_order_time
                ON order_events(order_id, created_at DESC);
                """
            )

    def map_status(self, raw_status: str) -> str:
        if raw_status in self.STATUS_MAP:
            return self.STATUS_MAP[raw_status]

        text = (raw_status or "").lower()
        if any(k in text for k in ("pay", "付款")):
            return "paid"
        if any(k in text for k in ("ship", "发货", "物流")):
            return "shipping"
        if any(k in text for k in ("after", "售后", "退款")):
            return "after_sales"
        if any(k in text for k in ("complete", "完成", "签收")):
            return "completed"
        if any(k in text for k in ("cancel", "关闭")):
            return "closed"
        return "processing"

    def upsert_order(
        self,
        order_id: str,
        raw_status: str,
        session_id: str = "",
        quote_snapshot: dict[str, Any] | None = None,
        item_type: str = "virtual",
    ) -> dict[str, Any]:
        status = self.map_status(raw_status)
        now = self._now()
        quote_json = json.dumps(quote_snapshot or {}, ensure_ascii=False)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO orders(
                    order_id, session_id, quote_snapshot_json, item_type, status,
                    manual_takeover, last_error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 0, NULL, ?, ?)
                ON CONFLICT(order_id) DO UPDATE SET
                    session_id=excluded.session_id,
                    quote_snapshot_json=excluded.quote_snapshot_json,
                    item_type=excluded.item_type,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (order_id, session_id, quote_json, item_type, status, now, now),
            )
            self._append_event(conn, order_id, "status_sync", status, {"raw_status": raw_status})

        return self.get_order(order_id)

    def _append_event(
        self,
        conn: sqlite3.Connection,
        order_id: str,
        event_type: str,
        status: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO order_events(order_id, event_type, status, detail_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (order_id, event_type, status, json.dumps(detail or {}, ensure_ascii=False), self._now()),
        )

    @staticmethod
    def _parse_order_row(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["manual_takeover"] = bool(data.get("manual_takeover", 0))
        quote = data.get("quote_snapshot_json") or "{}"
        data["quote_snapshot"] = json.loads(quote)
        return data

    def set_manual_takeover(self, order_id: str, enabled: bool) -> bool:
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE orders SET manual_takeover=?, updated_at=? WHERE order_id=?",
                (1 if enabled else 0, now, order_id),
            )
            if cur.rowcount > 0:
                self._append_event(
                    conn,
                    order_id,
                    "manual_takeover",
                    "manual" if enabled else "auto",
                    {"enabled": enabled},
                )
            return cur.rowcount > 0

    def deliver(self, order_id: str, dry_run: bool = False) -> dict[str, Any]:
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order not found: {order_id}")
        if order["manual_takeover"]:
            return {
                "order_id": order_id,
                "status": order["status"],
                "handled": False,
                "reason": "manual_takeover",
            }

        if order["item_type"] == "virtual":
            detail = {
                "action": "send_virtual_code",
                "message": "已通过闲鱼会话发送兑换信息。",
            }
        else:
            detail = {
                "action": "create_shipping_task",
                "message": "已创建实物发货任务，待揽收。",
            }

        with self._connect() as conn:
            next_status = "completed" if dry_run and order["item_type"] == "virtual" else "shipping"
            conn.execute(
                "UPDATE orders SET status=?, updated_at=? WHERE order_id=?",
                (next_status, self._now(), order_id),
            )
            self._append_event(conn, order_id, "delivery", next_status, {**detail, "dry_run": dry_run})

        updated = self.get_order(order_id)
        return {
            "order_id": order_id,
            "handled": True,
            "status": updated["status"],
            "delivery": detail,
        }

    def generate_after_sales_reply(self, issue_type: str = "delay") -> str:
        return self.AFTER_SALES_TEMPLATES.get(issue_type, self.AFTER_SALES_TEMPLATES["delay"])

    def create_after_sales_case(self, order_id: str, issue_type: str = "delay") -> dict[str, Any]:
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order not found: {order_id}")

        reply = self.generate_after_sales_reply(issue_type)
        with self._connect() as conn:
            conn.execute(
                "UPDATE orders SET status='after_sales', updated_at=? WHERE order_id=?",
                (self._now(), order_id),
            )
            self._append_event(
                conn,
                order_id,
                "after_sales",
                "after_sales",
                {"issue_type": issue_type, "reply": reply},
            )

        return {
            "order_id": order_id,
            "status": "after_sales",
            "reply_template": reply,
        }

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
            if not row:
                return None
            return self._parse_order_row(row)

    def list_orders(
        self,
        *,
        status: str | None = None,
        limit: int = 20,
        include_manual: bool = True,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM orders"
        clauses: list[str] = []
        params: list[Any] = []

        if status:
            clauses.append("status = ?")
            params.append(status)
        if not include_manual:
            clauses.append("manual_takeover = 0")

        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(int(limit), 1))

        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [self._parse_order_row(row) for row in rows]

    def get_summary(self) -> dict[str, Any]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(1) AS c FROM orders").fetchone()["c"]
            manual = conn.execute("SELECT COUNT(1) AS c FROM orders WHERE manual_takeover=1").fetchone()["c"]
            by_status_rows = conn.execute(
                "SELECT status, COUNT(1) AS c FROM orders GROUP BY status ORDER BY c DESC"
            ).fetchall()

        by_status = {str(row["status"]): int(row["c"]) for row in by_status_rows}
        return {
            "total_orders": int(total),
            "manual_takeover_orders": int(manual),
            "after_sales_orders": int(by_status.get("after_sales", 0)),
            "by_status": by_status,
        }

    def record_after_sales_followup(
        self,
        *,
        order_id: str,
        issue_type: str,
        reply_text: str,
        sent: bool,
        dry_run: bool,
        reason: str = "",
        session_id: str = "",
    ) -> dict[str, Any]:
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order not found: {order_id}")

        detail = {
            "issue_type": issue_type,
            "reply": reply_text,
            "sent": bool(sent),
            "dry_run": bool(dry_run),
            "reason": reason,
            "session_id": session_id,
        }
        with self._connect() as conn:
            conn.execute(
                "UPDATE orders SET updated_at=? WHERE order_id=?",
                (self._now(), order_id),
            )
            self._append_event(conn, order_id, "after_sales_followup", "after_sales", detail)

        return {
            "order_id": order_id,
            "status": "after_sales",
            "sent": bool(sent),
            "dry_run": bool(dry_run),
            "reason": reason,
        }

    def trace_order(self, order_id: str) -> dict[str, Any]:
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order not found: {order_id}")

        with self._connect() as conn:
            events = conn.execute(
                "SELECT event_type, status, detail_json, created_at FROM order_events WHERE order_id=? ORDER BY id ASC",
                (order_id,),
            ).fetchall()

        parsed_events = []
        for ev in events:
            parsed_events.append(
                {
                    "event_type": ev["event_type"],
                    "status": ev["status"],
                    "detail": json.loads(ev["detail_json"] or "{}"),
                    "created_at": ev["created_at"],
                }
            )

        return {
            "order": order,
            "events": parsed_events,
        }

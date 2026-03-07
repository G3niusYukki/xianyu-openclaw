from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Any

from .callbacks import VirtualGoodsCallbackService
from .ingress import VirtualGoodsIngress
from .store import VirtualGoodsStore


class VirtualGoodsService:
    def __init__(self, db_path: str = "data/orders.db", config: dict[str, Any] | None = None) -> None:
        self.store = VirtualGoodsStore(db_path=db_path)
        merged_config: dict[str, Any] = dict(config or {})
        merged_config.setdefault("auto_reissue_code", False)
        merged_config.setdefault("auto_replenish_order", False)
        self.callbacks = VirtualGoodsCallbackService(self.store, config=merged_config)
        self.ingress = VirtualGoodsIngress(self.callbacks)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    def _ts(cls) -> str:
        return cls._now().strftime("%Y-%m-%dT%H:%M:%SZ")

    @classmethod
    def _resp(
        cls,
        *,
        ok: bool,
        action: str,
        code: str,
        message: str,
        data: Any = None,
        metrics: dict[str, Any] | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "ok": bool(ok),
            "action": action,
            "code": code,
            "message": message,
            "data": data,
            "metrics": dict(metrics or {}),
            "errors": list(errors or []),
            "ts": cls._ts(),
        }

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.store.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    @staticmethod
    def _loads_json(text: Any, fallback: Any) -> Any:
        if not isinstance(text, str) or not text:
            return fallback
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return fallback

    @staticmethod
    def _to_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _to_float(cls, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def _callback_view(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        data = dict(row)
        data["payload"] = self._loads_json(data.get("payload_json"), {})
        data["headers"] = self._loads_json(data.get("headers_json"), {})
        return {
            "id": int(data.get("id") or 0),
            "external_event_id": data.get("external_event_id"),
            "dedupe_key": data.get("dedupe_key"),
            "xianyu_order_id": data.get("xianyu_order_id"),
            "source_family": data.get("source_family"),
            "event_kind": data.get("event_kind"),
            "verify_passed": bool(int(data.get("verify_passed") or 0)),
            "processed": bool(int(data.get("processed") or 0)),
            "attempt_count": int(data.get("attempt_count") or 0),
            "last_process_error": data.get("last_process_error"),
            "created_at": data.get("created_at"),
            "processed_at": data.get("processed_at"),
            "payload": data.get("payload") or {},
            "headers": data.get("headers") or {},
        }

    def list_timeout_backlog(self, *, timeout_seconds: int = 300, limit: int = 100) -> dict[str, Any]:
        timeout_seconds = max(0, int(timeout_seconds))
        limit = max(1, int(limit))
        cutoff = (self._now() - timedelta(seconds=timeout_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")

        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM virtual_goods_callbacks
                WHERE processed = 0
                  AND verify_passed = 1
                  AND created_at <= ?
                ORDER BY created_at ASC, id ASC
                LIMIT ?
                """,
                (cutoff, limit),
            ).fetchall()

        now = self._now()
        items: list[dict[str, Any]] = []
        unknown_count = 0
        for row in rows:
            item = self._callback_view(row)
            if item["event_kind"] == "unknown":
                unknown_count += 1
            created_at = datetime.strptime(str(item["created_at"]), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            item["age_seconds"] = max(0, int((now - created_at).total_seconds()))
            items.append(item)

        errors = []
        if unknown_count:
            errors.append(
                {
                    "code": "UNKNOWN_EVENT_KIND",
                    "message": "unknown event_kind found in timeout backlog",
                    "count": unknown_count,
                }
            )

        return self._resp(
            ok=True,
            action="list_timeout_backlog",
            code="OK",
            message="timeout backlog listed",
            data={"items": items},
            metrics={"count": len(items), "timeout_seconds": timeout_seconds, "unknown_event_kind": unknown_count},
            errors=errors,
        )

    def list_replay_candidates(self, *, limit: int = 100) -> dict[str, Any]:
        limit = max(1, int(limit))
        now = self._ts()
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM virtual_goods_callbacks
                WHERE verify_passed = 1
                  AND (
                    processed = 0
                    OR (processed = 1 AND last_process_error IS NOT NULL)
                    OR (claim_expires_at IS NOT NULL AND claim_expires_at <= ?)
                  )
                ORDER BY created_at ASC, id ASC
                LIMIT ?
                """,
                (now, limit),
            ).fetchall()

        items = [self._callback_view(row) for row in rows]
        unknown_count = sum(1 for item in items if item["event_kind"] == "unknown")
        errors = []
        if unknown_count:
            errors.append(
                {
                    "code": "UNKNOWN_EVENT_KIND",
                    "message": "unknown event_kind found in replay candidates",
                    "count": unknown_count,
                }
            )

        return self._resp(
            ok=True,
            action="list_replay_candidates",
            code="OK",
            message="replay candidates listed",
            data={"items": items},
            metrics={"count": len(items), "unknown_event_kind": unknown_count},
            errors=errors,
        )

    def list_manual_takeover_orders(self, *, limit: int = 100) -> dict[str, Any]:
        limit = max(1, int(limit))
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM virtual_goods_orders
                WHERE manual_takeover = 1
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return self._resp(
            ok=True,
            action="list_manual_takeover_orders",
            code="OK",
            message="manual takeover orders listed",
            data={"items": [dict(row) for row in rows]},
            metrics={"count": len(rows)},
        )

    def inspect_order(self, xianyu_order_id: str | None = None, *, order_id: str | None = None) -> dict[str, Any]:
        oid = str(order_id or xianyu_order_id or "").strip()
        if not oid:
            return self._resp(
                ok=False,
                action="inspect_order",
                code="BAD_REQUEST",
                message="missing order_id",
                data=None,
                errors=[{"code": "MISSING_ORDER_ID", "message": "order_id is required"}],
            )

        with closing(self._connect()) as conn:
            order = conn.execute("SELECT * FROM virtual_goods_orders WHERE xianyu_order_id=?", (oid,)).fetchone()
            callbacks = conn.execute(
                "SELECT * FROM virtual_goods_callbacks WHERE xianyu_order_id=? ORDER BY id DESC", (oid,)
            ).fetchall()
            exception_rows = conn.execute(
                """
                SELECT id, xianyu_order_id, event_kind, exception_code, severity, status,
                       first_seen_at, last_seen_at, occurrence_count, detail_json, created_at, updated_at
                FROM ops_exception_pool
                WHERE xianyu_order_id = ? AND status != 'resolved'
                ORDER BY CASE severity WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END ASC,
                         last_seen_at DESC,
                         id DESC
                """,
                (oid,),
            ).fetchall()

        if not order:
            return self._resp(
                ok=False,
                action="inspect_order",
                code="NOT_FOUND",
                message="order not found",
                data={"xianyu_order_id": oid, "order_id": oid, "order": None, "callbacks": [], "callback_timeline": []},
            )

        callback_items = [self._callback_view(row) for row in callbacks]
        callbacks_timeline = [
            {
                "callback_id": self._to_int(item.get("id")),
                "event_kind": str(item.get("event_kind") or ""),
                "verify_passed": bool(item.get("verify_passed")),
                "processed": bool(item.get("processed")),
                "attempt_count": self._to_int(item.get("attempt_count")),
                "last_process_error": str(item.get("last_process_error") or ""),
                "created_at": str(item.get("created_at") or ""),
                "processed_at": str(item.get("processed_at") or ""),
            }
            for item in callback_items
        ]
        unknown_count = sum(1 for item in callback_items if item["event_kind"] == "unknown")

        exception_items: list[dict[str, Any]] = []
        for row in exception_rows:
            detail = self._loads_json(row["detail_json"], {})
            exception_items.append(
                {
                    "priority": str(row["severity"] or "P2"),
                    "type": str(row["exception_code"] or "").upper(),
                    "count": self._to_int(row["occurrence_count"], 1),
                    "summary": str(row["event_kind"] or "") or str(row["exception_code"] or ""),
                    "exception_id": self._to_int(row["id"]),
                    "status": str(row["status"] or "open"),
                    "first_seen_at": str(row["first_seen_at"] or ""),
                    "last_seen_at": str(row["last_seen_at"] or ""),
                    "detail": detail if isinstance(detail, dict) else {},
                }
            )

        if unknown_count and not any(item.get("type") == "UNKNOWN_EVENT_KIND" for item in exception_items):
            exception_items.insert(
                0,
                {
                    "priority": "P0",
                    "type": "UNKNOWN_EVENT_KIND",
                    "count": unknown_count,
                    "summary": "该订单存在 unknown event_kind 回调，已纳入异常池。",
                },
            )

        errors = []
        if unknown_count:
            errors.append(
                {
                    "code": "UNKNOWN_EVENT_KIND",
                    "message": "unknown event_kind found in callbacks",
                    "count": unknown_count,
                }
            )

        order_data = dict(order)
        return self._resp(
            ok=True,
            action="inspect_order",
            code="OK",
            message="order inspected",
            data={
                "xianyu_order_id": oid,
                "order_id": oid,
                "order": order_data,
                "callbacks": callback_items,
                "callback_timeline": callbacks_timeline,
                "exception_priority_pool": {"total_items": len(exception_items), "items": exception_items},
            },
            metrics={
                "callback_count": len(callback_items),
                "unknown_event_kind": unknown_count,
                "exception_items": len(exception_items),
            },
            errors=errors,
        )

    def get_dashboard_metrics(self, *, timeout_seconds: int = 300) -> dict[str, Any]:
        timeout_seconds = max(0, int(timeout_seconds))
        cutoff = (self._now() - timedelta(seconds=timeout_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")

        with closing(self._connect()) as conn:
            total_orders = int(conn.execute("SELECT COUNT(1) FROM virtual_goods_orders").fetchone()[0])
            manual_orders = int(
                conn.execute("SELECT COUNT(1) FROM virtual_goods_orders WHERE manual_takeover=1").fetchone()[0]
            )
            total_callbacks = int(conn.execute("SELECT COUNT(1) FROM virtual_goods_callbacks").fetchone()[0])
            pending_callbacks = int(
                conn.execute("SELECT COUNT(1) FROM virtual_goods_callbacks WHERE processed=0").fetchone()[0]
            )
            processed_callbacks = int(
                conn.execute("SELECT COUNT(1) FROM virtual_goods_callbacks WHERE processed=1").fetchone()[0]
            )
            failed_callbacks = int(
                conn.execute(
                    "SELECT COUNT(1) FROM virtual_goods_callbacks WHERE last_process_error IS NOT NULL AND processed=0"
                ).fetchone()[0]
            )
            timeout_backlog = int(
                conn.execute(
                    "SELECT COUNT(1) FROM virtual_goods_callbacks WHERE processed=0 AND verify_passed=1 AND created_at<=?",
                    (cutoff,),
                ).fetchone()[0]
            )
            unknown_event_kind = int(
                conn.execute("SELECT COUNT(1) FROM virtual_goods_callbacks WHERE event_kind='unknown'").fetchone()[0]
            )

        metrics = {
            "total_orders": total_orders,
            "manual_takeover_orders": manual_orders,
            "total_callbacks": total_callbacks,
            "pending_callbacks": pending_callbacks,
            "processed_callbacks": processed_callbacks,
            "failed_callbacks": failed_callbacks,
            "timeout_backlog": timeout_backlog,
            "unknown_event_kind": unknown_event_kind,
            "timeout_seconds": timeout_seconds,
        }
        errors = []
        if unknown_event_kind:
            errors.append(
                {
                    "code": "UNKNOWN_EVENT_KIND",
                    "message": "unknown event_kind callbacks detected",
                    "count": unknown_event_kind,
                }
            )
        return self._resp(
            ok=True,
            action="get_dashboard_metrics",
            code="OK",
            message="dashboard metrics ready",
            data=metrics,
            metrics=metrics,
            errors=errors,
        )

    def get_funnel_metrics(
        self, *, start_date: str | None = None, end_date: str | None = None, limit: int = 500
    ) -> dict[str, Any]:
        limit = max(1, int(limit))
        where: list[str] = []
        params: list[Any] = []
        if start_date:
            where.append("stat_date >= ?")
            params.append(str(start_date))
        if end_date:
            where.append("stat_date <= ?")
            params.append(str(end_date))

        sql = "SELECT stat_date, stage, xianyu_product_id, xianyu_listing_id, metric_count, updated_at FROM ops_funnel_stage_daily"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY stat_date DESC, stage ASC LIMIT ?"
        params.append(limit)

        with closing(self._connect()) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
            unknown_event_kind = self._to_int(
                conn.execute(
                    "SELECT COUNT(1) FROM ops_exception_pool WHERE exception_code='unknown_event_kind' AND status != 'resolved'"
                ).fetchone()[0]
            )

        items = [dict(row) for row in rows]
        total_count = sum(self._to_int(item.get("metric_count")) for item in items)
        by_stage: dict[str, int] = {}
        for item in items:
            stage = str(item.get("stage") or "unknown")
            by_stage[stage] = by_stage.get(stage, 0) + self._to_int(item.get("metric_count"))

        errors = []
        if unknown_event_kind > 0:
            errors.append(
                {
                    "code": "UNKNOWN_EVENT_KIND",
                    "message": "unknown event_kind in exception pool",
                    "count": unknown_event_kind,
                }
            )

        return self._resp(
            ok=True,
            action="get_funnel_metrics",
            code="OK",
            message="funnel metrics ready",
            data={"items": items, "stage_totals": by_stage},
            metrics={
                "rows": len(items),
                "total_metric_count": total_count,
                "unknown_event_kind": unknown_event_kind,
                "source": "ops_funnel_stage_daily",
            },
            errors=errors,
        )

    def get_product_operation_metrics(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        xianyu_product_id: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        limit = max(1, int(limit))
        where: list[str] = []
        params: list[Any] = []
        if start_date:
            where.append("stat_date >= ?")
            params.append(str(start_date))
        if end_date:
            where.append("stat_date <= ?")
            params.append(str(end_date))
        if xianyu_product_id:
            where.append("xianyu_product_id = ?")
            params.append(str(xianyu_product_id))

        sql = (
            "SELECT stat_date, xianyu_product_id, xianyu_listing_id, exposure_count, paid_order_count, "
            "paid_amount_cents, refund_order_count, exception_count, manual_takeover_count, updated_at "
            "FROM ops_item_daily_snapshot"
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY stat_date DESC, xianyu_product_id ASC LIMIT ?"
        params.append(limit)

        with closing(self._connect()) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
            unknown_event_kind = self._to_int(
                conn.execute(
                    "SELECT COUNT(1) FROM ops_exception_pool WHERE exception_code='unknown_event_kind' AND status != 'resolved'"
                ).fetchone()[0]
            )

        items = [dict(row) for row in rows]
        exposure_total = 0
        paid_order_total = 0
        paid_amount_total = 0
        refund_total = 0
        exception_total = 0
        manual_total = 0
        for item in items:
            exposure_total += self._to_int(item.get("exposure_count"))
            paid_order_total += self._to_int(item.get("paid_order_count"))
            paid_amount_total += self._to_int(item.get("paid_amount_cents"))
            refund_total += self._to_int(item.get("refund_order_count"))
            exception_total += self._to_int(item.get("exception_count"))
            manual_total += self._to_int(item.get("manual_takeover_count"))

        has_ops_snapshot_data = len(items) > 0
        conversion_rate = round((paid_order_total / exposure_total) * 100, 4) if exposure_total > 0 else 0.0

        stable_summary: dict[str, Any]
        stable_field_state: dict[str, str]
        stable_field_class: dict[str, str]
        if has_ops_snapshot_data:
            stable_summary = {
                "exposure_count": exposure_total,
                "paid_order_count": paid_order_total,
                "paid_amount_cents": paid_amount_total,
                "refund_order_count": refund_total,
                "exception_count": exception_total,
                "manual_takeover_count": manual_total,
                "conversion_rate_pct": conversion_rate,
            }
            stable_field_state = {
                "exposure_count": "available",
                "paid_order_count": "available",
                "paid_amount_cents": "available",
                "refund_order_count": "available",
                "exception_count": "available",
                "manual_takeover_count": "available",
                "conversion_rate_pct": "available",
            }
            stable_field_class = {
                "exposure_count": "real_source",
                "paid_order_count": "real_source",
                "paid_amount_cents": "real_source",
                "refund_order_count": "real_source",
                "exception_count": "real_source",
                "manual_takeover_count": "real_source",
                "conversion_rate_pct": "real_source",
            }
        else:
            stable_summary = {
                "exposure_count": None,
                "paid_order_count": None,
                "paid_amount_cents": None,
                "refund_order_count": None,
                "exception_count": None,
                "manual_takeover_count": None,
                "conversion_rate_pct": None,
            }
            stable_field_state = {
                "exposure_count": "placeholder",
                "paid_order_count": "placeholder",
                "paid_amount_cents": "placeholder",
                "refund_order_count": "placeholder",
                "exception_count": "placeholder",
                "manual_takeover_count": "placeholder",
                "conversion_rate_pct": "placeholder",
            }
            stable_field_class = {
                "exposure_count": "placeholder_disabled",
                "paid_order_count": "placeholder_disabled",
                "paid_amount_cents": "placeholder_disabled",
                "refund_order_count": "placeholder_disabled",
                "exception_count": "placeholder_disabled",
                "manual_takeover_count": "placeholder_disabled",
                "conversion_rate_pct": "placeholder_disabled",
            }

        # 模块A约束：views/wants/sales/上下架重上/擦亮/Top-Bottom 二选一。
        # 当前 orders.db 内无稳定来源，明确返回禁用态，供前端与测试识别。
        optional_fields = {
            "views": {"state": "placeholder_disabled", "reason": "no_stable_source", "value": None},
            "wants": {"state": "placeholder_disabled", "reason": "no_stable_source", "value": None},
            "sales": {"state": "placeholder_disabled", "reason": "no_stable_source", "value": None},
            "relist_count": {"state": "placeholder_disabled", "reason": "no_stable_source", "value": None},
            "polish_count": {"state": "placeholder_disabled", "reason": "no_stable_source", "value": None},
            "top_bottom_count": {"state": "placeholder_disabled", "reason": "no_stable_source", "value": None},
        }
        errors = []
        if unknown_event_kind > 0:
            errors.append(
                {
                    "code": "UNKNOWN_EVENT_KIND",
                    "message": "unknown event_kind in exception pool",
                    "count": unknown_event_kind,
                }
            )

        return self._resp(
            ok=True,
            action="get_product_operation_metrics",
            code="OK",
            message="product operation metrics ready",
            data={
                "items": items,
                "summary": stable_summary,
                "field_state": stable_field_state,
                "field_class": stable_field_class,
                "optional_fields": optional_fields,
            },
            metrics={
                "rows": len(items),
                "unknown_event_kind": unknown_event_kind,
                "source": "ops_item_daily_snapshot",
                "has_ops_snapshot_data": has_ops_snapshot_data,
            },
            errors=errors,
        )

    def get_fulfillment_efficiency_metrics(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        xianyu_product_id: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        limit = max(1, int(limit))
        where: list[str] = []
        params: list[Any] = []
        if start_date:
            where.append("stat_date >= ?")
            params.append(str(start_date))
        if end_date:
            where.append("stat_date <= ?")
            params.append(str(end_date))
        if xianyu_product_id:
            where.append("xianyu_product_id = ?")
            params.append(str(xianyu_product_id))

        sql = (
            "SELECT stat_date, xianyu_product_id, xianyu_listing_id, total_orders, fulfilled_orders, failed_orders, "
            "avg_fulfillment_seconds, p95_fulfillment_seconds, updated_at FROM ops_fulfillment_eff_daily"
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY stat_date DESC, xianyu_product_id ASC LIMIT ?"
        params.append(limit)

        with closing(self._connect()) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
            unknown_event_kind = self._to_int(
                conn.execute(
                    "SELECT COUNT(1) FROM ops_exception_pool WHERE exception_code='unknown_event_kind' AND status != 'resolved'"
                ).fetchone()[0]
            )

        items = [dict(row) for row in rows]
        total_orders = 0
        fulfilled_orders = 0
        failed_orders = 0
        weighted_avg_sum = 0
        p95_max = 0
        for item in items:
            orders = self._to_int(item.get("total_orders"))
            total_orders += orders
            fulfilled_orders += self._to_int(item.get("fulfilled_orders"))
            failed_orders += self._to_int(item.get("failed_orders"))
            weighted_avg_sum += self._to_int(item.get("avg_fulfillment_seconds")) * orders
            p95_max = max(p95_max, self._to_int(item.get("p95_fulfillment_seconds")))

        avg_seconds = round(weighted_avg_sum / total_orders, 2) if total_orders > 0 else 0.0
        fulfillment_rate = round((fulfilled_orders / total_orders) * 100, 4) if total_orders > 0 else 0.0
        fail_rate = round((failed_orders / total_orders) * 100, 4) if total_orders > 0 else 0.0
        errors = []
        if unknown_event_kind > 0:
            errors.append(
                {
                    "code": "UNKNOWN_EVENT_KIND",
                    "message": "unknown event_kind in exception pool",
                    "count": unknown_event_kind,
                }
            )

        return self._resp(
            ok=True,
            action="get_fulfillment_efficiency_metrics",
            code="OK",
            message="fulfillment efficiency metrics ready",
            data={
                "items": items,
                "summary": {
                    "total_orders": total_orders,
                    "fulfilled_orders": fulfilled_orders,
                    "failed_orders": failed_orders,
                    "avg_fulfillment_seconds": avg_seconds,
                    "p95_fulfillment_seconds": p95_max,
                    "fulfillment_rate_pct": fulfillment_rate,
                    "failure_rate_pct": fail_rate,
                },
            },
            metrics={
                "rows": len(items),
                "unknown_event_kind": unknown_event_kind,
                "source": "ops_fulfillment_eff_daily",
            },
            errors=errors,
        )

    def list_priority_exceptions(self, *, limit: int = 100, status: str = "open") -> dict[str, Any]:
        limit = max(1, int(limit))
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM ops_exception_pool
                WHERE status = ?
                ORDER BY CASE severity WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END ASC,
                         last_seen_at DESC,
                         id DESC
                LIMIT ?
                """,
                (str(status or "open"), limit),
            ).fetchall()

        raw_items = [dict(row) for row in rows]
        items: list[dict[str, Any]] = []
        unknown_event_kind = 0
        by_severity = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
        for row in raw_items:
            severity = str(row.get("severity") or "P2").upper()
            if severity not in by_severity:
                severity = "P2"
            by_severity[severity] += 1
            if str(row.get("exception_code") or "") == "unknown_event_kind":
                unknown_event_kind += self._to_int(row.get("occurrence_count"), 1)
            detail = self._loads_json(row.get("detail_json"), {})
            items.append(
                {
                    **row,
                    "priority": severity,
                    "type": str(row.get("exception_code") or "").upper(),
                    "count": self._to_int(row.get("occurrence_count"), 1),
                    "summary": str(row.get("event_kind") or "") or str(row.get("exception_code") or ""),
                    "detail": detail if isinstance(detail, dict) else {},
                }
            )

        errors = []
        if unknown_event_kind > 0:
            errors.append(
                {
                    "code": "UNKNOWN_EVENT_KIND",
                    "message": "unknown event_kind in exception pool",
                    "count": unknown_event_kind,
                }
            )

        return self._resp(
            ok=True,
            action="list_priority_exceptions",
            code="OK",
            message="priority exceptions listed",
            data={"items": items},
            metrics={
                "rows": len(items),
                "unknown_event_kind": unknown_event_kind,
                "severity_p0": by_severity["P0"],
                "severity_p1": by_severity["P1"],
                "severity_p2": by_severity["P2"],
                "severity_p3": by_severity["P3"],
                "source": "ops_exception_pool",
            },
            errors=errors,
        )

    def set_manual_takeover(self, xianyu_order_id: str, enabled: bool) -> dict[str, Any]:
        oid = str(xianyu_order_id or "").strip()
        if not oid:
            return self._resp(
                ok=False,
                action="set_manual_takeover",
                code="BAD_REQUEST",
                message="missing xianyu_order_id",
                errors=[{"code": "MISSING_ORDER_ID", "message": "xianyu_order_id is required"}],
            )

        now = self._ts()
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute("SELECT * FROM virtual_goods_orders WHERE xianyu_order_id=?", (oid,)).fetchone()
            if not current:
                conn.execute("ROLLBACK")
                return self._resp(
                    ok=False,
                    action="set_manual_takeover",
                    code="NOT_FOUND",
                    message="order not found",
                    data={"xianyu_order_id": oid},
                )
            next_fulfillment = "manual" if enabled else (current["fulfillment_status"] or "pending")
            conn.execute(
                """
                UPDATE virtual_goods_orders
                SET manual_takeover=?,
                    fulfillment_status=?,
                    updated_at=?
                WHERE xianyu_order_id=?
                """,
                (1 if enabled else 0, next_fulfillment, now, oid),
            )
            updated = conn.execute("SELECT * FROM virtual_goods_orders WHERE xianyu_order_id=?", (oid,)).fetchone()
            conn.commit()

        return self._resp(
            ok=True,
            action="set_manual_takeover",
            code="OK",
            message="manual takeover updated",
            data={"order": dict(updated) if updated else None},
            metrics={"updated": 1},
        )

    def upsert_listing_product_mapping(
        self,
        *,
        xianyu_product_id: str,
        internal_listing_id: str | None = None,
        supply_goods_no: str | None = None,
        mapping_status: str = "unmapped",
        last_sync_at: str | None = None,
    ) -> dict[str, Any]:
        try:
            mapping = self.store.upsert_listing_product_mapping(
                xianyu_product_id=xianyu_product_id,
                internal_listing_id=internal_listing_id,
                supply_goods_no=supply_goods_no,
                mapping_status=mapping_status,
                last_sync_at=last_sync_at,
            )
        except ValueError as exc:
            return self._resp(
                ok=False,
                action="upsert_listing_product_mapping",
                code="BAD_REQUEST",
                message="invalid mapping payload",
                errors=[{"code": "INVALID_MAPPING", "message": str(exc)}],
            )
        return self._resp(
            ok=True,
            action="upsert_listing_product_mapping",
            code="OK",
            message="listing product mapping upserted",
            data={"mapping": mapping},
            metrics={"updated": 1},
        )

    def get_listing_product_mapping(
        self, *, xianyu_product_id: str | None = None, internal_listing_id: str | None = None
    ) -> dict[str, Any]:
        try:
            mapping = self.store.get_listing_product_mapping(
                xianyu_product_id=xianyu_product_id,
                internal_listing_id=internal_listing_id,
            )
        except ValueError as exc:
            return self._resp(
                ok=False,
                action="get_listing_product_mapping",
                code="BAD_REQUEST",
                message="invalid mapping query",
                errors=[{"code": "INVALID_QUERY", "message": str(exc)}],
            )

        if not mapping:
            return self._resp(
                ok=False,
                action="get_listing_product_mapping",
                code="NOT_FOUND",
                message="mapping not found",
                data={"mapping": None},
            )

        return self._resp(
            ok=True,
            action="get_listing_product_mapping",
            code="OK",
            message="mapping fetched",
            data={"mapping": mapping},
        )

    def get_listing_product_mapping_by_product_id(self, *, xianyu_product_id: str) -> dict[str, Any]:
        try:
            mapping = self.store.get_listing_product_mapping_by_product_id(xianyu_product_id=xianyu_product_id)
        except ValueError as exc:
            return self._resp(
                ok=False,
                action="get_listing_product_mapping_by_product_id",
                code="BAD_REQUEST",
                message="invalid mapping query",
                errors=[{"code": "INVALID_QUERY", "message": str(exc)}],
            )

        if not mapping:
            return self._resp(
                ok=False,
                action="get_listing_product_mapping_by_product_id",
                code="NOT_FOUND",
                message="mapping not found",
                data={"mapping": None},
            )

        return self._resp(
            ok=True,
            action="get_listing_product_mapping_by_product_id",
            code="OK",
            message="mapping fetched",
            data={"mapping": mapping},
        )

    def get_listing_product_mapping_by_internal_id(self, *, internal_listing_id: str) -> dict[str, Any]:
        try:
            mapping = self.store.get_listing_product_mapping_by_internal_id(internal_listing_id=internal_listing_id)
        except ValueError as exc:
            return self._resp(
                ok=False,
                action="get_listing_product_mapping_by_internal_id",
                code="BAD_REQUEST",
                message="invalid mapping query",
                errors=[{"code": "INVALID_QUERY", "message": str(exc)}],
            )

        if not mapping:
            return self._resp(
                ok=False,
                action="get_listing_product_mapping_by_internal_id",
                code="NOT_FOUND",
                message="mapping not found",
                data={"mapping": None},
            )

        return self._resp(
            ok=True,
            action="get_listing_product_mapping_by_internal_id",
            code="OK",
            message="mapping fetched",
            data={"mapping": mapping},
        )

    def update_listing_mapping_status(
        self,
        *,
        xianyu_product_id: str,
        mapping_status: str,
        last_sync_at: str | None = None,
    ) -> dict[str, Any]:
        try:
            mapping = self.store.update_listing_mapping_status(
                xianyu_product_id=xianyu_product_id,
                mapping_status=mapping_status,
                last_sync_at=last_sync_at,
            )
        except ValueError as exc:
            return self._resp(
                ok=False,
                action="update_listing_mapping_status",
                code="BAD_REQUEST",
                message="invalid mapping status update",
                errors=[{"code": "INVALID_MAPPING", "message": str(exc)}],
            )

        if not mapping:
            return self._resp(
                ok=False,
                action="update_listing_mapping_status",
                code="NOT_FOUND",
                message="mapping not found",
                data={"mapping": None},
                metrics={"updated": 0},
            )

        return self._resp(
            ok=True,
            action="update_listing_mapping_status",
            code="OK",
            message="mapping status updated",
            data={"mapping": mapping},
            metrics={"updated": 1},
        )

    def delete_listing_product_mapping(self, *, xianyu_product_id: str) -> dict[str, Any]:
        try:
            deleted = self.store.delete_listing_product_mapping(xianyu_product_id=xianyu_product_id)
        except ValueError as exc:
            return self._resp(
                ok=False,
                action="delete_listing_product_mapping",
                code="BAD_REQUEST",
                message="invalid mapping delete request",
                errors=[{"code": "INVALID_QUERY", "message": str(exc)}],
            )

        if not deleted:
            return self._resp(
                ok=False,
                action="delete_listing_product_mapping",
                code="NOT_FOUND",
                message="mapping not found",
                metrics={"deleted": 0},
            )

        return self._resp(
            ok=True,
            action="delete_listing_product_mapping",
            code="OK",
            message="mapping deleted",
            metrics={"deleted": 1},
        )

    def run_timeout_scan(self, *, timeout_seconds: int = 300, limit: int = 100) -> dict[str, Any]:
        timeout_seconds = max(0, int(timeout_seconds))
        limit = max(1, int(limit))
        cutoff = (self._now() - timedelta(seconds=timeout_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
        now = self._ts()

        timed_out = 0
        unknown_count = 0
        affected_orders: set[str] = set()

        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """
                SELECT id, xianyu_order_id, event_kind
                FROM virtual_goods_callbacks
                WHERE processed = 0
                  AND verify_passed = 1
                  AND created_at <= ?
                ORDER BY created_at ASC, id ASC
                LIMIT ?
                """,
                (cutoff, limit),
            ).fetchall()

            for row in rows:
                callback_id = int(row["id"])
                event_kind = str(row["event_kind"] or "")
                if event_kind == "unknown":
                    unknown_count += 1
                conn.execute(
                    """
                    UPDATE virtual_goods_callbacks
                    SET processed = 0,
                        processed_at = NULL,
                        last_process_error = 'timeout_scan',
                        claim_expires_at = NULL,
                        claimed_at = NULL,
                        claimed_by = NULL
                    WHERE id = ?
                    """,
                    (callback_id,),
                )
                oid = str(row["xianyu_order_id"] or "").strip()
                if oid:
                    affected_orders.add(oid)
                timed_out += 1

            for oid in affected_orders:
                conn.execute(
                    """
                    UPDATE virtual_goods_orders
                    SET callback_status='failed',
                        last_error='callback_timeout_scan',
                        updated_at=?
                    WHERE xianyu_order_id=?
                    """,
                    (now, oid),
                )
            conn.commit()

        errors = []
        if unknown_count:
            errors.append(
                {
                    "code": "UNKNOWN_EVENT_KIND",
                    "message": "unknown event_kind entered timeout metrics",
                    "count": unknown_count,
                }
            )

        return self._resp(
            ok=True,
            action="run_timeout_scan",
            code="OK",
            message="timeout scan completed",
            data={"timed_out_callback_ids": timed_out, "affected_orders": sorted(affected_orders)},
            metrics={
                "timed_out": timed_out,
                "affected_orders": len(affected_orders),
                "unknown_event_kind": unknown_count,
            },
            errors=errors,
        )

    def _replay(self, *, action: str, where_sql: str, value: str) -> dict[str, Any]:
        target = str(value or "").strip()
        if not target:
            return self._resp(
                ok=False,
                action=action,
                code="BAD_REQUEST",
                message="missing replay key",
                errors=[{"code": "MISSING_REPLAY_KEY", "message": "replay key is required"}],
            )

        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT * FROM virtual_goods_callbacks WHERE {where_sql} ORDER BY id DESC LIMIT 1", (target,)
            ).fetchone()

        if not row:
            return self._resp(
                ok=False, action=action, code="NOT_FOUND", message="callback not found", data={"target": target}
            )

        cb = dict(row)
        errors = []
        unknown_count = 0
        if str(cb.get("event_kind") or "") == "unknown":
            unknown_count = 1
            errors.append(
                {"code": "UNKNOWN_EVENT_KIND", "message": "replay callback has unknown event_kind", "count": 1}
            )

        headers = self._loads_json(cb.get("headers_json"), {})
        query_params = headers.get("query_params") if isinstance(headers, dict) else {}
        raw_headers = dict(headers) if isinstance(headers, dict) else {}
        raw_headers.pop("query_params", None)

        try:
            replay_result = self.callbacks.process(
                source_family=str(cb.get("source_family") or ""),
                event_kind=str(cb.get("event_kind") or ""),
                raw_body=str(cb.get("raw_body") or ""),
                headers=raw_headers,
                query_params=query_params if isinstance(query_params, dict) else {},
            )
        except Exception as exc:
            with closing(self._connect()) as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "UPDATE virtual_goods_callbacks SET processed=0, last_process_error=?, processed_at=NULL WHERE id=?",
                    (f"replay_exception:{exc}", int(cb["id"])),
                )
                if cb.get("xianyu_order_id"):
                    conn.execute(
                        "UPDATE virtual_goods_orders SET callback_status='failed', last_error=?, updated_at=? WHERE xianyu_order_id=?",
                        (f"replay_exception:{exc}", self._ts(), str(cb.get("xianyu_order_id"))),
                    )
                conn.commit()
            return self._resp(
                ok=False,
                action=action,
                code="REPLAY_EXCEPTION",
                message="replay failed",
                data={"callback_id": int(cb["id"]), "target": target},
                errors=[*errors, {"code": "REPLAY_EXCEPTION", "message": str(exc)}],
                metrics={"unknown_event_kind": unknown_count},
            )

        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if cb.get("xianyu_order_id"):
                conn.execute(
                    "UPDATE virtual_goods_orders SET callback_status=?, updated_at=? WHERE xianyu_order_id=?",
                    (
                        "processed" if replay_result.get("processed") else "received",
                        self._ts(),
                        str(cb.get("xianyu_order_id")),
                    ),
                )
            conn.commit()

        return self._resp(
            ok=bool(replay_result.get("ok", False)),
            action=action,
            code="OK" if replay_result.get("ok", False) else "REPLAY_FAILED",
            message="replay completed" if replay_result.get("ok", False) else "replay completed with failure",
            data={"callback_id": int(cb["id"]), "target": target, "result": replay_result},
            metrics={"processed": 1 if replay_result.get("processed") else 0, "unknown_event_kind": unknown_count},
            errors=errors,
        )

    def replay_callback_by_event_id(self, external_event_id: str) -> dict[str, Any]:
        return self._replay(
            action="replay_callback_by_event_id", where_sql="external_event_id = ?", value=external_event_id
        )

    def replay_callback_by_dedupe_key(self, dedupe_key: str) -> dict[str, Any]:
        return self._replay(action="replay_callback_by_dedupe_key", where_sql="dedupe_key = ?", value=dedupe_key)

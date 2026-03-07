from __future__ import annotations

import json
import os
import socket
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .models import ORDER_STATUS_VALUES, normalize_order_status

FULFILLMENT_STATUS_VALUES = {"pending", "delivering", "fulfilled", "failed", "manual"}
CALLBACK_STATUS_VALUES = {"none", "received", "processed", "failed"}
CALLBACK_SOURCE_FAMILY_VALUES = {"open_platform", "virtual_supply", "unknown"}
CALLBACK_EVENT_KIND_VALUES = {"order", "refund", "voucher", "coupon", "code", "unknown"}


class VirtualGoodsStore:
    def __init__(self, db_path: str = "data/orders.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.callback_lease_ttl_sec = max(1, int(os.getenv("VG_CALLBACK_LEASE_TTL_SEC", "60") or "60"))
        stable_claimer = str(os.getenv("VG_CALLBACK_CLAIMER_ID") or "").strip()
        self.callback_claimer_id = stable_claimer or f"{socket.gethostname()}:{os.getpid()}"
        self._init_db()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _lease_expires_at(self, ttl_sec: int | None = None) -> str:
        ttl = self.callback_lease_ttl_sec if ttl_sec is None else max(1, int(ttl_sec))
        return (datetime.now(timezone.utc) + timedelta(seconds=ttl)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def _init_db(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS virtual_goods_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    xianyu_product_id TEXT NOT NULL UNIQUE,
                    supply_goods_no TEXT,
                    supply_type TEXT,
                    delivery_mode TEXT,
                    price_policy_json TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS virtual_goods_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    xianyu_order_id TEXT NOT NULL UNIQUE,
                    xianyu_product_id TEXT,
                    supply_order_no TEXT UNIQUE,
                    session_id TEXT,
                    order_status TEXT NOT NULL,
                    fulfillment_status TEXT NOT NULL DEFAULT 'pending',
                    callback_status TEXT NOT NULL DEFAULT 'none',
                    manual_takeover INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK(order_status IN ('pending_payment','paid_waiting_delivery','delivered','delivery_failed','refund_pending','refunded','closed')),
                    CHECK(fulfillment_status IN ('pending','delivering','fulfilled','failed','manual')),
                    CHECK(callback_status IN ('none','received','processed','failed'))
                );

                CREATE TABLE IF NOT EXISTS virtual_goods_callbacks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    callback_type TEXT NOT NULL,
                    source_family TEXT NOT NULL DEFAULT 'unknown' CHECK(source_family IN ('open_platform','virtual_supply','unknown')),
                    event_kind TEXT NOT NULL DEFAULT 'unknown' CHECK(event_kind IN ('order','refund','voucher','coupon','code','unknown')),
                    external_event_id TEXT UNIQUE,
                    dedupe_key TEXT,
                    xianyu_order_id TEXT,
                    payload_json TEXT NOT NULL,
                    raw_body TEXT NOT NULL,
                    headers_json TEXT,
                    signature TEXT,
                    verify_passed INTEGER NOT NULL DEFAULT 0,
                    verify_error TEXT,
                    processed INTEGER NOT NULL DEFAULT 0,
                    processed_at TEXT,
                    claimed_by TEXT,
                    claimed_at TEXT,
                    claim_expires_at TEXT,
                    last_process_error TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS virtual_goods_manual_takeover_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    xianyu_order_id TEXT NOT NULL,
                    enabled INTEGER NOT NULL CHECK(enabled IN (0, 1)),
                    reason TEXT,
                    operator TEXT,
                    detail_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS virtual_goods_order_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    xianyu_order_id TEXT,
                    event_type TEXT NOT NULL,
                    event_kind TEXT NOT NULL,
                    callback_id INTEGER,
                    from_status TEXT,
                    to_status TEXT,
                    result TEXT,
                    error_code TEXT,
                    is_exception INTEGER NOT NULL DEFAULT 0 CHECK(is_exception IN (0, 1)),
                    detail_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS listing_product_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    xianyu_product_id TEXT NOT NULL UNIQUE,
                    internal_listing_id TEXT,
                    supply_goods_no TEXT,
                    mapping_status TEXT NOT NULL,
                    last_sync_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK(mapping_status IN ('unmapped','mapped','syncing','failed','disabled'))
                );

                CREATE TABLE IF NOT EXISTS ops_funnel_stage_daily (
                    stat_date TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    xianyu_product_id TEXT NOT NULL DEFAULT '',
                    xianyu_listing_id TEXT NOT NULL DEFAULT '',
                    metric_count INTEGER NOT NULL DEFAULT 0 CHECK(metric_count >= 0),
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (stat_date, stage, xianyu_product_id, xianyu_listing_id)
                );

                CREATE TABLE IF NOT EXISTS ops_item_daily_snapshot (
                    stat_date TEXT NOT NULL,
                    xianyu_product_id TEXT NOT NULL DEFAULT '',
                    xianyu_listing_id TEXT NOT NULL DEFAULT '',
                    exposure_count INTEGER NOT NULL DEFAULT 0 CHECK(exposure_count >= 0),
                    paid_order_count INTEGER NOT NULL DEFAULT 0 CHECK(paid_order_count >= 0),
                    paid_amount_cents INTEGER NOT NULL DEFAULT 0 CHECK(paid_amount_cents >= 0),
                    refund_order_count INTEGER NOT NULL DEFAULT 0 CHECK(refund_order_count >= 0),
                    exception_count INTEGER NOT NULL DEFAULT 0 CHECK(exception_count >= 0),
                    manual_takeover_count INTEGER NOT NULL DEFAULT 0 CHECK(manual_takeover_count >= 0),
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (stat_date, xianyu_product_id, xianyu_listing_id)
                );

                CREATE TABLE IF NOT EXISTS ops_exception_pool (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    xianyu_order_id TEXT,
                    event_kind TEXT NOT NULL,
                    exception_code TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'P2' CHECK(severity IN ('P0','P1','P2','P3')),
                    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','investigating','resolved','ignored')),
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    occurrence_count INTEGER NOT NULL DEFAULT 1 CHECK(occurrence_count >= 1),
                    detail_json TEXT,
                    resolved_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ops_exception_transition_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exception_id INTEGER NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    operator TEXT,
                    reason TEXT,
                    detail_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ops_fulfillment_eff_daily (
                    stat_date TEXT NOT NULL,
                    xianyu_product_id TEXT NOT NULL DEFAULT '',
                    xianyu_listing_id TEXT NOT NULL DEFAULT '',
                    total_orders INTEGER NOT NULL DEFAULT 0 CHECK(total_orders >= 0),
                    fulfilled_orders INTEGER NOT NULL DEFAULT 0 CHECK(fulfilled_orders >= 0),
                    failed_orders INTEGER NOT NULL DEFAULT 0 CHECK(failed_orders >= 0),
                    avg_fulfillment_seconds INTEGER NOT NULL DEFAULT 0 CHECK(avg_fulfillment_seconds >= 0),
                    p95_fulfillment_seconds INTEGER NOT NULL DEFAULT 0 CHECK(p95_fulfillment_seconds >= 0),
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (stat_date, xianyu_product_id, xianyu_listing_id)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_vg_callbacks_dedupe_no_event
                ON virtual_goods_callbacks(dedupe_key)
                WHERE external_event_id IS NULL AND dedupe_key IS NOT NULL;

                CREATE INDEX IF NOT EXISTS idx_vg_products_enabled_updated
                ON virtual_goods_products(enabled, updated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_vg_orders_status_updated
                ON virtual_goods_orders(order_status, updated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_vg_orders_callback_status_updated
                ON virtual_goods_orders(callback_status, updated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_vg_callbacks_order_created
                ON virtual_goods_callbacks(xianyu_order_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_vg_callbacks_claim_expires_at
                ON virtual_goods_callbacks(claim_expires_at);

                CREATE INDEX IF NOT EXISTS idx_vg_manual_takeover_events_order_created
                ON virtual_goods_manual_takeover_events(xianyu_order_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_vg_order_events_order_created
                ON virtual_goods_order_events(xianyu_order_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_vg_order_events_exception_created
                ON virtual_goods_order_events(is_exception, created_at DESC);

                CREATE UNIQUE INDEX IF NOT EXISTS idx_lpm_internal_listing_id
                ON listing_product_mappings(internal_listing_id)
                WHERE internal_listing_id IS NOT NULL;

                CREATE INDEX IF NOT EXISTS idx_lpm_mapping_status_updated
                ON listing_product_mappings(mapping_status, updated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_lpm_supply_goods_no_updated
                ON listing_product_mappings(supply_goods_no, updated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_ops_funnel_stage_date
                ON ops_funnel_stage_daily(stage, stat_date DESC);

                CREATE INDEX IF NOT EXISTS idx_ops_item_snapshot_date
                ON ops_item_daily_snapshot(stat_date DESC);

                CREATE INDEX IF NOT EXISTS idx_ops_exception_pool_priority
                ON ops_exception_pool(status, severity, last_seen_at DESC);

                CREATE INDEX IF NOT EXISTS idx_ops_exception_pool_order
                ON ops_exception_pool(xianyu_order_id, last_seen_at DESC);

                CREATE INDEX IF NOT EXISTS idx_ops_exception_transition_exception_created
                ON ops_exception_transition_log(exception_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_ops_fulfillment_eff_date
                ON ops_fulfillment_eff_daily(stat_date DESC);
                """
            )

    def upsert_order(
        self,
        *,
        xianyu_order_id: str,
        xianyu_product_id: str = "",
        supply_order_no: str | None = None,
        session_id: str = "",
        order_status: str,
        fulfillment_status: str = "pending",
        callback_status: str = "none",
        manual_takeover: bool = False,
        last_error: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        normalized_order_status = normalize_order_status(order_status)
        normalized_fulfillment = str(fulfillment_status or "pending").lower()
        normalized_callback = str(callback_status or "none").lower()
        if normalized_order_status not in ORDER_STATUS_VALUES:
            raise ValueError(f"Unsupported virtual_goods order status: {order_status}")
        if normalized_fulfillment not in FULFILLMENT_STATUS_VALUES:
            raise ValueError(f"Unsupported fulfillment status: {fulfillment_status}")
        if normalized_callback not in CALLBACK_STATUS_VALUES:
            raise ValueError(f"Unsupported callback status: {callback_status}")

        if conn is None:
            with closing(self._connect()) as local_conn, local_conn:
                return self.upsert_order(
                    xianyu_order_id=xianyu_order_id,
                    xianyu_product_id=xianyu_product_id,
                    supply_order_no=supply_order_no,
                    session_id=session_id,
                    order_status=normalized_order_status,
                    fulfillment_status=normalized_fulfillment,
                    callback_status=normalized_callback,
                    manual_takeover=manual_takeover,
                    last_error=last_error,
                    conn=local_conn,
                )

        conn.execute(
            """
            INSERT INTO virtual_goods_orders(
                xianyu_order_id, xianyu_product_id, supply_order_no, session_id,
                order_status, fulfillment_status, callback_status, manual_takeover,
                last_error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(xianyu_order_id) DO UPDATE SET
                xianyu_product_id=excluded.xianyu_product_id,
                supply_order_no=COALESCE(excluded.supply_order_no, virtual_goods_orders.supply_order_no),
                session_id=excluded.session_id,
                order_status=excluded.order_status,
                fulfillment_status=excluded.fulfillment_status,
                callback_status=excluded.callback_status,
                manual_takeover=excluded.manual_takeover,
                last_error=excluded.last_error,
                updated_at=excluded.updated_at
            """,
            (
                xianyu_order_id,
                xianyu_product_id,
                supply_order_no,
                session_id,
                normalized_order_status,
                normalized_fulfillment,
                normalized_callback,
                1 if manual_takeover else 0,
                last_error,
                now,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM virtual_goods_orders WHERE xianyu_order_id=?", (xianyu_order_id,)).fetchone()
        return dict(row) if row else {}

    @staticmethod
    def _infer_source_family(callback_type: str) -> str:
        ctype = str(callback_type or "").strip().lower()
        if ctype in {"order", "refund"}:
            return "open_platform"
        if ctype in {"voucher", "coupon", "code"}:
            return "virtual_supply"
        return "unknown"

    @staticmethod
    def _infer_event_kind(callback_type: str) -> str:
        ctype = str(callback_type or "").strip().lower()
        return ctype if ctype in CALLBACK_EVENT_KIND_VALUES else "unknown"

    def insert_callback(
        self,
        *,
        callback_type: str,
        external_event_id: str | None,
        dedupe_key: str | None,
        xianyu_order_id: str | None,
        payload: dict[str, Any],
        raw_body: str,
        headers: dict[str, Any],
        signature: str,
        verify_passed: bool,
        verify_error: str = "",
        source_family: str | None = None,
        event_kind: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> tuple[int, bool]:
        normalized_external_event_id = (
            str(external_event_id).strip() if external_event_id is not None and str(external_event_id).strip() else None
        )
        normalized_dedupe_key = str(dedupe_key).strip() if dedupe_key is not None and str(dedupe_key).strip() else None
        if normalized_external_event_id is None and normalized_dedupe_key is None:
            raise ValueError("insert_callback requires external_event_id or dedupe_key")

        normalized_source_family = str(source_family or self._infer_source_family(callback_type)).strip().lower()
        normalized_event_kind_raw = str(event_kind or self._infer_event_kind(callback_type)).strip().lower()
        if normalized_source_family not in CALLBACK_SOURCE_FAMILY_VALUES:
            raise ValueError(f"Unsupported source_family: {source_family}")

        unknown_event_kind = normalized_event_kind_raw not in CALLBACK_EVENT_KIND_VALUES
        normalized_event_kind = normalized_event_kind_raw if not unknown_event_kind else "unknown"
        now = self._now()

        if conn is None:
            with closing(self._connect()) as local_conn, local_conn:
                return self.insert_callback(
                    callback_type=callback_type,
                    external_event_id=normalized_external_event_id,
                    dedupe_key=normalized_dedupe_key,
                    xianyu_order_id=xianyu_order_id,
                    payload=payload,
                    raw_body=raw_body,
                    headers=headers,
                    signature=signature,
                    verify_passed=verify_passed,
                    verify_error=verify_error,
                    source_family=normalized_source_family,
                    event_kind=normalized_event_kind_raw,
                    conn=local_conn,
                )

        try:
            cur = conn.execute(
                """
                INSERT INTO virtual_goods_callbacks(
                    callback_type, source_family, event_kind,
                    external_event_id, dedupe_key, xianyu_order_id,
                    payload_json, raw_body, headers_json, signature,
                    verify_passed, verify_error,
                    processed, processed_at,
                    claimed_by, claimed_at, claim_expires_at,
                    last_process_error, attempt_count,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL, NULL, NULL, NULL, 0, ?)
                """,
                (
                    callback_type,
                    normalized_source_family,
                    normalized_event_kind,
                    normalized_external_event_id,
                    normalized_dedupe_key,
                    xianyu_order_id,
                    json.dumps(payload, ensure_ascii=False),
                    raw_body,
                    json.dumps(headers, ensure_ascii=False),
                    signature,
                    1 if verify_passed else 0,
                    verify_error or None,
                    now,
                ),
            )
            callback_id = int(cur.lastrowid)
            inserted = True
        except sqlite3.IntegrityError:
            row = conn.execute(
                """
                SELECT id FROM virtual_goods_callbacks
                WHERE (external_event_id IS NOT NULL AND external_event_id = ?)
                   OR (external_event_id IS NULL AND dedupe_key = ?)
                ORDER BY id DESC LIMIT 1
                """,
                (normalized_external_event_id, normalized_dedupe_key),
            ).fetchone()
            callback_id = int(row["id"]) if row else 0
            inserted = False

        if unknown_event_kind:
            detail = {"callback_type": callback_type, "event_kind": normalized_event_kind_raw}
            self.record_order_event(
                xianyu_order_id=xianyu_order_id,
                event_type="callback_event_kind_unknown",
                event_kind=normalized_event_kind_raw or "unknown",
                callback_id=callback_id or None,
                result="ignored_kind",
                error_code="unknown_event_kind",
                is_exception=True,
                detail=detail,
                conn=conn,
            )
            self.record_ops_exception(
                xianyu_order_id=xianyu_order_id,
                event_kind=normalized_event_kind_raw or "unknown",
                exception_code="unknown_event_kind",
                severity="P1",
                detail=detail,
                conn=conn,
            )

        return callback_id, inserted

    def claim_callback_lease(
        self,
        callback_id: int,
        *,
        processed: bool | None = None,
        claimer_id: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> bool:
        now = self._now()
        expires_at = self._lease_expires_at()
        effective_claimer = str(claimer_id or self.callback_claimer_id).strip() or self.callback_claimer_id

        processed_filter = "" if processed is None else " AND processed = ?"
        params: list[Any] = [effective_claimer, now, expires_at, int(callback_id), now]
        if processed is not None:
            params.append(1 if processed else 0)

        if conn is None:
            with closing(self._connect()) as local_conn, local_conn:
                return self.claim_callback_lease(
                    callback_id=callback_id,
                    processed=processed,
                    claimer_id=claimer_id,
                    conn=local_conn,
                )

        updated = conn.execute(
            f"""
            UPDATE virtual_goods_callbacks
            SET claimed_by = ?,
                claimed_at = ?,
                claim_expires_at = ?,
                attempt_count = attempt_count + 1,
                last_process_error = NULL
            WHERE id = ?
              AND verify_passed = 1
              AND (claim_expires_at IS NULL OR claim_expires_at <= ?)
              {processed_filter}
            """,
            tuple(params),
        )
        return updated.rowcount == 1

    def reclaim_callback_lease(self, callback_id: int, *, claimer_id: str | None = None) -> bool:
        effective_claimer = str(claimer_id or self.callback_claimer_id).strip() or self.callback_claimer_id
        with closing(self._connect()) as conn, conn:
            updated = conn.execute(
                """
                UPDATE virtual_goods_callbacks
                SET claim_expires_at = NULL,
                    claimed_at = NULL,
                    claimed_by = NULL
                WHERE id = ?
                  AND (claimed_by IS NULL OR claimed_by = ?)
                """,
                (int(callback_id), effective_claimer),
            )
            return updated.rowcount == 1

    def claim_callback(self, *, processed: bool = False, claimer_id: str | None = None) -> dict[str, Any] | None:
        now = self._now()
        expires_at = self._lease_expires_at()
        effective_claimer = str(claimer_id or self.callback_claimer_id).strip() or self.callback_claimer_id

        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT id
                FROM virtual_goods_callbacks
                WHERE processed = ?
                  AND verify_passed = 1
                  AND (claim_expires_at IS NULL OR claim_expires_at <= ?)
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """,
                (1 if processed else 0, now),
            ).fetchone()
            if not row:
                conn.commit()
                return None

            callback_id = int(row["id"])
            updated = conn.execute(
                """
                UPDATE virtual_goods_callbacks
                SET claimed_by = ?,
                    claimed_at = ?,
                    claim_expires_at = ?,
                    attempt_count = attempt_count + 1,
                    last_process_error = NULL
                WHERE id = ?
                  AND verify_passed = 1
                  AND processed = ?
                  AND (claim_expires_at IS NULL OR claim_expires_at <= ?)
                """,
                (effective_claimer, now, expires_at, callback_id, 1 if processed else 0, now),
            )
            if updated.rowcount != 1:
                conn.commit()
                return None

            claimed = conn.execute("SELECT * FROM virtual_goods_callbacks WHERE id=?", (callback_id,)).fetchone()
            conn.commit()
            return dict(claimed) if claimed else None

    def mark_callback_processed(
        self,
        callback_id: int,
        *,
        processed: bool = True,
        last_process_error: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        processed_at = self._now() if processed else None
        if conn is None:
            with closing(self._connect()) as local_conn, local_conn:
                self.mark_callback_processed(
                    callback_id=callback_id,
                    processed=processed,
                    last_process_error=last_process_error,
                    conn=local_conn,
                )
                return

        conn.execute(
            """
            UPDATE virtual_goods_callbacks
            SET processed = ?,
                processed_at = ?,
                last_process_error = ?,
                claim_expires_at = NULL,
                claimed_at = NULL,
                claimed_by = NULL
            WHERE id = ?
            """,
            (
                1 if processed else 0,
                processed_at,
                (last_process_error or None),
                int(callback_id),
            ),
        )

    def record_manual_takeover_event(
        self,
        *,
        xianyu_order_id: str,
        enabled: bool,
        reason: str | None = None,
        operator: str | None = None,
        detail: dict[str, Any] | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        now = self._now()
        if conn is None:
            with closing(self._connect()) as local_conn, local_conn:
                return self.record_manual_takeover_event(
                    xianyu_order_id=xianyu_order_id,
                    enabled=enabled,
                    reason=reason,
                    operator=operator,
                    detail=detail,
                    conn=local_conn,
                )

        cur = conn.execute(
            """
            INSERT INTO virtual_goods_manual_takeover_events(
                xianyu_order_id, enabled, reason, operator, detail_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                xianyu_order_id,
                1 if enabled else 0,
                reason,
                operator,
                json.dumps(detail or {}, ensure_ascii=False),
                now,
            ),
        )
        return int(cur.lastrowid)

    def set_manual_takeover(
        self,
        xianyu_order_id: str,
        enabled: bool,
        *,
        reason: str | None = None,
        operator: str | None = None,
        detail: dict[str, Any] | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> bool:
        now = self._now()
        if conn is None:
            with closing(self._connect()) as local_conn, local_conn:
                return self.set_manual_takeover(
                    xianyu_order_id=xianyu_order_id,
                    enabled=enabled,
                    reason=reason,
                    operator=operator,
                    detail=detail,
                    conn=local_conn,
                )

        cur = conn.execute(
            "UPDATE virtual_goods_orders SET manual_takeover=?, updated_at=? WHERE xianyu_order_id=?",
            (1 if enabled else 0, now, xianyu_order_id),
        )
        if cur.rowcount > 0:
            self.record_manual_takeover_event(
                xianyu_order_id=xianyu_order_id,
                enabled=enabled,
                reason=reason,
                operator=operator,
                detail=detail,
                conn=conn,
            )
        return cur.rowcount > 0

    def record_order_event(
        self,
        *,
        event_type: str,
        event_kind: str,
        xianyu_order_id: str | None = None,
        callback_id: int | None = None,
        from_status: str | None = None,
        to_status: str | None = None,
        result: str | None = None,
        error_code: str | None = None,
        is_exception: bool = False,
        detail: dict[str, Any] | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        now = self._now()
        if conn is None:
            with closing(self._connect()) as local_conn, local_conn:
                return self.record_order_event(
                    event_type=event_type,
                    event_kind=event_kind,
                    xianyu_order_id=xianyu_order_id,
                    callback_id=callback_id,
                    from_status=from_status,
                    to_status=to_status,
                    result=result,
                    error_code=error_code,
                    is_exception=is_exception,
                    detail=detail,
                    conn=local_conn,
                )

        cur = conn.execute(
            """
            INSERT INTO virtual_goods_order_events(
                xianyu_order_id, event_type, event_kind, callback_id,
                from_status, to_status, result, error_code,
                is_exception, detail_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                xianyu_order_id,
                event_type,
                event_kind,
                callback_id,
                from_status,
                to_status,
                result,
                error_code,
                1 if is_exception else 0,
                json.dumps(detail or {}, ensure_ascii=False),
                now,
            ),
        )
        return int(cur.lastrowid)

    def upsert_listing_product_mapping(
        self,
        *,
        xianyu_product_id: str,
        internal_listing_id: str | None = None,
        supply_goods_no: str | None = None,
        mapping_status: str = "unmapped",
        last_sync_at: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        product_id = str(xianyu_product_id or "").strip()
        listing_id = str(internal_listing_id or "").strip() or None
        supply_no = str(supply_goods_no or "").strip() or None
        status = str(mapping_status or "unmapped").strip().lower()
        if status not in {"unmapped", "mapped", "syncing", "failed", "disabled"}:
            raise ValueError(f"Unsupported mapping status: {mapping_status}")
        if not product_id:
            raise ValueError("xianyu_product_id is required")
        now = self._now()

        if conn is None:
            with closing(self._connect()) as local_conn, local_conn:
                return self.upsert_listing_product_mapping(
                    xianyu_product_id=product_id,
                    internal_listing_id=listing_id,
                    supply_goods_no=supply_no,
                    mapping_status=status,
                    last_sync_at=last_sync_at,
                    conn=local_conn,
                )

        conn.execute(
            """
            INSERT INTO listing_product_mappings(
                xianyu_product_id, internal_listing_id, supply_goods_no,
                mapping_status, last_sync_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(xianyu_product_id) DO UPDATE SET
                internal_listing_id=excluded.internal_listing_id,
                supply_goods_no=excluded.supply_goods_no,
                mapping_status=excluded.mapping_status,
                last_sync_at=excluded.last_sync_at,
                updated_at=excluded.updated_at
            """,
            (product_id, listing_id, supply_no, status, last_sync_at, now, now),
        )
        row = conn.execute(
            "SELECT * FROM listing_product_mappings WHERE xianyu_product_id=?",
            (product_id,),
        ).fetchone()
        return dict(row) if row else {}

    def get_listing_product_mapping(
        self,
        *,
        xianyu_product_id: str | None = None,
        internal_listing_id: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        product_id = str(xianyu_product_id or "").strip()
        listing_id = str(internal_listing_id or "").strip()
        if not product_id and not listing_id:
            raise ValueError("xianyu_product_id or internal_listing_id is required")

        if conn is None:
            with closing(self._connect()) as local_conn, local_conn:
                return self.get_listing_product_mapping(
                    xianyu_product_id=product_id or None,
                    internal_listing_id=listing_id or None,
                    conn=local_conn,
                )

        if product_id:
            row = conn.execute(
                "SELECT * FROM listing_product_mappings WHERE xianyu_product_id=?",
                (product_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM listing_product_mappings WHERE internal_listing_id=?",
                (listing_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_listing_product_mapping_by_product_id(
        self,
        *,
        xianyu_product_id: str,
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        product_id = str(xianyu_product_id or "").strip()
        if not product_id:
            raise ValueError("xianyu_product_id is required")

        return self.get_listing_product_mapping(xianyu_product_id=product_id, conn=conn)

    def get_listing_product_mapping_by_internal_id(
        self,
        *,
        internal_listing_id: str,
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        listing_id = str(internal_listing_id or "").strip()
        if not listing_id:
            raise ValueError("internal_listing_id is required")

        return self.get_listing_product_mapping(internal_listing_id=listing_id, conn=conn)

    def update_listing_mapping_status(
        self,
        *,
        xianyu_product_id: str,
        mapping_status: str,
        last_sync_at: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        product_id = str(xianyu_product_id or "").strip()
        if not product_id:
            raise ValueError("xianyu_product_id is required")

        status = str(mapping_status or "").strip().lower()
        if status not in {"unmapped", "mapped", "syncing", "failed", "disabled"}:
            raise ValueError(f"Unsupported mapping status: {mapping_status}")

        if conn is None:
            with closing(self._connect()) as local_conn, local_conn:
                return self.update_listing_mapping_status(
                    xianyu_product_id=product_id,
                    mapping_status=status,
                    last_sync_at=last_sync_at,
                    conn=local_conn,
                )

        now = self._now()
        cur = conn.execute(
            """
            UPDATE listing_product_mappings
            SET mapping_status=?,
                last_sync_at=COALESCE(?, last_sync_at),
                updated_at=?
            WHERE xianyu_product_id=?
            """,
            (status, last_sync_at, now, product_id),
        )
        if cur.rowcount <= 0:
            return None
        row = conn.execute(
            "SELECT * FROM listing_product_mappings WHERE xianyu_product_id=?",
            (product_id,),
        ).fetchone()
        return dict(row) if row else None

    def delete_listing_product_mapping(self, *, xianyu_product_id: str, conn: sqlite3.Connection | None = None) -> bool:
        product_id = str(xianyu_product_id or "").strip()
        if not product_id:
            raise ValueError("xianyu_product_id is required")

        if conn is None:
            with closing(self._connect()) as local_conn, local_conn:
                return self.delete_listing_product_mapping(xianyu_product_id=product_id, conn=local_conn)

        cur = conn.execute("DELETE FROM listing_product_mappings WHERE xianyu_product_id=?", (product_id,))
        return cur.rowcount > 0

    def record_ops_exception(
        self,
        *,
        xianyu_order_id: str | None,
        event_kind: str,
        exception_code: str,
        severity: str = "P1",
        detail: dict[str, Any] | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        now = self._now()
        sev = str(severity or "P1").upper()
        if sev not in {"P0", "P1", "P2", "P3"}:
            sev = "P2"

        if conn is None:
            with closing(self._connect()) as local_conn, local_conn:
                return self.record_ops_exception(
                    xianyu_order_id=xianyu_order_id,
                    event_kind=event_kind,
                    exception_code=exception_code,
                    severity=sev,
                    detail=detail,
                    conn=local_conn,
                )

        row = conn.execute(
            """
            SELECT id, status, occurrence_count
            FROM ops_exception_pool
            WHERE COALESCE(xianyu_order_id, '') = COALESCE(?, '')
              AND event_kind = ?
              AND exception_code = ?
              AND status != 'resolved'
            ORDER BY id DESC
            LIMIT 1
            """,
            (xianyu_order_id, event_kind, exception_code),
        ).fetchone()

        if row:
            exception_id = int(row["id"])
            previous_status = str(row["status"] or "open")
            conn.execute(
                """
                UPDATE ops_exception_pool
                SET severity=?,
                    status='open',
                    last_seen_at=?,
                    occurrence_count=occurrence_count+1,
                    detail_json=?,
                    updated_at=?
                WHERE id=?
                """,
                (sev, now, json.dumps(detail or {}, ensure_ascii=False), now, exception_id),
            )
            if previous_status != "open":
                conn.execute(
                    """
                    INSERT INTO ops_exception_transition_log(
                        exception_id, from_status, to_status, operator, reason, detail_json, created_at
                    ) VALUES (?, ?, 'open', ?, ?, ?, ?)
                    """,
                    (
                        exception_id,
                        previous_status,
                        "system",
                        "exception_reoccurred",
                        json.dumps(detail or {}, ensure_ascii=False),
                        now,
                    ),
                )
            return exception_id

        cur = conn.execute(
            """
            INSERT INTO ops_exception_pool(
                xianyu_order_id, event_kind, exception_code, severity, status,
                first_seen_at, last_seen_at, occurrence_count, detail_json,
                resolved_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'open', ?, ?, 1, ?, NULL, ?, ?)
            """,
            (
                xianyu_order_id,
                event_kind,
                exception_code,
                sev,
                now,
                now,
                json.dumps(detail or {}, ensure_ascii=False),
                now,
                now,
            ),
        )
        exception_id = int(cur.lastrowid)
        conn.execute(
            """
            INSERT INTO ops_exception_transition_log(
                exception_id, from_status, to_status, operator, reason, detail_json, created_at
            ) VALUES (?, NULL, 'open', ?, ?, ?, ?)
            """,
            (
                exception_id,
                "system",
                "exception_created",
                json.dumps(detail or {}, ensure_ascii=False),
                now,
            ),
        )
        return exception_id

    def list_order_events(
        self,
        *,
        xianyu_order_id: str | None = None,
        is_exception: bool | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if xianyu_order_id is not None:
            where.append("xianyu_order_id = ?")
            params.append(xianyu_order_id)
        if is_exception is not None:
            where.append("is_exception = ?")
            params.append(1 if is_exception else 0)

        sql = "SELECT * FROM virtual_goods_order_events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, int(limit)))

        with closing(self._connect()) as conn, conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [dict(r) for r in rows]

    def get_callback(self, callback_id: int) -> dict[str, Any] | None:
        with closing(self._connect()) as conn, conn:
            row = conn.execute("SELECT * FROM virtual_goods_callbacks WHERE id=?", (int(callback_id),)).fetchone()
            return dict(row) if row else None

    def get_order(self, xianyu_order_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT * FROM virtual_goods_orders WHERE xianyu_order_id=?", (xianyu_order_id,)
            ).fetchone()
            return dict(row) if row else None

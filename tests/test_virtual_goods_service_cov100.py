from __future__ import annotations

import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest


def _create_db(db_path: str) -> None:
    """Create tables needed by VirtualGoodsService."""
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS virtual_goods_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            xianyu_order_id TEXT UNIQUE,
            xianyu_product_id TEXT,
            xianyu_listing_id TEXT,
            order_status TEXT DEFAULT 'unknown',
            fulfillment_status TEXT DEFAULT 'pending',
            callback_status TEXT DEFAULT 'none',
            manual_takeover INTEGER DEFAULT 0,
            last_error TEXT,
            reason TEXT,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS virtual_goods_callbacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_event_id TEXT,
            dedupe_key TEXT,
            xianyu_order_id TEXT,
            source_family TEXT DEFAULT 'unknown',
            event_kind TEXT DEFAULT 'unknown',
            verify_passed INTEGER DEFAULT 0,
            processed INTEGER DEFAULT 0,
            attempt_count INTEGER DEFAULT 0,
            last_process_error TEXT,
            payload_json TEXT,
            headers_json TEXT,
            raw_body TEXT,
            claim_expires_at TEXT,
            claimed_at TEXT,
            claimed_by TEXT,
            created_at TEXT,
            processed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS ops_exception_pool (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            xianyu_order_id TEXT,
            event_kind TEXT,
            exception_code TEXT,
            severity TEXT DEFAULT 'P2',
            status TEXT DEFAULT 'open',
            first_seen_at TEXT,
            last_seen_at TEXT,
            occurrence_count INTEGER DEFAULT 1,
            detail_json TEXT,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS ops_funnel_stage_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stat_date TEXT,
            stage TEXT,
            xianyu_product_id TEXT,
            xianyu_listing_id TEXT,
            metric_count INTEGER DEFAULT 0,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS ops_item_daily_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stat_date TEXT,
            xianyu_product_id TEXT,
            xianyu_listing_id TEXT,
            exposure_count INTEGER DEFAULT 0,
            paid_order_count INTEGER DEFAULT 0,
            paid_amount_cents INTEGER DEFAULT 0,
            refund_order_count INTEGER DEFAULT 0,
            exception_count INTEGER DEFAULT 0,
            manual_takeover_count INTEGER DEFAULT 0,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS ops_fulfillment_eff_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stat_date TEXT,
            xianyu_product_id TEXT,
            xianyu_listing_id TEXT,
            total_orders INTEGER DEFAULT 0,
            fulfilled_orders INTEGER DEFAULT 0,
            failed_orders INTEGER DEFAULT 0,
            avg_fulfillment_seconds INTEGER DEFAULT 0,
            p95_fulfillment_seconds INTEGER DEFAULT 0,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS listing_product_mapping (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            xianyu_product_id TEXT UNIQUE,
            internal_listing_id TEXT,
            supply_goods_no TEXT,
            mapping_status TEXT DEFAULT 'unmapped',
            last_sync_at TEXT,
            created_at TEXT,
            updated_at TEXT
        );
    """)
    conn.close()


def _make_service(db_path: str):
    with patch("src.modules.virtual_goods.store.VirtualGoodsStore._init_db"):
        from src.modules.virtual_goods.service import VirtualGoodsService
        svc = VirtualGoodsService(db_path=db_path, config={})
    _create_db(db_path)
    return svc


@pytest.fixture
def db_path(tmp_path):
    p = str(tmp_path / "test_vg.db")
    return p


@pytest.fixture
def service(db_path):
    return _make_service(db_path)


class TestStaticHelpers:
    def test_loads_json_valid(self):
        from src.modules.virtual_goods.service import VirtualGoodsService
        assert VirtualGoodsService._loads_json('{"a":1}', {}) == {"a": 1}

    def test_loads_json_invalid(self):
        from src.modules.virtual_goods.service import VirtualGoodsService
        assert VirtualGoodsService._loads_json("not json", "fb") == "fb"

    def test_loads_json_not_string(self):
        from src.modules.virtual_goods.service import VirtualGoodsService
        assert VirtualGoodsService._loads_json(123, "fb") == "fb"

    def test_loads_json_empty(self):
        from src.modules.virtual_goods.service import VirtualGoodsService
        assert VirtualGoodsService._loads_json("", "fb") == "fb"

    def test_to_int_valid(self):
        from src.modules.virtual_goods.service import VirtualGoodsService
        assert VirtualGoodsService._to_int("42") == 42

    def test_to_int_invalid(self):
        from src.modules.virtual_goods.service import VirtualGoodsService
        assert VirtualGoodsService._to_int("abc", 5) == 5

    def test_to_float_valid(self):
        from src.modules.virtual_goods.service import VirtualGoodsService
        assert VirtualGoodsService._to_float("3.14") == 3.14

    def test_to_float_invalid(self):
        from src.modules.virtual_goods.service import VirtualGoodsService
        assert VirtualGoodsService._to_float("abc", 1.0) == 1.0


class TestListTimeoutBacklog:
    def test_empty(self, service):
        result = service.list_timeout_backlog()
        assert result["ok"] is True
        assert result["data"]["items"] == []

    def test_with_timed_out_callbacks(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT INTO virtual_goods_callbacks
            (xianyu_order_id, event_kind, verify_passed, processed, created_at,
             external_event_id, dedupe_key, source_family, payload_json, headers_json, attempt_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("order1", "order", 1, 0, "2020-01-01T00:00:00Z",
             "evt1", "dk1", "open_platform", '{}', '{}', 0),
        )
        conn.commit()
        conn.close()
        result = service.list_timeout_backlog(timeout_seconds=1)
        assert result["ok"] is True
        assert len(result["data"]["items"]) == 1
        assert result["data"]["items"][0]["age_seconds"] > 0

    def test_with_unknown_event_kind(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT INTO virtual_goods_callbacks
            (xianyu_order_id, event_kind, verify_passed, processed, created_at,
             external_event_id, dedupe_key, source_family, payload_json, headers_json, attempt_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("order2", "unknown", 1, 0, "2020-01-01T00:00:00Z",
             "evt2", "dk2", "unknown", '{}', '{}', 0),
        )
        conn.commit()
        conn.close()
        result = service.list_timeout_backlog(timeout_seconds=1)
        assert result["metrics"]["unknown_event_kind"] > 0
        assert any(e["code"] == "UNKNOWN_EVENT_KIND" for e in result["errors"])


class TestListReplayCandidates:
    def test_empty(self, service):
        result = service.list_replay_candidates()
        assert result["ok"] is True
        assert result["data"]["items"] == []

    def test_with_unprocessed(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT INTO virtual_goods_callbacks
            (xianyu_order_id, event_kind, verify_passed, processed, created_at,
             external_event_id, dedupe_key, source_family, payload_json, headers_json, attempt_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("order1", "order", 1, 0, "2025-01-01T00:00:00Z",
             "evt1", "dk1", "open_platform", '{}', '{}', 0),
        )
        conn.commit()
        conn.close()
        result = service.list_replay_candidates()
        assert len(result["data"]["items"]) == 1

    def test_with_unknown_event_kind(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT INTO virtual_goods_callbacks
            (xianyu_order_id, event_kind, verify_passed, processed, created_at,
             external_event_id, dedupe_key, source_family, payload_json, headers_json, attempt_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("order2", "unknown", 1, 0, "2025-01-01T00:00:00Z",
             "evt2", "dk2", "unknown", '{}', '{}', 0),
        )
        conn.commit()
        conn.close()
        result = service.list_replay_candidates()
        assert any(e["code"] == "UNKNOWN_EVENT_KIND" for e in result["errors"])


class TestListManualTakeoverOrders:
    def test_empty(self, service):
        result = service.list_manual_takeover_orders()
        assert result["ok"] is True
        assert result["data"]["items"] == []

    def test_with_orders(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO virtual_goods_orders (xianyu_order_id, manual_takeover, updated_at) VALUES (?, ?, ?)",
            ("order1", 1, "2025-01-01T00:00:00Z"),
        )
        conn.commit()
        conn.close()
        result = service.list_manual_takeover_orders()
        assert len(result["data"]["items"]) == 1


class TestGetDashboardMetrics:
    def test_empty_db(self, service):
        result = service.get_dashboard_metrics()
        assert result["ok"] is True
        assert result["data"]["total_orders"] == 0

    def test_with_data(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO virtual_goods_orders (xianyu_order_id, manual_takeover, updated_at) VALUES (?, ?, ?)",
            ("order1", 1, "2025-01-01T00:00:00Z"),
        )
        conn.execute(
            """INSERT INTO virtual_goods_callbacks
            (xianyu_order_id, event_kind, verify_passed, processed, created_at,
             external_event_id, dedupe_key, source_family, payload_json, headers_json, attempt_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("order1", "unknown", 1, 0, "2020-01-01T00:00:00Z",
             "evt1", "dk1", "unknown", '{}', '{}', 0),
        )
        conn.commit()
        conn.close()
        result = service.get_dashboard_metrics(timeout_seconds=1)
        assert result["ok"] is True
        assert result["data"]["total_orders"] == 1
        assert result["data"]["unknown_event_kind"] > 0
        assert any(e["code"] == "UNKNOWN_EVENT_KIND" for e in result["errors"])


class TestInspectOrder:
    def test_missing_order_id(self, service):
        result = service.inspect_order()
        assert result["ok"] is False
        assert result["code"] == "BAD_REQUEST"

    def test_not_found(self, service):
        result = service.inspect_order("nonexistent")
        assert result["ok"] is False
        assert result["code"] == "NOT_FOUND"

    def test_found_with_callbacks(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO virtual_goods_orders (xianyu_order_id, fulfillment_status, updated_at) VALUES (?, ?, ?)",
            ("order1", "pending", "2025-01-01T00:00:00Z"),
        )
        conn.execute(
            """INSERT INTO virtual_goods_callbacks
            (xianyu_order_id, event_kind, verify_passed, processed, attempt_count, created_at,
             external_event_id, dedupe_key, source_family, payload_json, headers_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("order1", "order", 1, 1, 1, "2025-01-01T00:00:00Z",
             "evt1", "dk1", "open_platform", '{"k":"v"}', '{"h":"v"}'),
        )
        conn.commit()
        conn.close()

        result = service.inspect_order("order1")
        assert result["ok"] is True
        assert result["data"]["xianyu_order_id"] == "order1"

    def test_found_with_unknown_event_kind(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO virtual_goods_orders (xianyu_order_id, updated_at) VALUES (?, ?)",
            ("order2", "2025-01-01T00:00:00Z"),
        )
        conn.execute(
            """INSERT INTO virtual_goods_callbacks
            (xianyu_order_id, event_kind, verify_passed, processed, created_at,
             external_event_id, dedupe_key, source_family, payload_json, headers_json, attempt_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("order2", "unknown", 1, 0, "2025-01-01T00:00:00Z",
             "evt2", "dk2", "unknown", '{}', '{}', 0),
        )
        conn.commit()
        conn.close()

        result = service.inspect_order("order2")
        assert result["ok"] is True
        assert result["metrics"]["unknown_event_kind"] > 0

    def test_with_exceptions(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO virtual_goods_orders (xianyu_order_id, updated_at) VALUES (?, ?)",
            ("order3", "2025-01-01T00:00:00Z"),
        )
        conn.execute(
            """INSERT INTO ops_exception_pool
            (xianyu_order_id, event_kind, exception_code, severity, status,
             first_seen_at, last_seen_at, occurrence_count, detail_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("order3", "order", "DUPLICATE_ORDER", "P1", "open",
             "2025-01-01T00:00:00Z", "2025-01-01T01:00:00Z", 3,
             '{"detail":"test"}', "2025-01-01T00:00:00Z", "2025-01-01T01:00:00Z"),
        )
        conn.commit()
        conn.close()

        result = service.inspect_order("order3")
        assert result["ok"] is True
        pool = result["data"]["exception_priority_pool"]
        assert pool["total_items"] > 0


class TestGetFunnelMetrics:
    def test_no_data(self, service):
        result = service.get_funnel_metrics()
        assert result["ok"] is True
        assert result["data"]["items"] == []

    def test_with_date_range(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO ops_funnel_stage_daily (stat_date, stage, metric_count) VALUES (?, ?, ?)",
            ("2025-01-01", "payment", 10),
        )
        conn.commit()
        conn.close()

        result = service.get_funnel_metrics(start_date="2025-01-01", end_date="2025-01-02")
        assert result["ok"] is True
        assert len(result["data"]["items"]) == 1

    def test_unknown_event_kind_in_exception_pool(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT INTO ops_exception_pool
            (exception_code, status, severity) VALUES (?, ?, ?)""",
            ("unknown_event_kind", "open", "P0"),
        )
        conn.commit()
        conn.close()

        result = service.get_funnel_metrics()
        assert any(e["code"] == "UNKNOWN_EVENT_KIND" for e in result["errors"])


class TestGetProductOperationMetrics:
    def test_no_data(self, service):
        result = service.get_product_operation_metrics()
        assert result["ok"] is True
        assert result["data"]["summary"]["conversion_rate_pct"] == 0.0

    def test_with_data(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT INTO ops_item_daily_snapshot
            (stat_date, xianyu_product_id, exposure_count, paid_order_count,
             paid_amount_cents, refund_order_count, exception_count, manual_takeover_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("2025-01-01", "prod1", 100, 10, 5000, 1, 0, 0),
        )
        conn.commit()
        conn.close()

        result = service.get_product_operation_metrics(
            start_date="2025-01-01", end_date="2025-01-02", xianyu_product_id="prod1"
        )
        assert result["ok"] is True
        assert result["data"]["summary"]["conversion_rate_pct"] > 0

    def test_unknown_event_kind(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO ops_exception_pool (exception_code, status, severity) VALUES (?, ?, ?)",
            ("unknown_event_kind", "open", "P0"),
        )
        conn.commit()
        conn.close()

        result = service.get_product_operation_metrics()
        assert any(e["code"] == "UNKNOWN_EVENT_KIND" for e in result["errors"])


class TestGetFulfillmentEfficiencyMetrics:
    def test_no_data(self, service):
        result = service.get_fulfillment_efficiency_metrics()
        assert result["ok"] is True
        assert result["data"]["summary"]["fulfillment_rate_pct"] == 0.0

    def test_with_data(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT INTO ops_fulfillment_eff_daily
            (stat_date, xianyu_product_id, total_orders, fulfilled_orders, failed_orders,
             avg_fulfillment_seconds, p95_fulfillment_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("2025-01-01", "prod1", 100, 90, 10, 30, 120),
        )
        conn.commit()
        conn.close()

        result = service.get_fulfillment_efficiency_metrics(
            start_date="2025-01-01", end_date="2025-01-02", xianyu_product_id="prod1"
        )
        assert result["ok"] is True
        assert result["data"]["summary"]["fulfillment_rate_pct"] == 90.0

    def test_unknown_event_kind(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO ops_exception_pool (exception_code, status, severity) VALUES (?, ?, ?)",
            ("unknown_event_kind", "open", "P0"),
        )
        conn.commit()
        conn.close()

        result = service.get_fulfillment_efficiency_metrics()
        assert any(e["code"] == "UNKNOWN_EVENT_KIND" for e in result["errors"])


class TestListPriorityExceptions:
    def test_no_data(self, service):
        result = service.list_priority_exceptions()
        assert result["ok"] is True
        assert result["data"]["items"] == []

    def test_with_data(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT INTO ops_exception_pool
            (exception_code, severity, status, event_kind, occurrence_count, detail_json, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("unknown_event_kind", "P0", "open", "unknown", 5, '{"k":"v"}', "2025-01-01T00:00:00Z"),
        )
        conn.execute(
            """INSERT INTO ops_exception_pool
            (exception_code, severity, status, event_kind, occurrence_count, detail_json, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("TIMEOUT", "P5", "open", "order", 1, 'invalid', "2025-01-01T00:00:00Z"),
        )
        conn.commit()
        conn.close()

        result = service.list_priority_exceptions()
        assert result["ok"] is True
        assert len(result["data"]["items"]) == 2
        assert result["metrics"]["unknown_event_kind"] > 0


class TestSetManualTakeover:
    def test_missing_order_id(self, service):
        result = service.set_manual_takeover("", True)
        assert result["ok"] is False
        assert result["code"] == "BAD_REQUEST"

    def test_order_not_found(self, service):
        result = service.set_manual_takeover("nonexistent", True)
        assert result["ok"] is False
        assert result["code"] == "NOT_FOUND"

    def test_enable(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO virtual_goods_orders (xianyu_order_id, fulfillment_status, updated_at) VALUES (?, ?, ?)",
            ("order1", "pending", "2025-01-01T00:00:00Z"),
        )
        conn.commit()
        conn.close()

        result = service.set_manual_takeover("order1", True)
        assert result["ok"] is True
        assert result["data"]["order"]["manual_takeover"] == 1

    def test_disable(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO virtual_goods_orders (xianyu_order_id, fulfillment_status, manual_takeover, updated_at) VALUES (?, ?, ?, ?)",
            ("order2", "fulfilled", 1, "2025-01-01T00:00:00Z"),
        )
        conn.commit()
        conn.close()

        result = service.set_manual_takeover("order2", False)
        assert result["ok"] is True
        assert result["data"]["order"]["manual_takeover"] == 0


class TestUpsertListingProductMapping:
    def test_success(self, service):
        with patch.object(service.store, "upsert_listing_product_mapping", return_value={"xianyu_product_id": "p1"}):
            result = service.upsert_listing_product_mapping(xianyu_product_id="p1")
        assert result["ok"] is True

    def test_value_error(self, service):
        with patch.object(service.store, "upsert_listing_product_mapping", side_effect=ValueError("bad")):
            result = service.upsert_listing_product_mapping(xianyu_product_id="p1")
        assert result["ok"] is False
        assert result["code"] == "BAD_REQUEST"


class TestGetListingProductMapping:
    def test_found(self, service):
        with patch.object(service.store, "get_listing_product_mapping", return_value={"xianyu_product_id": "p1"}):
            result = service.get_listing_product_mapping(xianyu_product_id="p1")
        assert result["ok"] is True

    def test_not_found(self, service):
        with patch.object(service.store, "get_listing_product_mapping", return_value=None):
            result = service.get_listing_product_mapping(xianyu_product_id="p1")
        assert result["ok"] is False
        assert result["code"] == "NOT_FOUND"

    def test_value_error(self, service):
        with patch.object(service.store, "get_listing_product_mapping", side_effect=ValueError("bad")):
            result = service.get_listing_product_mapping(xianyu_product_id="p1")
        assert result["ok"] is False


class TestGetListingProductMappingByProductId:
    def test_found(self, service):
        with patch.object(service.store, "get_listing_product_mapping_by_product_id", return_value={"id": 1}):
            result = service.get_listing_product_mapping_by_product_id(xianyu_product_id="p1")
        assert result["ok"] is True

    def test_not_found(self, service):
        with patch.object(service.store, "get_listing_product_mapping_by_product_id", return_value=None):
            result = service.get_listing_product_mapping_by_product_id(xianyu_product_id="p1")
        assert result["ok"] is False

    def test_value_error(self, service):
        with patch.object(service.store, "get_listing_product_mapping_by_product_id", side_effect=ValueError("bad")):
            result = service.get_listing_product_mapping_by_product_id(xianyu_product_id="p1")
        assert result["ok"] is False


class TestGetListingProductMappingByInternalId:
    def test_found(self, service):
        with patch.object(service.store, "get_listing_product_mapping_by_internal_id", return_value={"id": 1}):
            result = service.get_listing_product_mapping_by_internal_id(internal_listing_id="lid1")
        assert result["ok"] is True

    def test_not_found(self, service):
        with patch.object(service.store, "get_listing_product_mapping_by_internal_id", return_value=None):
            result = service.get_listing_product_mapping_by_internal_id(internal_listing_id="lid1")
        assert result["ok"] is False

    def test_value_error(self, service):
        with patch.object(service.store, "get_listing_product_mapping_by_internal_id", side_effect=ValueError("bad")):
            result = service.get_listing_product_mapping_by_internal_id(internal_listing_id="lid1")
        assert result["ok"] is False


class TestUpdateListingMappingStatus:
    def test_success(self, service):
        with patch.object(service.store, "update_listing_mapping_status", return_value={"id": 1}):
            result = service.update_listing_mapping_status(xianyu_product_id="p1", mapping_status="mapped")
        assert result["ok"] is True

    def test_not_found(self, service):
        with patch.object(service.store, "update_listing_mapping_status", return_value=None):
            result = service.update_listing_mapping_status(xianyu_product_id="p1", mapping_status="mapped")
        assert result["ok"] is False

    def test_value_error(self, service):
        with patch.object(service.store, "update_listing_mapping_status", side_effect=ValueError("bad")):
            result = service.update_listing_mapping_status(xianyu_product_id="p1", mapping_status="mapped")
        assert result["ok"] is False


class TestDeleteListingProductMapping:
    def test_success(self, service):
        with patch.object(service.store, "delete_listing_product_mapping", return_value=True):
            result = service.delete_listing_product_mapping(xianyu_product_id="p1")
        assert result["ok"] is True

    def test_not_found(self, service):
        with patch.object(service.store, "delete_listing_product_mapping", return_value=False):
            result = service.delete_listing_product_mapping(xianyu_product_id="p1")
        assert result["ok"] is False

    def test_value_error(self, service):
        with patch.object(service.store, "delete_listing_product_mapping", side_effect=ValueError("bad")):
            result = service.delete_listing_product_mapping(xianyu_product_id="p1")
        assert result["ok"] is False


class TestRunTimeoutScan:
    def test_no_timed_out(self, service):
        result = service.run_timeout_scan()
        assert result["ok"] is True
        assert result["data"]["timed_out_callback_ids"] == 0

    def test_with_timed_out(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT INTO virtual_goods_callbacks
            (xianyu_order_id, event_kind, verify_passed, processed, created_at)
            VALUES (?, ?, ?, ?, ?)""",
            ("order1", "order", 1, 0, "2020-01-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO virtual_goods_orders (xianyu_order_id, updated_at) VALUES (?, ?)",
            ("order1", "2020-01-01T00:00:00Z"),
        )
        conn.commit()
        conn.close()

        result = service.run_timeout_scan(timeout_seconds=1)
        assert result["ok"] is True
        assert result["data"]["timed_out_callback_ids"] > 0
        assert len(result["data"]["affected_orders"]) > 0

    def test_unknown_event_kind_in_scan(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT INTO virtual_goods_callbacks
            (xianyu_order_id, event_kind, verify_passed, processed, created_at)
            VALUES (?, ?, ?, ?, ?)""",
            ("order2", "unknown", 1, 0, "2020-01-01T00:00:00Z"),
        )
        conn.commit()
        conn.close()

        result = service.run_timeout_scan(timeout_seconds=1)
        assert result["metrics"]["unknown_event_kind"] > 0


class TestReplay:
    def test_missing_key(self, service):
        result = service.replay_callback_by_event_id("")
        assert result["ok"] is False
        assert result["code"] == "BAD_REQUEST"

    def test_not_found(self, service):
        result = service.replay_callback_by_dedupe_key("nonexistent")
        assert result["ok"] is False
        assert result["code"] == "NOT_FOUND"

    def test_replay_success(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT INTO virtual_goods_callbacks
            (external_event_id, dedupe_key, xianyu_order_id, event_kind,
             source_family, verify_passed, processed, raw_body,
             payload_json, headers_json, created_at, attempt_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("evt1", "dk1", "order1", "order", "open_platform",
             1, 0, '{"test":true}', '{}',
             '{"query_params":{"k":"v"},"Authorization":"x"}',
             "2025-01-01T00:00:00Z", 0),
        )
        conn.execute(
            "INSERT INTO virtual_goods_orders (xianyu_order_id, updated_at) VALUES (?, ?)",
            ("order1", "2025-01-01T00:00:00Z"),
        )
        conn.commit()
        conn.close()

        with patch.object(service.callbacks, "process", return_value={"ok": True, "processed": True}):
            result = service.replay_callback_by_event_id("evt1")
        assert result["ok"] is True

    def test_replay_failed_result(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT INTO virtual_goods_callbacks
            (external_event_id, dedupe_key, xianyu_order_id, event_kind,
             source_family, verify_passed, processed, raw_body,
             payload_json, headers_json, created_at, attempt_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("evt2", "dk2", "order2", "order", "open_platform",
             1, 0, '{}', '{}', '{}',
             "2025-01-01T00:00:00Z", 0),
        )
        conn.execute(
            "INSERT INTO virtual_goods_orders (xianyu_order_id, updated_at) VALUES (?, ?)",
            ("order2", "2025-01-01T00:00:00Z"),
        )
        conn.commit()
        conn.close()

        with patch.object(service.callbacks, "process", return_value={"ok": False, "processed": False}):
            result = service.replay_callback_by_dedupe_key("dk2")
        assert result["code"] == "REPLAY_FAILED"

    def test_replay_exception(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT INTO virtual_goods_callbacks
            (external_event_id, dedupe_key, xianyu_order_id, event_kind,
             source_family, verify_passed, processed, raw_body,
             payload_json, headers_json, created_at, attempt_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("evt3", "dk3", "order3", "order", "open_platform",
             1, 0, '{}', '{}', '{}',
             "2025-01-01T00:00:00Z", 0),
        )
        conn.execute(
            "INSERT INTO virtual_goods_orders (xianyu_order_id, updated_at) VALUES (?, ?)",
            ("order3", "2025-01-01T00:00:00Z"),
        )
        conn.commit()
        conn.close()

        with patch.object(service.callbacks, "process", side_effect=RuntimeError("replay_fail")):
            result = service.replay_callback_by_event_id("evt3")
        assert result["ok"] is False
        assert result["code"] == "REPLAY_EXCEPTION"

    def test_replay_unknown_event_kind(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT INTO virtual_goods_callbacks
            (external_event_id, dedupe_key, xianyu_order_id, event_kind,
             source_family, verify_passed, processed, raw_body,
             payload_json, headers_json, created_at, attempt_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("evt4", "dk4", "", "unknown", "unknown",
             1, 0, '{}', '{}', '{}',
             "2025-01-01T00:00:00Z", 0),
        )
        conn.commit()
        conn.close()

        with patch.object(service.callbacks, "process", return_value={"ok": True, "processed": True}):
            result = service.replay_callback_by_event_id("evt4")
        assert any(e["code"] == "UNKNOWN_EVENT_KIND" for e in result["errors"])

    def test_replay_exception_no_order_id(self, service, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT INTO virtual_goods_callbacks
            (external_event_id, dedupe_key, xianyu_order_id, event_kind,
             source_family, verify_passed, processed, raw_body,
             payload_json, headers_json, created_at, attempt_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("evt5", "dk5", "", "order", "open_platform",
             1, 0, '{}', '{}', '{}',
             "2025-01-01T00:00:00Z", 0),
        )
        conn.commit()
        conn.close()

        with patch.object(service.callbacks, "process", side_effect=RuntimeError("fail")):
            result = service.replay_callback_by_event_id("evt5")
        assert result["ok"] is False

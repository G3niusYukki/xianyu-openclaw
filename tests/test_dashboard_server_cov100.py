from __future__ import annotations

import io
import json
import sqlite3
import tempfile
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_mimic_ops(project_root=None, module_console=None):
    """Create a MimicOps instance with all heavy deps mocked."""
    with patch("src.dashboard_server.get_config") as mock_cfg:
        mock_cfg.return_value = MagicMock(
            browser={"delay": {"min": 0.01, "max": 0.02}},
            database={"path": ":memory:"},
        )
        from src.dashboard_server import MimicOps
        ops = MimicOps(
            project_root=project_root or Path(tempfile.mkdtemp()),
            module_console=module_console or MagicMock(),
        )
    return ops


# ---------------------------------------------------------------------------
# _error_payload
# ---------------------------------------------------------------------------

class TestErrorPayload:
    def test_without_details(self):
        from src.dashboard_server import _error_payload
        p = _error_payload("msg", code="CODE")
        assert p["success"] is False
        assert p["error_code"] == "CODE"
        assert "details" not in p

    def test_with_details(self):
        from src.dashboard_server import _error_payload
        p = _error_payload("msg", details={"k": "v"})
        assert p["details"]["k"] == "v"


# ---------------------------------------------------------------------------
# retry_xianguanjia_delivery
# ---------------------------------------------------------------------------

class TestRetryXianguanjiaDelivery:
    def test_not_configured(self):
        ops = _make_mimic_ops()
        with patch.object(ops, "_get_xianguanjia_settings", return_value={"configured": False}):
            result = ops.retry_xianguanjia_delivery({})
        assert result["success"] is False
        assert result["error_code"] == "XGJ_NOT_CONFIGURED"

    def test_missing_order_id(self):
        ops = _make_mimic_ops()
        settings = {"configured": True, "auto_ship_enabled": True, "auto_ship_on_paid": True,
                     "app_key": "k", "app_secret": "s", "merchant_id": "m", "base_url": "u"}
        with patch.object(ops, "_get_xianguanjia_settings", return_value=settings), \
             patch.object(ops, "_xianguanjia_service_config", return_value={}):
            result = ops.retry_xianguanjia_delivery({})
        assert result["error_code"] == "MISSING_ORDER_ID"

    def test_success(self):
        ops = _make_mimic_ops()
        settings = {"configured": True, "auto_ship_enabled": True, "auto_ship_on_paid": True,
                     "app_key": "k", "app_secret": "s", "merchant_id": "m", "base_url": "u"}
        with patch.object(ops, "_get_xianguanjia_settings", return_value=settings), \
             patch.object(ops, "_xianguanjia_service_config", return_value={}), \
             patch("src.dashboard_server.MimicOps.retry_xianguanjia_delivery.__wrapped__", create=True), \
             patch("src.modules.orders.service.OrderFulfillmentService") as MockSvc:
            mock_svc = MagicMock()
            mock_svc.deliver.return_value = {"delivered": True}
            MockSvc.return_value = mock_svc
            result = ops.retry_xianguanjia_delivery({
                "order_id": "O123",
                "shipping_info": {"waybill_no": "WB123"},
                "waybill_no": "WB123",
                "express_code": "SF",
            })
        assert result["success"] is True

    def test_exception(self):
        ops = _make_mimic_ops()
        settings = {"configured": True, "auto_ship_enabled": True, "auto_ship_on_paid": True,
                     "app_key": "k", "app_secret": "s", "merchant_id": "m", "base_url": "u"}
        with patch.object(ops, "_get_xianguanjia_settings", return_value=settings), \
             patch.object(ops, "_xianguanjia_service_config", return_value={}), \
             patch("src.modules.orders.service.OrderFulfillmentService") as MockSvc:
            MockSvc.return_value.deliver.side_effect = RuntimeError("ship err")
            result = ops.retry_xianguanjia_delivery({"order_id": "O123"})
        assert result["error_code"] == "XGJ_RETRY_SHIP_FAILED"

    def test_shipping_info_not_dict(self):
        ops = _make_mimic_ops()
        settings = {"configured": True, "auto_ship_enabled": True, "auto_ship_on_paid": True,
                     "app_key": "k", "app_secret": "s", "merchant_id": "m", "base_url": "u"}
        with patch.object(ops, "_get_xianguanjia_settings", return_value=settings), \
             patch.object(ops, "_xianguanjia_service_config", return_value={}), \
             patch("src.modules.orders.service.OrderFulfillmentService") as MockSvc:
            MockSvc.return_value.deliver.return_value = {"ok": True}
            result = ops.retry_xianguanjia_delivery({
                "order_id": "O1",
                "shipping_info": "not_dict",
                "order_no": "O1",
            })
        assert result["success"] is True


# ---------------------------------------------------------------------------
# retry_xianguanjia_price
# ---------------------------------------------------------------------------

class TestRetryXianguanjiaPrice:
    def test_not_configured(self):
        ops = _make_mimic_ops()
        with patch.object(ops, "_get_xianguanjia_settings", return_value={"configured": False}):
            result = ops.retry_xianguanjia_price({})
        assert result["error_code"] == "XGJ_NOT_CONFIGURED"

    def test_missing_product_id(self):
        ops = _make_mimic_ops()
        settings = {"configured": True, "app_key": "k", "app_secret": "s", "merchant_id": "", "base_url": "u"}
        with patch.object(ops, "_get_xianguanjia_settings", return_value=settings):
            result = ops.retry_xianguanjia_price({})
        assert result["error_code"] == "MISSING_PRODUCT_ID"

    def test_invalid_new_price(self):
        ops = _make_mimic_ops()
        settings = {"configured": True, "app_key": "k", "app_secret": "s", "merchant_id": "", "base_url": "u"}
        with patch.object(ops, "_get_xianguanjia_settings", return_value=settings):
            result = ops.retry_xianguanjia_price({"product_id": "p1", "new_price": "abc"})
        assert result["error_code"] == "INVALID_NEW_PRICE"

    def test_invalid_original_price(self):
        ops = _make_mimic_ops()
        settings = {"configured": True, "app_key": "k", "app_secret": "s", "merchant_id": "", "base_url": "u"}
        with patch.object(ops, "_get_xianguanjia_settings", return_value=settings):
            result = ops.retry_xianguanjia_price({
                "product_id": "p1", "new_price": 10.0, "original_price": "not_num",
            })
        assert result["error_code"] == "INVALID_ORIGINAL_PRICE"

    def test_success(self):
        ops = _make_mimic_ops()
        settings = {"configured": True, "app_key": "k", "app_secret": "s", "merchant_id": "", "base_url": "u"}
        with patch.object(ops, "_get_xianguanjia_settings", return_value=settings), \
             patch.object(ops, "_xianguanjia_service_config", return_value={}), \
             patch("src.modules.operations.service.get_compliance_guard"), \
             patch("src.modules.operations.service.get_config") as mcfg, \
             patch("src.dashboard_server._run_async") as mock_run:
            mcfg.return_value = MagicMock(browser={"delay": {"min": 0.01, "max": 0.02}})
            mock_run.return_value = {"success": True}
            result = ops.retry_xianguanjia_price({
                "product_id": "p1", "new_price": 10.0, "original_price": 15.0,
            })
        assert result["success"] is True

    def test_exception(self):
        ops = _make_mimic_ops()
        settings = {"configured": True, "app_key": "k", "app_secret": "s", "merchant_id": "", "base_url": "u"}
        with patch.object(ops, "_get_xianguanjia_settings", return_value=settings), \
             patch.object(ops, "_xianguanjia_service_config", return_value={}), \
             patch("src.modules.operations.service.get_compliance_guard"), \
             patch("src.modules.operations.service.get_config") as mcfg, \
             patch("src.dashboard_server._run_async", side_effect=RuntimeError("price err")):
            mcfg.return_value = MagicMock(browser={"delay": {"min": 0.01, "max": 0.02}})
            result = ops.retry_xianguanjia_price({
                "product_id": "p1", "new_price": 10.0,
            })
        assert result["error_code"] == "XGJ_RETRY_PRICE_FAILED"


# ---------------------------------------------------------------------------
# handle_order_callback
# ---------------------------------------------------------------------------

class TestHandleOrderCallback:
    def test_success(self):
        ops = _make_mimic_ops()
        settings = {"configured": True, "auto_ship_enabled": True, "auto_ship_on_paid": True,
                     "app_key": "k", "app_secret": "s", "merchant_id": "", "base_url": "u"}
        with patch.object(ops, "_get_xianguanjia_settings", return_value=settings), \
             patch.object(ops, "_xianguanjia_service_config", return_value={}), \
             patch("src.modules.orders.service.OrderFulfillmentService") as MockSvc:
            MockSvc.return_value.process_callback.return_value = {"processed": True}
            result = ops.handle_order_callback({"order_id": "O1"})
        assert "settings" in result

    def test_exception(self):
        ops = _make_mimic_ops()
        settings = {"configured": False, "auto_ship_enabled": False, "auto_ship_on_paid": False,
                     "app_key": "", "app_secret": "", "merchant_id": "", "base_url": ""}
        with patch.object(ops, "_get_xianguanjia_settings", return_value=settings), \
             patch.object(ops, "_xianguanjia_service_config", return_value={}), \
             patch("src.modules.orders.service.OrderFulfillmentService") as MockSvc:
            MockSvc.return_value.process_callback.side_effect = RuntimeError("cb err")
            result = ops.handle_order_callback({})
        assert result["error_code"] == "XGJ_CALLBACK_FAILED"


# ---------------------------------------------------------------------------
# _vg_int
# ---------------------------------------------------------------------------

class TestVgInt:
    def test_normal(self):
        from src.dashboard_server import MimicOps
        assert MimicOps._vg_int({"k": 5}, "k") == 5

    def test_exception(self):
        from src.dashboard_server import MimicOps
        assert MimicOps._vg_int({"k": "abc"}, "k") == 0

    def test_missing_key(self):
        from src.dashboard_server import MimicOps
        assert MimicOps._vg_int({}, "k") == 0


# ---------------------------------------------------------------------------
# _build_virtual_goods_dashboard_panels
# ---------------------------------------------------------------------------

class TestBuildVirtualGoodsDashboardPanels:
    def test_full_panels(self):
        ops = _make_mimic_ops()
        dashboard_result = {
            "metrics": {
                "total_orders": 10, "total_callbacks": 20,
                "pending_callbacks": 5, "processed_callbacks": 12,
                "failed_callbacks": 3, "timeout_backlog": 2,
                "unknown_event_kind": 1, "timeout_seconds": 300,
            },
            "errors": [],
        }
        funnel_result = {
            "data": {"stage_totals": {"payment": 10, "fulfillment": 5}},
            "metrics": {"total_metric_count": 15, "source": "ops_funnel_stage_daily"},
        }
        exception_result = {"data": {"items": []}}
        fulfillment_result = {
            "data": {"summary": {
                "fulfilled_orders": 8, "failed_orders": 2,
                "fulfillment_rate_pct": 80.0, "failure_rate_pct": 20.0,
                "avg_fulfillment_seconds": 30.0, "p95_fulfillment_seconds": 120.0,
            }}
        }
        product_result = {
            "data": {"summary": {
                "exposure_count": 100, "paid_order_count": 10,
                "paid_amount_cents": 5000, "refund_order_count": 1,
                "exception_count": 0, "manual_takeover_count": 0,
                "conversion_rate_pct": 10.0,
            }}
        }
        panels = ops._build_virtual_goods_dashboard_panels(
            dashboard_result, [], funnel_result,
            exception_result, fulfillment_result, product_result,
        )
        assert "operations_funnel_overview" in panels
        assert "exception_priority_pool" in panels
        assert panels["fulfillment_efficiency"]["fulfillment_rate_pct"] == 80.0

    def test_with_unknown_event_kind_in_errors(self):
        ops = _make_mimic_ops()
        dashboard_result = {
            "metrics": {
                "total_orders": 0, "total_callbacks": 0,
                "pending_callbacks": 0, "processed_callbacks": 0,
                "failed_callbacks": 0, "timeout_backlog": 0,
                "unknown_event_kind": 0, "timeout_seconds": 300,
            },
            "errors": [
                {"code": "UNKNOWN_EVENT_KIND", "count": 3, "message": "unknown detected"},
            ],
        }
        panels = ops._build_virtual_goods_dashboard_panels(
            dashboard_result, [], None, None, None, None,
        )
        pool = panels["exception_priority_pool"]["items"]
        assert any(i.get("type") == "UNKNOWN_EVENT_KIND" for i in pool)

    def test_non_dict_error_in_errors(self):
        ops = _make_mimic_ops()
        dashboard_result = {
            "metrics": {
                "total_orders": 0, "total_callbacks": 0,
                "pending_callbacks": 0, "processed_callbacks": 0,
                "failed_callbacks": 0, "timeout_backlog": 0,
                "unknown_event_kind": 0, "timeout_seconds": 300,
            },
            "errors": ["not_a_dict", None],
        }
        panels = ops._build_virtual_goods_dashboard_panels(
            dashboard_result, [], None, None, None, None,
        )
        assert "operations_funnel_overview" in panels


# ---------------------------------------------------------------------------
# get_virtual_goods_metrics
# ---------------------------------------------------------------------------

class TestGetVirtualGoodsMetrics:
    def test_query_not_callable(self):
        ops = _make_mimic_ops()
        with patch.object(ops, "_virtual_goods_service") as mock_svc:
            svc = MagicMock(spec=[])
            mock_svc.return_value = svc
            result = ops.get_virtual_goods_metrics()
        assert result["error_code"] == "VG_QUERY_NOT_AVAILABLE"

    def test_not_dict_result(self):
        ops = _make_mimic_ops()
        with patch.object(ops, "_virtual_goods_service") as mock_svc:
            svc = MagicMock()
            svc.get_dashboard_metrics.return_value = "not_dict"
            mock_svc.return_value = svc
            result = ops.get_virtual_goods_metrics()
        assert result["error_code"] == "VG_METRICS_INVALID"

    def test_manual_orders_extraction(self):
        ops = _make_mimic_ops()
        with patch.object(ops, "_virtual_goods_service") as mock_svc, \
             patch.object(ops, "_build_virtual_goods_dashboard_panels", return_value={}):
            svc = MagicMock()
            svc.get_dashboard_metrics.return_value = {
                "ok": True, "action": "x", "code": "OK",
                "message": "", "data": {}, "metrics": {},
                "errors": [], "ts": "",
            }
            manual_resp = {"data": {"items": [{"xianyu_order_id": "O1"}]}}
            svc.list_manual_takeover_orders.return_value = manual_resp
            svc.get_funnel_metrics.return_value = None
            svc.list_priority_exceptions.return_value = None
            svc.get_fulfillment_efficiency_metrics.return_value = None
            svc.get_product_operation_metrics.return_value = None
            mock_svc.return_value = svc
            result = ops.get_virtual_goods_metrics()
        assert result["success"] is True


# ---------------------------------------------------------------------------
# get_dashboard_readonly_aggregate
# ---------------------------------------------------------------------------

class TestGetDashboardReadonlyAggregate:
    def test_success(self):
        ops = _make_mimic_ops()
        with patch.object(ops, "get_virtual_goods_metrics", return_value={
            "success": True,
            "service_response": {},
            "dashboard_panels": {
                "operations_funnel_overview": {},
                "exception_priority_pool": {},
                "fulfillment_efficiency": {},
                "product_operations": {},
                "drill_down": {},
            },
            "generated_at": "2025-01-01",
        }):
            result = ops.get_dashboard_readonly_aggregate()
        assert result["success"] is True
        assert result["readonly"] is True

    def test_failed_metrics(self):
        ops = _make_mimic_ops()
        with patch.object(ops, "get_virtual_goods_metrics", return_value={"success": False, "error": "fail"}):
            result = ops.get_dashboard_readonly_aggregate()
        assert result["success"] is False


# ---------------------------------------------------------------------------
# inspect_virtual_goods_order
# ---------------------------------------------------------------------------

class TestInspectVirtualGoodsOrder:
    def test_missing_order_id(self):
        ops = _make_mimic_ops()
        result = ops.inspect_virtual_goods_order("")
        assert result["error_code"] == "MISSING_ORDER_ID"

    def test_inspect_not_callable(self):
        ops = _make_mimic_ops()
        with patch.object(ops, "_virtual_goods_service") as mock_svc:
            svc = MagicMock(spec=[])
            mock_svc.return_value = svc
            result = ops.inspect_virtual_goods_order("O1")
        assert result["error_code"] == "VG_QUERY_NOT_AVAILABLE"

    def test_not_dict_result(self):
        ops = _make_mimic_ops()
        with patch.object(ops, "_virtual_goods_service") as mock_svc:
            svc = MagicMock()
            svc.inspect_order.return_value = "not_dict"
            mock_svc.return_value = svc
            result = ops.inspect_virtual_goods_order("O1")
        assert result["error_code"] == "VG_INSPECT_INVALID"

    def test_success_with_data(self):
        ops = _make_mimic_ops()
        with patch.object(ops, "_virtual_goods_service") as mock_svc:
            svc = MagicMock()
            svc.inspect_order.return_value = {
                "ok": True, "action": "inspect_order", "code": "OK",
                "message": "ok", "ts": "2025-01-01",
                "data": {
                    "order": {
                        "xianyu_order_id": "O1", "order_status": "paid",
                        "fulfillment_status": "pending", "updated_at": "2025",
                        "manual_takeover": False, "last_error": "",
                    },
                    "callbacks": [
                        {
                            "id": 1, "external_event_id": "e1", "dedupe_key": "dk1",
                            "event_kind": "order", "verify_passed": True,
                            "processed": True, "attempt_count": 1,
                            "last_process_error": "", "created_at": "2025",
                            "processed_at": "2025",
                        }
                    ],
                    "exception_priority_pool": {"items": []},
                },
            }
            mock_svc.return_value = svc
            result = ops.inspect_virtual_goods_order("O1")
        assert result["success"] is True
        assert result["order_id"] == "O1"

    def test_type_error_fallback(self):
        ops = _make_mimic_ops()
        with patch.object(ops, "_virtual_goods_service") as mock_svc:
            svc = MagicMock()
            call_count = 0

            def inspect_side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise TypeError("bad arg")
                return {
                    "ok": True, "data": {"order": {}, "callbacks": [],
                                          "exception_priority_pool": {"items": []}},
                }

            svc.inspect_order.side_effect = inspect_side_effect
            mock_svc.return_value = svc
            result = ops.inspect_virtual_goods_order("O1")
        assert result["success"] is True


# ---------------------------------------------------------------------------
# get_replies
# ---------------------------------------------------------------------------

class TestGetReplies:
    def test_get_replies(self):
        ops = _make_mimic_ops()
        with patch.object(ops, "get_template", return_value={
            "success": True,
            "weight_template": "W",
            "volume_template": "V",
            "updated_at": "2025",
        }):
            result = ops.get_replies()
        assert result["success"] is True
        assert result["replies"]["weight_template"] == "W"


# ---------------------------------------------------------------------------
# DashboardHandler do_GET / do_POST uncovered paths
# ---------------------------------------------------------------------------

class FakeWfile:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data

    def flush(self):
        pass


class FakeHandler:
    """Minimal mock of DashboardHandler for testing route methods."""

    def __init__(self):
        self.headers_sent = {}
        self.status_code = None
        self.body = b""
        self.wfile = FakeWfile()

    def send_response(self, code):
        self.status_code = code

    def send_header(self, key, value):
        self.headers_sent[key] = value

    def end_headers(self):
        pass


def _make_handler(path="/", method="GET", body=None):
    """Create a DashboardHandler-like object for testing."""
    from src.dashboard_server import DashboardHandler

    handler = object.__new__(DashboardHandler)
    handler.path = path
    handler.requestline = f"{method} {path} HTTP/1.1"
    handler.request_version = "HTTP/1.1"
    handler.command = method
    handler.client_address = ("127.0.0.1", 12345)
    handler.close_connection = True

    raw_body = json.dumps(body).encode() if body else b""
    handler.headers = MagicMock()
    handler.headers.get = lambda k, d="": {
        "Content-Length": str(len(raw_body)),
        "Content-Type": "application/json",
    }.get(k, d)
    handler.wfile = FakeWfile()
    handler.rfile = io.BytesIO(raw_body)

    handler.repo = MagicMock()
    handler.module_console = MagicMock()
    handler.mimic_ops = MagicMock()

    return handler


class TestDashboardHandlerDoGET:
    def test_healthz(self):
        handler = _make_handler("/healthz")
        handler.repo._connect.return_value.__enter__ = MagicMock()
        handler.repo._connect.return_value.__exit__ = MagicMock()
        mock_conn = MagicMock()
        handler.repo._connect.return_value = mock_conn
        handler.mimic_ops.service_status.return_value = {
            "system_running": True, "alive_count": 3, "total_modules": 5,
        }
        handler.mimic_ops._service_started_at = "2025-01-01T00:00:00"

        from src.dashboard_server import DashboardHandler
        DashboardHandler.do_GET(handler)
        assert handler.wfile.data  # some response sent

    def test_healthz_db_error(self):
        handler = _make_handler("/healthz")
        handler.repo._connect.side_effect = Exception("db error")
        handler.mimic_ops.service_status.side_effect = Exception("status fail")
        handler.mimic_ops._service_started_at = ""

        from src.dashboard_server import DashboardHandler
        DashboardHandler.do_GET(handler)
        assert handler.wfile.data

    def test_healthz_bad_uptime(self):
        handler = _make_handler("/healthz")
        mock_conn = MagicMock()
        handler.repo._connect.return_value = mock_conn
        handler.mimic_ops.service_status.return_value = {"system_running": True}
        handler.mimic_ops._service_started_at = "INVALID_DATE"

        from src.dashboard_server import DashboardHandler
        DashboardHandler.do_GET(handler)
        assert handler.wfile.data

    def test_api_summary_aggregate(self):
        handler = _make_handler("/api/summary")
        handler.mimic_ops.get_dashboard_readonly_aggregate.return_value = {
            "success": True, "sections": {
                "operations_funnel_overview": {"k": "v"},
            },
        }
        from src.dashboard_server import DashboardHandler
        DashboardHandler.do_GET(handler)

    def test_api_summary_aggregate_not_success(self):
        handler = _make_handler("/api/summary")
        handler.mimic_ops.get_dashboard_readonly_aggregate.return_value = {
            "success": False,
        }
        from src.dashboard_server import DashboardHandler
        DashboardHandler.do_GET(handler)

    def test_api_summary_aggregate_none(self):
        handler = _make_handler("/api/summary")
        handler.mimic_ops.get_dashboard_readonly_aggregate.return_value = None
        # fallback path
        from src.dashboard_server import DashboardHandler
        DashboardHandler.do_GET(handler)

    def test_api_replies(self):
        handler = _make_handler("/api/replies")
        handler.mimic_ops.get_replies.return_value = {"success": True}
        from src.dashboard_server import DashboardHandler
        DashboardHandler.do_GET(handler)

    def test_api_virtual_goods_metrics_has_getter(self):
        handler = _make_handler("/api/virtual-goods/metrics")
        handler.mimic_ops.get_virtual_goods_metrics.return_value = {"success": True}
        from src.dashboard_server import DashboardHandler
        DashboardHandler.do_GET(handler)

    def test_api_virtual_goods_metrics_no_getter(self):
        handler = _make_handler("/api/virtual-goods/metrics")
        handler.mimic_ops.get_virtual_goods_metrics = None
        handler.mimic_ops.get_dashboard_readonly_aggregate.return_value = {
            "success": True, "service_response": {}, "sections": {}, "generated_at": "",
        }
        from src.dashboard_server import DashboardHandler
        DashboardHandler.do_GET(handler)

    def test_api_virtual_goods_metrics_no_getter_no_aggregate(self):
        handler = _make_handler("/api/virtual-goods/metrics")
        handler.mimic_ops.get_virtual_goods_metrics = None
        handler.mimic_ops.get_dashboard_readonly_aggregate = None
        from src.dashboard_server import DashboardHandler
        DashboardHandler.do_GET(handler)

    def test_api_virtual_goods_metrics_no_getter_aggregate_not_dict(self):
        handler = _make_handler("/api/virtual-goods/metrics")
        handler.mimic_ops.get_virtual_goods_metrics = None
        agg_fn = MagicMock(return_value="not_dict")
        handler.mimic_ops.get_dashboard_readonly_aggregate = agg_fn
        from src.dashboard_server import DashboardHandler
        DashboardHandler.do_GET(handler)

    def test_api_virtual_goods_metrics_aggregate_not_success(self):
        handler = _make_handler("/api/virtual-goods/metrics")
        handler.mimic_ops.get_virtual_goods_metrics = None
        agg_fn = MagicMock(return_value={"success": False, "error": "fail"})
        handler.mimic_ops.get_dashboard_readonly_aggregate = agg_fn
        from src.dashboard_server import DashboardHandler
        DashboardHandler.do_GET(handler)

    def test_api_dashboard(self):
        handler = _make_handler("/api/dashboard")
        handler.mimic_ops.get_dashboard_readonly_aggregate.return_value = {"success": True}
        from src.dashboard_server import DashboardHandler
        DashboardHandler.do_GET(handler)

    def test_api_listing_templates(self):
        handler = _make_handler("/api/listing/templates")
        with patch("src.modules.listing.templates.list_templates", return_value=[{"id": "t1"}]):
            from src.dashboard_server import DashboardHandler
            DashboardHandler.do_GET(handler)

    def test_api_virtual_goods_inspect_order_get(self):
        handler = _make_handler("/api/virtual-goods/inspect-order?order_id=O1")
        handler.mimic_ops.inspect_virtual_goods_order.return_value = {"success": True}
        from src.dashboard_server import DashboardHandler
        DashboardHandler.do_GET(handler)


class TestDashboardHandlerDoPOST:
    def test_xgj_settings(self):
        handler = _make_handler("/api/xgj/settings", method="POST", body={"app_key": "k"})
        handler.mimic_ops.save_xianguanjia_settings.return_value = {"success": True}
        from src.dashboard_server import DashboardHandler
        DashboardHandler.do_POST(handler)

    def test_xgj_retry_price(self):
        handler = _make_handler("/api/xgj/retry-price", method="POST", body={"product_id": "p1", "new_price": 10})
        handler.mimic_ops.retry_xianguanjia_price.return_value = {"success": True}
        from src.dashboard_server import DashboardHandler
        DashboardHandler.do_POST(handler)

    def test_xgj_retry_ship(self):
        handler = _make_handler("/api/xgj/retry-ship", method="POST", body={"order_id": "O1"})
        handler.mimic_ops.retry_xianguanjia_delivery.return_value = {"success": True}
        from src.dashboard_server import DashboardHandler
        DashboardHandler.do_POST(handler)

    def test_orders_callback(self):
        handler = _make_handler("/api/orders/callback", method="POST", body={"order_id": "O1"})
        handler.mimic_ops.handle_order_callback.return_value = {"success": True}
        from src.dashboard_server import DashboardHandler
        DashboardHandler.do_POST(handler)

    def test_virtual_goods_inspect_order_post(self):
        handler = _make_handler("/api/virtual-goods/inspect-order", method="POST", body={"order_id": "O1"})
        handler.mimic_ops.inspect_virtual_goods_order.return_value = {"success": True}
        from src.dashboard_server import DashboardHandler
        DashboardHandler.do_POST(handler)

    def test_listing_preview(self):
        handler = _make_handler("/api/listing/preview", method="POST", body={"name": "test"})
        from src.dashboard_server import DashboardHandler
        with patch.object(DashboardHandler, "_handle_listing_preview", return_value={"ok": True}):
            DashboardHandler.do_POST(handler)

    def test_listing_publish(self):
        handler = _make_handler("/api/listing/publish", method="POST", body={"name": "test"})
        from src.dashboard_server import DashboardHandler
        with patch.object(DashboardHandler, "_handle_listing_publish", return_value={"ok": True}):
            DashboardHandler.do_POST(handler)


# ---------------------------------------------------------------------------
# _handle_listing_preview / _handle_listing_publish
# ---------------------------------------------------------------------------

class TestHandleListingPreview:
    def test_success(self):
        handler = _make_handler()
        handler.mimic_ops = MagicMock()
        from src.dashboard_server import DashboardHandler

        with patch.object(handler, "_xianguanjia_service_config", create=True, return_value={}), \
             patch("src.modules.listing.auto_publish.get_compliance_guard"), \
             patch("src.modules.listing.auto_publish.ContentService"), \
             patch("src.modules.listing.auto_publish.OSSUploader"), \
             patch("src.modules.listing.auto_publish.generate_product_images", return_value=["/img.png"]):
            result = DashboardHandler._handle_listing_preview(handler, {"name": "test"})
        assert isinstance(result, dict)

    def test_exception(self):
        handler = _make_handler()
        from src.dashboard_server import DashboardHandler

        with patch.object(handler, "_xianguanjia_service_config", create=True, side_effect=RuntimeError("fail")):
            result = DashboardHandler._handle_listing_preview(handler, {})
        assert result["ok"] is False
        assert result["step"] == "error"


class TestHandleListingPublish:
    def test_no_credentials(self):
        handler = _make_handler()
        from src.dashboard_server import DashboardHandler

        with patch.object(handler, "_xianguanjia_service_config", create=True, return_value={"xianguanjia": {}}):
            result = DashboardHandler._handle_listing_publish(handler, {})
        assert result["ok"] is False

    def test_exception(self):
        handler = _make_handler()
        from src.dashboard_server import DashboardHandler

        with patch.object(handler, "_xianguanjia_service_config", create=True, side_effect=RuntimeError("err")):
            result = DashboardHandler._handle_listing_publish(handler, {})
        assert result["ok"] is False
        assert result["step"] == "error"

    def test_with_preview_data(self):
        handler = _make_handler()
        from src.dashboard_server import DashboardHandler

        with patch.object(handler, "_xianguanjia_service_config", create=True, return_value={
            "xianguanjia": {"app_key": "k", "app_secret": "s", "base_url": "u"},
        }), \
             patch("src.integrations.xianguanjia.open_platform_client.OpenPlatformClient"), \
             patch("src.modules.listing.auto_publish.get_compliance_guard"), \
             patch("src.modules.listing.auto_publish.ContentService"), \
             patch("src.modules.listing.auto_publish.OSSUploader") as MockOSS:
            mock_uploader = MagicMock()
            mock_uploader.configured = False
            MockOSS.return_value = mock_uploader
            result = DashboardHandler._handle_listing_publish(handler, {
                "preview_data": {"local_images": ["/img.png"], "title": "T"},
            })
        assert isinstance(result, dict)

    def test_publish_without_preview(self):
        handler = _make_handler()
        from src.dashboard_server import DashboardHandler

        with patch.object(handler, "_xianguanjia_service_config", create=True, return_value={
            "xianguanjia": {"app_key": "k", "app_secret": "s", "base_url": "u"},
        }), \
             patch("src.integrations.xianguanjia.open_platform_client.OpenPlatformClient") as MockClient, \
             patch("src.modules.listing.auto_publish.get_compliance_guard"), \
             patch("src.modules.listing.auto_publish.ContentService") as MockCS, \
             patch("src.modules.listing.auto_publish.OSSUploader") as MockOSS:
            mock_uploader = MagicMock()
            mock_uploader.configured = False
            MockOSS.return_value = mock_uploader
            mock_cs = MagicMock()
            mock_cs.generate_listing_content.return_value = {"compliance": {}}
            MockCS.return_value = mock_cs
            result = DashboardHandler._handle_listing_publish(handler, {"name": "test"})
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# _aggregate_dashboard_payload
# ---------------------------------------------------------------------------

class TestAggregateDashboardPayload:
    def test_not_callable(self):
        handler = _make_handler()
        handler.mimic_ops.get_dashboard_readonly_aggregate = None
        from src.dashboard_server import DashboardHandler
        result = DashboardHandler._aggregate_dashboard_payload(handler, "/api/summary")
        assert result is None

    def test_not_dict(self):
        handler = _make_handler()
        handler.mimic_ops.get_dashboard_readonly_aggregate.return_value = "not_dict"
        from src.dashboard_server import DashboardHandler
        result = DashboardHandler._aggregate_dashboard_payload(handler, "/api/summary")
        assert result is None

    def test_not_success(self):
        handler = _make_handler()
        handler.mimic_ops.get_dashboard_readonly_aggregate.return_value = {"success": False, "error": "fail"}
        from src.dashboard_server import DashboardHandler
        result = DashboardHandler._aggregate_dashboard_payload(handler, "/api/summary")
        assert result["success"] is False

    def test_success_with_sections(self):
        handler = _make_handler()
        handler.mimic_ops.get_dashboard_readonly_aggregate.return_value = {
            "success": True,
            "sections": {
                "operations_funnel_overview": {"k": "v"},
                "fulfillment_efficiency": {"k2": "v2"},
                "exception_priority_pool": {},
                "product_operations": {},
            },
        }
        from src.dashboard_server import DashboardHandler

        for path in ["/api/summary", "/api/trend", "/api/recent-operations", "/api/top-products"]:
            result = DashboardHandler._aggregate_dashboard_payload(handler, path)
            assert result["success"] is True
            assert result["readonly"] is True


# ---------------------------------------------------------------------------
# _vg_service_metrics
# ---------------------------------------------------------------------------

class TestCookiePairsToText:
    def test_empty_key_value(self):
        from src.dashboard_server import MimicOps
        text, count = MimicOps._cookie_pairs_to_text([("", "val"), ("key", ""), ("", "")])
        assert count == 0
        assert text == ""


class TestServiceStatusDatetimeParsing:
    def test_bad_last_auto_recover_at(self):
        ops = _make_mimic_ops()
        with patch.object(ops, "_get_env_value", return_value=""), \
             patch.object(ops, "_maybe_auto_recover_presales", return_value={
                 "stage": "recover_triggered",
                 "last_auto_recover_at": "INVALID_DATE",
             }), \
             patch.object(ops, "_extract_cookie_pairs_from_header", return_value=[]):
            result = ops.service_status()
        assert isinstance(result, dict)


class TestImportCookiePluginFilesZipContinue:
    def test_zip_bad_zip(self):
        ops = _make_mimic_ops()
        bad_zip = b"not_a_zip"
        files = [("test.zip", bad_zip)]
        result = ops.import_cookie_plugin_files(files, auto_recover=False)
        assert isinstance(result, dict)

    def test_zip_general_exception(self):
        ops = _make_mimic_ops()
        import zipfile as zf
        buf = io.BytesIO()
        with zf.ZipFile(buf, "w") as z:
            z.writestr("cookies.txt", "k=v")
        zip_bytes = buf.getvalue()
        files = [("test.zip", zip_bytes)]
        import src.dashboard_server as ds_mod
        orig_zipfile = ds_mod.zipfile.ZipFile
        ds_mod.zipfile.ZipFile = Mock(side_effect=PermissionError("denied"))
        try:
            result = ops.import_cookie_plugin_files(files, auto_recover=False)
        finally:
            ds_mod.zipfile.ZipFile = orig_zipfile
        assert isinstance(result, dict)

    def test_non_cookie_file_skipped(self):
        ops = _make_mimic_ops()
        files = [("readme.md", b"this is not a cookie file")]
        result = ops.import_cookie_plugin_files(files, auto_recover=False)
        assert isinstance(result, dict)

    def test_cookie_txt_file(self):
        ops = _make_mimic_ops()
        files = [("cookies.txt", b"unb=123456; cookie2=xyz")]
        result = ops.import_cookie_plugin_files(files, auto_recover=False)
        assert isinstance(result, dict)


class TestImportRouteFilesZipContinue:
    def test_zip_bad_zip(self):
        ops = _make_mimic_ops()
        bad_zip = b"not_a_zip"
        files = [("test.zip", bad_zip)]
        result = ops.import_route_files(files)
        assert isinstance(result, dict)

    def test_zip_general_exception(self):
        ops = _make_mimic_ops()
        import zipfile as zf
        buf = io.BytesIO()
        with zf.ZipFile(buf, "w") as z:
            z.writestr("routes.xlsx", b"data")
        zip_bytes = buf.getvalue()
        files = [("test.zip", zip_bytes)]
        import src.dashboard_server as ds_mod
        orig_zipfile = ds_mod.zipfile.ZipFile
        ds_mod.zipfile.ZipFile = Mock(side_effect=PermissionError("denied"))
        try:
            result = ops.import_route_files(files)
        finally:
            ds_mod.zipfile.ZipFile = orig_zipfile
        assert isinstance(result, dict)

    def test_non_route_file_skipped(self):
        ops = _make_mimic_ops()
        files = [("readme.md", b"not a route file")]
        result = ops.import_route_files(files)
        assert isinstance(result, dict)


class TestImportMarkupFilesZipContinue:
    def test_zip_bad_zip(self):
        ops = _make_mimic_ops()
        bad_zip = b"not_a_zip"
        files = [("test.zip", bad_zip)]
        result = ops.import_markup_files(files)
        assert isinstance(result, dict)

    def test_zip_general_exception(self):
        ops = _make_mimic_ops()
        import zipfile as zf
        buf = io.BytesIO()
        with zf.ZipFile(buf, "w") as z:
            z.writestr("markup.xlsx", b"data")
        zip_bytes = buf.getvalue()
        files = [("test.zip", zip_bytes)]
        import src.dashboard_server as ds_mod
        orig_zipfile = ds_mod.zipfile.ZipFile
        ds_mod.zipfile.ZipFile = Mock(side_effect=PermissionError("denied"))
        try:
            result = ops.import_markup_files(files)
        finally:
            ds_mod.zipfile.ZipFile = orig_zipfile
        assert isinstance(result, dict)

    def test_non_markup_file_processed(self):
        ops = _make_mimic_ops()
        files = [("readme.md", b"not a markup file")]
        result = ops.import_markup_files(files)
        assert isinstance(result, dict)


class TestParseMarkupRulesEmptyRow:
    def test_empty_row_skipped(self):
        ops = _make_mimic_ops()
        rows = [
            ["快递", "加价1", "加价2", "加价3", "加价4"],
            ["", "", "", "", ""],
            [],
        ]
        with patch.object(ops, "_resolve_markup_header_map", return_value=(
            {"courier": 0, "normal_first_add": 1, "member_first_add": 2, "normal_extra_add": 3, "member_extra_add": 4},
            0,
        )):
            result = ops._parse_markup_rules_from_rows(rows)
        assert isinstance(result, dict)

    def test_col_idx_none_for_some_fields(self):
        ops = _make_mimic_ops()
        rows = [
            ["header_courier", "header_field"],
            ["SF", "10", "20", "30", "40"],
        ]
        mapping = {
            "courier": 0,
            "normal_first_add": None,
            "member_first_add": 1,
            "normal_extra_add": 100,
            "member_extra_add": 3,
        }
        with patch.object(ops, "_resolve_markup_header_map", return_value=(mapping, 0)), \
             patch.object(ops, "_markup_float", side_effect=lambda x: float(x) if str(x).replace('.','').isdigit() else None), \
             patch.object(ops, "_normalize_markup_courier", side_effect=lambda x: str(x).strip() if str(x).strip() and str(x).strip() != "header_courier" else ""), \
             patch.object(ops, "_build_markup_rule", return_value={"rule": True}):
            result = ops._parse_markup_rules_from_rows(rows)
        assert isinstance(result, dict)


class TestVgServiceMetrics:
    def test_with_metrics(self):
        from src.dashboard_server import MimicOps
        assert MimicOps._vg_service_metrics({"metrics": {"a": 1}}) == {"a": 1}

    def test_with_data(self):
        from src.dashboard_server import MimicOps
        assert MimicOps._vg_service_metrics({"data": {"b": 2}}) == {"b": 2}

    def test_fallback(self):
        from src.dashboard_server import MimicOps
        assert MimicOps._vg_service_metrics({}) == {}

    def test_metrics_not_dict(self):
        from src.dashboard_server import MimicOps
        assert MimicOps._vg_service_metrics({"metrics": "not_dict", "data": {"c": 3}}) == {"c": 3}

from __future__ import annotations

from types import SimpleNamespace

import pytest

import inspect

from src.dashboard_server import DASHBOARD_HTML, DashboardHandler, MimicOps


def test_wave_d_dashboard_only_consumes_service_aggregate(monkeypatch: pytest.MonkeyPatch, temp_dir) -> None:
    called: dict[str, bool] = {}

    class FakeVirtualGoodsService:
        def __init__(self, db_path: str, config: dict | None = None) -> None:
            called["init"] = True

        def get_dashboard_metrics(self):
            called["get_dashboard_metrics"] = True
            return {
                "ok": True,
                "action": "get_dashboard_metrics",
                "code": "OK",
                "message": "ready",
                "data": {
                    "total_orders": 10,
                    "total_callbacks": 20,
                    "pending_callbacks": 3,
                    "processed_callbacks": 16,
                    "failed_callbacks": 1,
                    "timeout_backlog": 2,
                    "unknown_event_kind": 1,
                    "timeout_seconds": 300,
                },
                "errors": [{"code": "UNKNOWN_EVENT_KIND", "count": 1, "message": "unknown event_kind callbacks detected"}],
                "ts": "2026-03-06T00:00:00Z",
            }

        def get_funnel_metrics(self, *, limit: int = 500):
            called["get_funnel_metrics"] = True
            return {
                "ok": True,
                "action": "get_funnel_metrics",
                "data": {
                    "items": [
                        {"stage": "paid", "metric_count": 10},
                        {"stage": "delivered", "metric_count": 8},
                        {"stage": "refund", "metric_count": 1},
                    ],
                    "stage_totals": {"paid": 10, "delivered": 8, "refund": 1},
                },
                "metrics": {"total_metric_count": 19, "source": "ops_funnel_stage_daily"},
            }

        def list_priority_exceptions(self, *, limit: int = 100, status: str = "open"):
            called["list_priority_exceptions"] = True
            return {"ok": True, "action": "list_priority_exceptions", "data": {"items": [{"priority": "P0", "type": "UNKNOWN_EVENT_KIND", "count": 1, "summary": "unknown"}]}}

        def get_fulfillment_efficiency_metrics(self, *, limit: int = 500):
            called["get_fulfillment_efficiency_metrics"] = True
            return {
                "ok": True,
                "action": "get_fulfillment_efficiency_metrics",
                "data": {
                    "summary": {
                        "fulfilled_orders": 8,
                        "failed_orders": 1,
                        "fulfillment_rate_pct": 88.89,
                        "failure_rate_pct": 11.11,
                        "avg_fulfillment_seconds": 120.0,
                        "p95_fulfillment_seconds": 300.0,
                    }
                },
                "metrics": {"source": "ops_fulfillment_eff_daily"},
            }

        def get_product_operation_metrics(self, *, limit: int = 500):
            called["get_product_operation_metrics"] = True
            return {"ok": True, "action": "get_product_operation_metrics", "data": {"summary": {"exposure_count": 100, "paid_order_count": 5, "paid_amount_cents": 2000, "refund_order_count": 1, "exception_count": 2, "manual_takeover_count": 1, "conversion_rate_pct": 5.0}}}

        def list_manual_takeover_orders(self):
            called["list_manual_takeover_orders"] = True
            return [{"xianyu_order_id": "OID-1", "fulfillment_status": "manual", "reason": "retry"}]

    monkeypatch.setattr("src.dashboard_server.VirtualGoodsService", FakeVirtualGoodsService)

    ops = MimicOps(project_root=temp_dir, module_console=SimpleNamespace())
    payload = ops.get_virtual_goods_metrics()

    assert payload["success"] is True
    assert called["get_dashboard_metrics"] is True
    assert called["get_funnel_metrics"] is True
    assert called["list_priority_exceptions"] is True
    assert called["get_fulfillment_efficiency_metrics"] is True
    assert called["get_product_operation_metrics"] is True
    assert called["list_manual_takeover_orders"] is True

    assert "metrics" not in payload
    panels = payload["dashboard_panels"]
    assert set(panels.keys()) == {
        "operations_funnel_overview",
        "exception_priority_pool",
        "fulfillment_efficiency",
        "product_operations",
        "drill_down",
    }
    assert panels["operations_funnel_overview"]["stage_totals"]["paid"] == 10
    assert panels["exception_priority_pool"]["total_items"] >= 1
    assert any(item["type"] == "UNKNOWN_EVENT_KIND" for item in panels["exception_priority_pool"]["items"])
    product_summary = panels["product_operations"]["summary"]
    assert set(product_summary.keys()) == {
        "exposure_count",
        "paid_order_count",
        "paid_amount_cents",
        "refund_order_count",
        "exception_count",
        "manual_takeover_count",
        "conversion_rate_pct",
    }


def test_wave_d_readonly_dashboard_aggregate_has_five_sections(monkeypatch: pytest.MonkeyPatch, temp_dir) -> None:
    class FakeVirtualGoodsService:
        def __init__(self, db_path: str, config: dict | None = None) -> None:
            pass

        def get_dashboard_metrics(self):
            return {
                "ok": True,
                "action": "get_dashboard_metrics",
                "code": "OK",
                "data": {
                    "total_orders": 1,
                    "total_callbacks": 1,
                    "pending_callbacks": 0,
                    "processed_callbacks": 1,
                    "failed_callbacks": 0,
                    "timeout_backlog": 0,
                    "unknown_event_kind": 0,
                    "timeout_seconds": 300,
                },
            }

        def list_manual_takeover_orders(self):
            return []

    monkeypatch.setattr("src.dashboard_server.VirtualGoodsService", FakeVirtualGoodsService)

    ops = MimicOps(project_root=temp_dir, module_console=SimpleNamespace())
    payload = ops.get_dashboard_readonly_aggregate()

    assert payload["success"] is True
    assert payload["readonly"] is True
    assert set(payload["sections"].keys()) == {
        "operations_funnel_overview",
        "exception_priority_pool",
        "fulfillment_efficiency",
        "product_operations",
        "drill_down",
    }


def test_wave_d_inspect_unknown_event_kind_must_enter_exception_pool(monkeypatch: pytest.MonkeyPatch, temp_dir) -> None:
    class FakeVirtualGoodsService:
        def __init__(self, db_path: str, config: dict | None = None) -> None:
            pass

        def inspect_order(self, order_id: str):
            return {
                "ok": True,
                "action": "inspect_order",
                "code": "OK",
                "message": "order inspected",
                "data": {
                    "order": {
                        "xianyu_order_id": order_id,
                        "order_status": "paid",
                        "fulfillment_status": "pending",
                        "manual_takeover": 0,
                    },
                    "callbacks": [
                        {"id": 1, "event_kind": "unknown_event_kind", "verify_passed": 1, "processed": 0, "attempt_count": 2},
                        {"id": 2, "event_kind": "paid", "verify_passed": 1, "processed": 1, "attempt_count": 1},
                    ],
                },
            }

    monkeypatch.setattr("src.dashboard_server.VirtualGoodsService", FakeVirtualGoodsService)

    ops = MimicOps(project_root=temp_dir, module_console=SimpleNamespace())
    payload = ops.inspect_virtual_goods_order("OID-X")

    assert payload["success"] is True
    view = payload["drill_down_view"]
    pool = view["exception_priority_pool"]
    assert pool["total_items"] == 1
    assert pool["items"][0]["type"] == "UNKNOWN_EVENT_KIND"
    assert pool["items"][0]["count"] == 1
    assert "current_status" in view
    assert "callback_chain" in view
    assert "claim_replay_trace" in view
    assert "recent_errors" in view
    assert all(action["enabled"] is False for action in view["actions"])


def test_wave_d_dashboard_legacy_endpoints_are_service_aggregated_only() -> None:
    source = inspect.getsource(DashboardHandler.do_GET)
    assert "get_dashboard_readonly_aggregate" in source
    assert "virtual_goods_service.get_dashboard_metrics" in source
    assert "self.repo.get_summary" not in source
    assert "self.repo.get_trend" not in source
    assert "self.repo.get_recent_operations" not in source
    assert "self.repo.get_top_products" not in source


def test_wave_d_ui_no_raw_json_and_has_five_sections() -> None:
    assert "JSON.stringify(data.inspect" not in DASHBOARD_HTML
    assert "Object.keys(metrics).slice" not in DASHBOARD_HTML
    assert "系统概览条" in DASHBOARD_HTML
    assert "健康等级" not in DASHBOARD_HTML
    assert "运营漏斗总览" in DASHBOARD_HTML
    assert "异常优先级池" in DASHBOARD_HTML
    assert "履约效率" in DASHBOARD_HTML
    assert "商品运营" in DASHBOARD_HTML
    assert "成品化 Drill-down" in DASHBOARD_HTML
    assert "claim-replay轨迹" in DASHBOARD_HTML
    assert "可执行动作（禁用态）" in DASHBOARD_HTML

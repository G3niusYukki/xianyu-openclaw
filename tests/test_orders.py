"""订单履约模块测试。"""

from unittest.mock import Mock

import pytest

from src.modules.orders.service import OrderFulfillmentService


def test_order_status_mapping(temp_dir) -> None:
    service = OrderFulfillmentService(db_path=str(temp_dir / "orders.db"))

    assert service.map_status("待发货") == "processing"
    assert service.map_status("已完成") == "completed"
    assert service.map_status("退款中") == "after_sales"


def test_open_platform_status_mapping_is_fixed(temp_dir) -> None:
    service = OrderFulfillmentService(db_path=str(temp_dir / "orders_open_platform.db"))

    assert service.map_open_platform_status(11) == "pending"
    assert service.map_open_platform_status("12") == "processing"
    assert service.map_open_platform_status(21) == "shipping"
    assert service.map_open_platform_status(22) == "completed"
    assert service.map_open_platform_status(23) == "after_sales"
    assert service.map_open_platform_status(24) == "closed"

    with pytest.raises(ValueError, match="Unsupported open platform order_status"):
        service.map_open_platform_status(99)


def test_sync_open_platform_list_orders_is_idempotent(temp_dir) -> None:
    class _Client:
        def __init__(self) -> None:
            self.calls = []

        def list_orders(self, payload):
            self.calls.append(dict(payload))
            return {
                "code": 0,
                "data": {
                    "list": [
                        {
                            "order_no": "xy-sync-1",
                            "order_status": 12,
                            "consign_type": 1,
                            "receiver_name": "张三",
                            "receiver_mobile": "13800138000",
                            "address": "桂庙新村100室",
                            "goods": {"title": "测试商品", "product_id": 1001},
                            "update_time": 1700000001,
                        }
                    ]
                },
            }

    service = OrderFulfillmentService(db_path=str(temp_dir / "orders_sync_list.db"))
    client = _Client()

    first = service.sync_open_platform_list_orders(client, {"page_no": 1, "page_size": 10, "order_status": 12})
    second = service.sync_open_platform_list_orders(client, {"page_no": 1, "page_size": 10, "order_status": 12})
    trace = service.trace_order("xy-sync-1")

    assert first["success"] is True
    assert first["total"] == 1
    assert first["changed"] == 1
    assert second["changed"] == 0
    assert trace["order"]["status"] == "processing"
    assert trace["order"]["item_type"] == "physical"
    assert trace["order"]["quote_snapshot"]["open_platform"]["order_status"] == 12
    assert trace["order"]["quote_snapshot"]["open_platform"]["source"] == "list_orders"
    assert len([ev for ev in trace["events"] if ev["event_type"] == "status_sync"]) == 1
    assert len(client.calls) == 2


def test_sync_open_platform_order_detail_merges_snapshot_idempotently(temp_dir) -> None:
    class _Client:
        def get_order_detail(self, payload):
            assert payload == {"order_no": "xy-sync-detail"}
            return {
                "order_no": "xy-sync-detail",
                "order_status": 21,
                "consign_type": 1,
                "receiver_name": "李四",
                "receiver_mobile": "13800138001",
                "address": "科技园一路88号",
                "waybill_no": "SF23817389113",
                "express_code": "shunfeng",
                "express_name": "顺丰速运",
                "goods": {"title": "公交卡测试", "product_id": 2002},
                "update_time": 1700000010,
            }

    service = OrderFulfillmentService(db_path=str(temp_dir / "orders_sync_detail.db"))
    service.upsert_order(
        order_id="xy-sync-detail",
        raw_status="待付款",
        session_id="session-sync-detail",
        quote_snapshot={"quote_result": {"total_fee": 19.9}},
        item_type="virtual",
    )

    first = service.sync_open_platform_order_detail(_Client(), order_no="xy-sync-detail")
    second = service.sync_open_platform_order_detail(_Client(), order_no="xy-sync-detail")
    trace = service.trace_order("xy-sync-detail")

    assert first["success"] is True
    assert first["changed"] is True
    assert second["changed"] is False
    assert trace["order"]["session_id"] == "session-sync-detail"
    assert trace["order"]["status"] == "shipping"
    assert trace["order"]["item_type"] == "physical"
    assert trace["order"]["quote_snapshot"]["quote_result"]["total_fee"] == 19.9
    assert trace["order"]["quote_snapshot"]["shipping_info"]["waybill_no"] == "SF23817389113"
    assert trace["order"]["quote_snapshot"]["open_platform"]["source"] == "get_order_detail"
    assert len([ev for ev in trace["events"] if ev["event_type"] == "status_sync"]) == 2


def test_order_upsert_and_trace(temp_dir) -> None:
    service = OrderFulfillmentService(db_path=str(temp_dir / "orders.db"))

    order = service.upsert_order(
        order_id="o1",
        raw_status="待发货",
        session_id="s1",
        quote_snapshot={"total_fee": 19.9},
        item_type="virtual",
    )
    trace = service.trace_order("o1")

    assert order["status"] == "processing"
    assert order["session_id"] == "s1"
    assert trace["order"]["quote_snapshot"]["total_fee"] == 19.9
    assert trace["events"][0]["event_type"] == "status_sync"


def test_order_manual_takeover_and_resume(temp_dir) -> None:
    service = OrderFulfillmentService(db_path=str(temp_dir / "orders.db"))
    service.upsert_order(order_id="o2", raw_status="待发货", item_type="physical")

    assert service.set_manual_takeover("o2", True) is True
    blocked = service.deliver("o2")
    assert blocked["handled"] is False
    assert blocked["reason"] == "manual_takeover"

    assert service.set_manual_takeover("o2", False) is True
    delivered = service.deliver("o2")
    assert delivered["handled"] is True
    assert delivered["status"] == "processing"


def test_order_after_sales_template(temp_dir) -> None:
    service = OrderFulfillmentService(db_path=str(temp_dir / "orders.db"))
    service.upsert_order(order_id="o3", raw_status="已付款", item_type="virtual")

    case = service.create_after_sales_case("o3", issue_type="refund")

    assert case["status"] == "after_sales"
    assert "退款" in case["reply_template"]


def test_order_summary_and_list(temp_dir) -> None:
    service = OrderFulfillmentService(db_path=str(temp_dir / "orders.db"))
    service.upsert_order(order_id="s1", raw_status="已付款", session_id="session_1", item_type="virtual")
    service.upsert_order(order_id="s2", raw_status="售后中", session_id="session_2", item_type="virtual")
    service.set_manual_takeover("s2", True)

    summary = service.get_summary()
    active = service.list_orders(status="after_sales", include_manual=False, limit=20)
    all_after_sales = service.list_orders(status="after_sales", include_manual=True, limit=20)

    assert summary["total_orders"] == 2
    assert summary["manual_takeover_orders"] == 1
    assert summary["after_sales_orders"] == 1
    assert len(active) == 0
    assert len(all_after_sales) == 1


def test_record_after_sales_followup_event(temp_dir) -> None:
    service = OrderFulfillmentService(db_path=str(temp_dir / "orders.db"))
    service.upsert_order(order_id="s3", raw_status="售后中", session_id="session_3", item_type="virtual")

    recorded = service.record_after_sales_followup(
        order_id="s3",
        issue_type="delay",
        reply_text="已为您加急处理",
        sent=True,
        dry_run=False,
        reason="sent",
        session_id="session_3",
    )
    trace = service.trace_order("s3")

    assert recorded["sent"] is True
    assert trace["events"][-1]["event_type"] == "after_sales_followup"
    assert trace["events"][-1]["detail"]["reason"] == "sent"


def test_order_physical_delivery_prefers_xianguanjia_shipping(temp_dir) -> None:
    api = Mock()
    api.list_express_companies = Mock(return_value=Mock(ok=True, data=[{"express_code": "YTO", "express_name": "圆通"}]))
    api.delivery_order = Mock(return_value=Mock(ok=True))

    service = OrderFulfillmentService(db_path=str(temp_dir / "orders_ship.db"), shipping_api_client=api)
    service.upsert_order(
        order_id="o_ship",
        raw_status="待发货",
        item_type="physical",
        quote_snapshot={
            "shipping_info": {
                "waybill_no": "YT123456789",
                "express_name": "圆通",
                "ship_name": "张三",
                "ship_mobile": "13800138000",
            }
        },
    )

    delivered = service.deliver("o_ship")

    assert delivered["handled"] is True
    assert delivered["status"] == "shipping"
    assert delivered["delivery"]["channel"] == "xianguanjia_api"
    assert delivered["delivery"]["action"] == "ship_order_via_xianguanjia"
    api.delivery_order.assert_called_once()


def test_order_physical_delivery_falls_back_when_shipping_info_incomplete(temp_dir) -> None:
    api = Mock()
    api.list_express_companies = Mock(return_value=Mock(ok=True, data=[]))
    api.delivery_order = Mock()

    service = OrderFulfillmentService(db_path=str(temp_dir / "orders_ship_fallback.db"), shipping_api_client=api)
    service.upsert_order(
        order_id="o_fallback",
        raw_status="待发货",
        item_type="physical",
        quote_snapshot={"shipping_info": {"express_name": "未知快递"}},
    )

    delivered = service.deliver("o_fallback")

    assert delivered["handled"] is True
    assert delivered["status"] == "processing"
    assert delivered["delivery"]["channel"] == "manual_fallback"
    assert delivered["delivery"]["action"] == "create_shipping_task"
    assert delivered["delivery"]["api_error"] == "missing_waybill_no"
    api.delivery_order.assert_not_called()


def test_order_callback_triggers_auto_delivery_for_paid_physical_order(temp_dir) -> None:
    api = Mock()
    api.list_express_companies = Mock(return_value=Mock(ok=True, data=[{"express_code": "YTO", "express_name": "圆通"}]))
    api.delivery_order = Mock(return_value=Mock(ok=True))

    service = OrderFulfillmentService(db_path=str(temp_dir / "orders_callback.db"), shipping_api_client=api)

    out = service.process_callback(
        {
            "order_id": "o_callback",
            "status": "已付款",
            "item_type": "physical",
            "shipping_info": {
                "waybill_no": "YT123456789",
                "express_name": "圆通",
            },
        },
        auto_deliver=True,
    )

    assert out["success"] is True
    assert out["auto_delivery_triggered"] is True
    assert out["order"]["status"] == "shipping"
    assert out["delivery"]["delivery"]["channel"] == "xianguanjia_api"
    api.delivery_order.assert_called_once()


def test_order_callback_upserts_without_auto_delivery_when_disabled(temp_dir) -> None:
    api = Mock()
    service = OrderFulfillmentService(db_path=str(temp_dir / "orders_callback_idle.db"), shipping_api_client=api)

    out = service.process_callback(
        {
            "orderNo": "o_callback_idle",
            "tradeStatus": "已付款",
            "shipping_info": {"waybill_no": "YT123456789"},
        },
        auto_deliver=False,
    )

    assert out["success"] is True
    assert out["auto_delivery_triggered"] is False
    assert out["order"]["status"] == "paid"
    api.ship_order.assert_not_called()


def test_order_callback_external_event_id_is_idempotent(temp_dir) -> None:
    api = Mock()
    api.list_express_companies = Mock(return_value=Mock(ok=True, data=[{"express_code": "YTO", "express_name": "圆通"}]))
    api.delivery_order = Mock(return_value=Mock(ok=True))

    service = OrderFulfillmentService(db_path=str(temp_dir / "orders_callback_idempotent.db"), shipping_api_client=api)

    payload = {
        "order_id": "o_callback_idempotent",
        "status": "已付款",
        "item_type": "physical",
        "external_event_id": "evt_xy_001",
        "shipping_info": {
            "waybill_no": "YT123456789",
            "express_name": "圆通",
        },
    }

    first = service.process_callback(payload, auto_deliver=True)
    second = service.process_callback(payload, auto_deliver=True)

    assert first["success"] is True
    assert first["duplicate"] is False
    assert first["external_event_id"] == "evt_xy_001"
    assert first["auto_delivery_triggered"] is True

    assert second["success"] is True
    assert second["duplicate"] is True
    assert second["external_event_id"] == "evt_xy_001"
    assert second["auto_delivery_triggered"] is False

    trace = service.trace_order("o_callback_idempotent")
    status_sync_count = sum(1 for ev in trace["events"] if ev["event_type"] == "status_sync")
    assert status_sync_count == 1
    api.delivery_order.assert_called_once()

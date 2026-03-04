"""订单履约模块测试。"""

from unittest.mock import Mock

from src.modules.orders.service import OrderFulfillmentService


def test_order_status_mapping(temp_dir) -> None:
    service = OrderFulfillmentService(db_path=str(temp_dir / "orders.db"))

    assert service.map_status("待发货") == "processing"
    assert service.map_status("已完成") == "completed"
    assert service.map_status("退款中") == "after_sales"


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
    api.find_express_company = Mock(return_value={"express_code": "YTO", "express_name": "圆通"})
    api.ship_order = Mock(return_value={"code": 0, "data": {"ok": True}})

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
    api.ship_order.assert_called_once()


def test_order_physical_delivery_falls_back_when_shipping_info_incomplete(temp_dir) -> None:
    api = Mock()
    api.find_express_company = Mock(return_value=None)
    api.ship_order = Mock()

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
    api.ship_order.assert_not_called()


def test_order_callback_triggers_auto_delivery_for_paid_physical_order(temp_dir) -> None:
    api = Mock()
    api.find_express_company = Mock(return_value={"express_code": "YTO", "express_name": "圆通"})
    api.ship_order = Mock(return_value={"code": 0, "data": {"ok": True}})

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
    api.ship_order.assert_called_once()


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
    api.find_express_company = Mock(return_value={"express_code": "YTO", "express_name": "圆通"})
    api.ship_order = Mock(return_value={"code": 0, "data": {"ok": True}})

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
    api.ship_order.assert_called_once()

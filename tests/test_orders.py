"""订单履约模块测试。"""

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
    assert delivered["status"] == "shipping"


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

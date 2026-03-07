from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.modules.orders.service import OrderFulfillmentService


def _make_service(tmp_path=None, **kwargs):
    db_path = str(tmp_path / "orders.db") if tmp_path else str(Path(tempfile.mkdtemp()) / "orders.db")
    return OrderFulfillmentService(db_path=db_path, **kwargs)


class TestBuildShippingApiClient:
    def test_no_config(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc._build_shipping_api_client() is None

    def test_disabled(self, tmp_path):
        svc = _make_service(tmp_path, config={"xianguanjia": {"enabled": False}})
        assert svc._build_shipping_api_client() is None

    def test_missing_keys(self, tmp_path):
        svc = _make_service(tmp_path, config={"xianguanjia": {"enabled": True, "app_key": "k", "app_secret": ""}})
        assert svc._build_shipping_api_client() is None

    def test_success(self, tmp_path):
        svc = _make_service(tmp_path, config={"xianguanjia": {"enabled": True, "app_key": "k", "app_secret": "s"}})
        client = svc._build_shipping_api_client()
        assert client is not None


class TestExtractShippingInfo:
    def test_direct(self):
        result = OrderFulfillmentService._extract_shipping_info(
            {"shipping_info": {"addr": "A"}}, {}
        )
        assert result == {"addr": "A"}

    def test_nested(self):
        result = OrderFulfillmentService._extract_shipping_info(
            {"shipping": {"addr": "B"}}, {}
        )
        assert result == {"addr": "B"}

    def test_from_snapshot(self):
        result = OrderFulfillmentService._extract_shipping_info(
            {}, {"shipping_info": {"addr": "C"}}
        )
        assert result == {"addr": "C"}

    def test_empty(self):
        result = OrderFulfillmentService._extract_shipping_info({}, {})
        assert result == {}


class TestNormalizeItemType:
    def test_physical(self):
        assert OrderFulfillmentService._normalize_item_type("physical", {}) == "physical"
        assert OrderFulfillmentService._normalize_item_type("实物", {}) == "physical"

    def test_virtual(self):
        assert OrderFulfillmentService._normalize_item_type("virtual", {}) == "virtual"
        assert OrderFulfillmentService._normalize_item_type("卡密", {}) == "virtual"

    def test_with_shipping_info(self):
        assert OrderFulfillmentService._normalize_item_type("", {"addr": "x"}) == "physical"

    def test_default_virtual(self):
        assert OrderFulfillmentService._normalize_item_type("", {}) == "virtual"


class TestCoerceInt:
    def test_none(self):
        assert OrderFulfillmentService._coerce_int(None) is None

    def test_empty_string(self):
        assert OrderFulfillmentService._coerce_int("") is None

    def test_valid_int(self):
        assert OrderFulfillmentService._coerce_int("42") == 42
        assert OrderFulfillmentService._coerce_int(42) == 42

    def test_invalid(self):
        assert OrderFulfillmentService._coerce_int("abc") is None


class TestMapStatus:
    def test_known_status(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.map_status("待付款") == "pending"
        assert svc.map_status("已完成") == "completed"

    def test_text_match(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.map_status("payment_done") == "paid"
        assert svc.map_status("shipped") == "shipping"
        assert svc.map_status("after_sales_case") == "after_sales"
        assert svc.map_status("completed_ok") == "completed"
        assert svc.map_status("cancelled") == "closed"

    def test_default(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.map_status("xyz") == "processing"


class TestMapOpenPlatformStatus:
    def test_valid(self):
        assert OrderFulfillmentService.map_open_platform_status(11) == "pending"
        assert OrderFulfillmentService.map_open_platform_status("22") == "completed"

    def test_invalid(self):
        with pytest.raises(ValueError):
            OrderFulfillmentService.map_open_platform_status(99)

    def test_none(self):
        with pytest.raises(ValueError):
            OrderFulfillmentService.map_open_platform_status(None)


class TestUpsertOrder:
    def test_basic_upsert(self, tmp_path):
        svc = _make_service(tmp_path)
        order = svc.upsert_order("o1", "已付款", session_id="s1")
        assert order["order_id"] == "o1"
        assert order["status"] == "paid"

    def test_idempotent_no_change(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.upsert_order("o1", "已付款", session_id="s1", item_type="virtual", quote_snapshot={})
        order = svc.upsert_order("o1", "已付款", session_id="s1", item_type="virtual", quote_snapshot={}, idempotent=True)
        assert order["order_id"] == "o1"


class TestMergeQuoteSnapshot:
    def test_merge_shipping_info(self):
        base = {"shipping_info": {"addr": "old"}, "key1": "v1"}
        incoming = {"shipping_info": {"city": "new"}, "key2": "v2"}
        result = OrderFulfillmentService._merge_quote_snapshot(base, incoming)
        assert result["shipping_info"]["addr"] == "old"
        assert result["shipping_info"]["city"] == "new"
        assert result["key1"] == "v1"
        assert result["key2"] == "v2"

    def test_merge_open_platform(self):
        base = {"open_platform": {"source": "old"}}
        incoming = {"open_platform": {"order_status": 12}}
        result = OrderFulfillmentService._merge_quote_snapshot(base, incoming)
        assert result["open_platform"]["source"] == "old"
        assert result["open_platform"]["order_status"] == 12

    def test_merge_none(self):
        result = OrderFulfillmentService._merge_quote_snapshot(None, None)
        assert result == {}


class TestBuildOpenPlatformSnapshot:
    def test_basic(self):
        payload = {
            "order_no": "ON1",
            "receiver_name": "Bob",
            "order_status": 12,
            "goods": {"name": "item1"},
        }
        result = OrderFulfillmentService._build_open_platform_snapshot(payload, source="callback")
        assert "shipping_info" in result
        assert result["shipping_info"]["order_no"] == "ON1"
        assert result["goods"]["name"] == "item1"
        assert result["open_platform"]["source"] == "callback"


class TestItemTypeFromOpenPlatform:
    def test_consign_type_2(self):
        assert OrderFulfillmentService._item_type_from_open_platform({"consign_type": 2}, {}) == "virtual"

    def test_consign_type_1(self):
        assert OrderFulfillmentService._item_type_from_open_platform({"consign_type": 1}, {}) == "physical"

    def test_no_consign_type(self):
        assert OrderFulfillmentService._item_type_from_open_platform({}, {}) == "virtual"


class TestExtractOpenPlatformPayload:
    def test_response_ok(self):
        resp = MagicMock()
        resp.ok = True
        resp.data = {"key": "val"}
        result = OrderFulfillmentService._extract_open_platform_payload(resp, path="test")
        assert result == {"key": "val"}

    def test_response_not_ok(self):
        resp = MagicMock()
        resp.ok = False
        resp.error_message = "fail"
        with pytest.raises(ValueError, match="fail"):
            OrderFulfillmentService._extract_open_platform_payload(resp, path="test")

    def test_response_not_ok_no_message(self):
        resp = MagicMock()
        resp.ok = False
        resp.error_message = ""
        with pytest.raises(ValueError, match="test failed"):
            OrderFulfillmentService._extract_open_platform_payload(resp, path="test")

    def test_dict_with_code_success(self):
        result = OrderFulfillmentService._extract_open_platform_payload(
            {"code": 0, "data": {"x": 1}}, path="test"
        )
        assert result == {"x": 1}

    def test_dict_with_code_failure(self):
        with pytest.raises(ValueError, match="bad"):
            OrderFulfillmentService._extract_open_platform_payload(
                {"code": 1, "msg": "bad"}, path="test"
            )

    def test_dict_with_code_failure_message_key(self):
        with pytest.raises(ValueError, match="error msg"):
            OrderFulfillmentService._extract_open_platform_payload(
                {"code": 2, "message": "error msg"}, path="test"
            )

    def test_dict_with_code_failure_no_msg(self):
        with pytest.raises(ValueError, match="test failed"):
            OrderFulfillmentService._extract_open_platform_payload(
                {"code": 3}, path="test"
            )

    def test_plain_response(self):
        result = OrderFulfillmentService._extract_open_platform_payload("hello", path="test")
        assert result == "hello"


class TestFindExpressCompany:
    def test_no_client(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.shipping_api_client = None
        assert svc._find_express_company("sf") is None

    def test_empty_keyword(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.shipping_api_client = MagicMock()
        assert svc._find_express_company("") is None

    def test_api_failure(self, tmp_path):
        svc = _make_service(tmp_path)
        mock_client = MagicMock()
        resp = MagicMock()
        resp.ok = False
        mock_client.list_express_companies.return_value = resp
        svc.shipping_api_client = mock_client
        assert svc._find_express_company("sf") is None

    def test_found(self, tmp_path):
        svc = _make_service(tmp_path)
        mock_client = MagicMock()
        resp = MagicMock()
        resp.ok = True
        resp.data = [
            {"express_code": "SF", "express_name": "顺丰速运"},
            {"express_code": "YTO", "express_name": "圆通速递"},
        ]
        mock_client.list_express_companies.return_value = resp
        svc.shipping_api_client = mock_client
        result = svc._find_express_company("顺丰")
        assert result["express_code"] == "SF"

    def test_not_found(self, tmp_path):
        svc = _make_service(tmp_path)
        mock_client = MagicMock()
        resp = MagicMock()
        resp.ok = True
        resp.data = [{"express_code": "SF", "express_name": "顺丰"}]
        mock_client.list_express_companies.return_value = resp
        svc.shipping_api_client = mock_client
        assert svc._find_express_company("中通") is None

    def test_non_dict_row(self, tmp_path):
        svc = _make_service(tmp_path)
        mock_client = MagicMock()
        resp = MagicMock()
        resp.ok = True
        resp.data = ["not_a_dict", {"express_code": "SF", "express_name": "顺丰"}]
        mock_client.list_express_companies.return_value = resp
        svc.shipping_api_client = mock_client
        result = svc._find_express_company("顺丰")
        assert result is not None


class TestShipViaXianguanjia:
    def test_no_client(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.shipping_api_client = None
        detail, err = svc._ship_via_xianguanjia("o1", {}, False)
        assert detail is None
        assert err is None

    def test_missing_waybill_no(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.shipping_api_client = MagicMock()
        detail, err = svc._ship_via_xianguanjia("o1", {"express_code": "SF"}, False)
        assert detail is None
        assert err == "missing_waybill_no"

    def test_missing_express_code(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.shipping_api_client = MagicMock()
        svc.shipping_api_client.list_express_companies.return_value = MagicMock(ok=False)
        detail, err = svc._ship_via_xianguanjia("o1", {"waybill_no": "W1", "express_name": "XX"}, False)
        assert detail is None
        assert err == "missing_express_code"

    def test_dry_run(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.shipping_api_client = MagicMock()
        detail, err = svc._ship_via_xianguanjia(
            "o1", {"waybill_no": "W1", "express_code": "SF"}, True
        )
        assert detail["dry_run"] is True
        assert err is None

    def test_api_success(self, tmp_path):
        svc = _make_service(tmp_path)
        mock_client = MagicMock()
        resp = MagicMock()
        resp.ok = True
        mock_client.delivery_order.return_value = resp
        svc.shipping_api_client = mock_client
        detail, err = svc._ship_via_xianguanjia(
            "o1",
            {"waybill_no": "W1", "express_code": "SF", "express_name": "顺丰", "ship_name": "Bob"},
            False,
        )
        assert detail is not None
        assert detail["dry_run"] is False
        assert err is None

    def test_api_failure(self, tmp_path):
        svc = _make_service(tmp_path)
        mock_client = MagicMock()
        resp = MagicMock()
        resp.ok = False
        resp.error_message = "api error"
        mock_client.delivery_order.return_value = resp
        svc.shipping_api_client = mock_client
        detail, err = svc._ship_via_xianguanjia("o1", {"waybill_no": "W1", "express_code": "SF"}, False)
        assert detail is None
        assert err == "api error"

    def test_lookup_express_code(self, tmp_path):
        svc = _make_service(tmp_path)
        mock_client = MagicMock()
        express_resp = MagicMock()
        express_resp.ok = True
        express_resp.data = [{"express_code": "YTO", "express_name": "圆通"}]
        mock_client.list_express_companies.return_value = express_resp
        delivery_resp = MagicMock()
        delivery_resp.ok = True
        mock_client.delivery_order.return_value = delivery_resp
        svc.shipping_api_client = mock_client
        detail, err = svc._ship_via_xianguanjia(
            "o1", {"waybill_no": "W1", "express_name": "圆通"}, False
        )
        assert detail is not None
        assert err is None


class TestDeliver:
    def test_order_not_found(self, tmp_path):
        svc = _make_service(tmp_path)
        with pytest.raises(ValueError, match="Order not found"):
            svc.deliver("nonexistent")

    def test_manual_takeover(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.upsert_order("o1", "已付款")
        svc.set_manual_takeover("o1", True)
        result = svc.deliver("o1")
        assert result["handled"] is False
        assert result["reason"] == "manual_takeover"

    def test_virtual_delivery(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.upsert_order("o1", "已付款", item_type="virtual")
        result = svc.deliver("o1")
        assert result["handled"] is True
        assert result["delivery"]["action"] == "send_virtual_code"

    def test_physical_delivery_with_api(self, tmp_path):
        svc = _make_service(tmp_path)
        mock_client = MagicMock()
        delivery_resp = MagicMock()
        delivery_resp.ok = True
        mock_client.delivery_order.return_value = delivery_resp
        svc.shipping_api_client = mock_client
        svc.upsert_order("o1", "已付款", item_type="physical",
                         quote_snapshot={"shipping_info": {"waybill_no": "W1", "express_code": "SF"}})
        result = svc.deliver("o1")
        assert result["handled"] is True

    def test_physical_delivery_api_exception(self, tmp_path):
        svc = _make_service(tmp_path)
        mock_client = MagicMock()
        mock_client.delivery_order.side_effect = Exception("boom")
        svc.shipping_api_client = mock_client
        svc.upsert_order("o1", "已付款", item_type="physical",
                         quote_snapshot={"shipping_info": {"waybill_no": "W1", "express_code": "SF"}})
        result = svc.deliver("o1")
        assert result["handled"] is True
        assert result["delivery"]["channel"] == "manual_fallback"


class TestProcessCallback:
    def test_missing_order_id(self, tmp_path):
        svc = _make_service(tmp_path)
        with pytest.raises(ValueError, match="Missing order_id"):
            svc.process_callback({})

    def test_duplicate_event(self, tmp_path):
        svc = _make_service(tmp_path)
        payload = {"order_id": "o1", "raw_status": "已付款", "external_event_id": "ev1"}
        svc.process_callback(payload)
        result = svc.process_callback(payload)
        assert result["duplicate"] is True

    def test_auto_deliver(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.shipping_api_client = None
        payload = {
            "order_id": "o1",
            "raw_status": "已付款",
            "item_type": "physical",
            "shipping_info": {"waybill_no": "W1", "express_code": "SF"},
        }
        result = svc.process_callback(payload, auto_deliver=True)
        assert result["auto_delivery_triggered"] is True


class TestSyncOpenPlatformListOrders:
    def test_sync(self, tmp_path):
        svc = _make_service(tmp_path)
        mock_client = MagicMock()
        resp = MagicMock()
        resp.ok = True
        resp.data = {"list": [
            {"order_no": "o1", "order_status": 12},
            {"order_no": "o2", "order_status": 22},
        ]}
        mock_client.list_orders.return_value = resp
        result = svc.sync_open_platform_list_orders(mock_client)
        assert result["success"] is True
        assert result["total"] == 2

    def test_sync_list_orders_alias(self, tmp_path):
        svc = _make_service(tmp_path)
        mock_client = MagicMock()
        resp = MagicMock()
        resp.ok = True
        resp.data = {"list": []}
        mock_client.list_orders.return_value = resp
        result = svc.sync_list_orders(mock_client)
        assert result["success"] is True


class TestSyncOpenPlatformOrderDetail:
    def test_sync(self, tmp_path):
        svc = _make_service(tmp_path)
        mock_client = MagicMock()
        resp = MagicMock()
        resp.ok = True
        resp.data = {"order_no": "o1", "order_status": 12}
        mock_client.get_order_detail.return_value = resp
        result = svc.sync_open_platform_order_detail(mock_client, order_no="o1")
        assert result["success"] is True

    def test_invalid_payload(self, tmp_path):
        svc = _make_service(tmp_path)
        mock_client = MagicMock()
        resp = MagicMock()
        resp.ok = True
        resp.data = "not_a_dict"
        mock_client.get_order_detail.return_value = resp
        with pytest.raises(ValueError, match="Invalid"):
            svc.sync_open_platform_order_detail(mock_client, order_no="o1")

    def test_alias(self, tmp_path):
        svc = _make_service(tmp_path)
        mock_client = MagicMock()
        resp = MagicMock()
        resp.ok = True
        resp.data = {"order_no": "o1", "order_status": 12}
        mock_client.get_order_detail.return_value = resp
        result = svc.sync_get_order_detail(mock_client, order_no="o1")
        assert result["success"] is True


class TestShippingContextFrom:
    def test_with_override(self):
        result = OrderFulfillmentService._shipping_context_from({}, {"addr": "A"})
        assert result == {"addr": "A"}

    def test_from_quote_snapshot(self):
        order = {"quote_snapshot": {"shipping_info": {"city": "B"}}}
        result = OrderFulfillmentService._shipping_context_from(order)
        assert result == {"city": "B"}

    def test_empty(self):
        result = OrderFulfillmentService._shipping_context_from({})
        assert result == {}

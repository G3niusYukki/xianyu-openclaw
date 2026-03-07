from __future__ import annotations

import warnings
from unittest.mock import MagicMock, patch

import httpx
import pytest


class TestXianGuanJiaClientModule:
    """Tests for src.modules.orders.xianguanjia (deprecated module)."""

    def test_import_emits_deprecation_warning(self):
        import importlib
        import src.modules.orders.xianguanjia as mod
        old_classes = {
            name: getattr(mod, name)
            for name in dir(mod)
            if isinstance(getattr(mod, name), type)
        }
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            importlib.reload(mod)
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1
        for name, cls in old_classes.items():
            setattr(mod, name, cls)

    def test_canonical_json(self):
        from src.modules.orders.xianguanjia import canonical_json
        result = canonical_json({"b": 2, "a": 1})
        assert '"a":1' in result
        assert '"b":2' in result

    def test_build_sign_without_merchant(self):
        from src.modules.orders.xianguanjia import build_sign
        result = build_sign(app_key="key", app_secret="secret", timestamp="12345", body="{}")
        assert isinstance(result, str) and len(result) == 32

    def test_build_sign_with_merchant(self):
        from src.modules.orders.xianguanjia import build_sign
        result = build_sign(
            app_key="key", app_secret="secret", timestamp="12345",
            body="{}", merchant_id="m1"
        )
        assert isinstance(result, str) and len(result) == 32

    def test_api_error_str(self):
        from src.modules.orders.xianguanjia import XianGuanJiaAPIError
        err = XianGuanJiaAPIError(message="test error", status_code=400)
        assert str(err) == "test error"

    def test_client_init_missing_app_key(self):
        from src.modules.orders.xianguanjia import XianGuanJiaClient
        with pytest.raises(ValueError, match="app_key"):
            XianGuanJiaClient(app_key="", app_secret="secret")

    def test_client_init_missing_app_secret(self):
        from src.modules.orders.xianguanjia import XianGuanJiaClient
        with pytest.raises(ValueError, match="app_secret"):
            XianGuanJiaClient(app_key="key", app_secret="")

    def test_client_init_with_merchant(self):
        from src.modules.orders.xianguanjia import XianGuanJiaClient
        client = XianGuanJiaClient(app_key="key", app_secret="secret", merchant_id="m1")
        assert client.merchant_id == "m1"

    def test_signed_query_with_merchant(self):
        from src.modules.orders.xianguanjia import XianGuanJiaClient
        client = XianGuanJiaClient(app_key="key", app_secret="secret", merchant_id="m1")
        query = client._signed_query(body="{}", timestamp="12345")
        assert "merchantId" in query
        assert query["merchantId"] == "m1"

    def test_post_http_error(self):
        from src.modules.orders.xianguanjia import XianGuanJiaClient, XianGuanJiaAPIError
        client = XianGuanJiaClient(app_key="key", app_secret="secret")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("httpx.post", return_value=mock_resp):
            with pytest.raises(XianGuanJiaAPIError, match="HTTP 500"):
                client._post("/test", {})

    def test_post_invalid_response(self):
        from src.modules.orders.xianguanjia import XianGuanJiaClient, XianGuanJiaAPIError
        client = XianGuanJiaClient(app_key="key", app_secret="secret")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = "not a dict"
        with patch("httpx.post", return_value=mock_resp):
            with pytest.raises(XianGuanJiaAPIError, match="Invalid response"):
                client._post("/test", {})

    def test_post_business_error(self):
        from src.modules.orders.xianguanjia import XianGuanJiaClient, XianGuanJiaAPIError
        client = XianGuanJiaClient(app_key="key", app_secret="secret")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 1001, "msg": "business err"}
        with patch("httpx.post", return_value=mock_resp):
            with pytest.raises(XianGuanJiaAPIError, match="business err"):
                client._post("/test", {})

    def test_post_success(self):
        from src.modules.orders.xianguanjia import XianGuanJiaClient
        client = XianGuanJiaClient(app_key="key", app_secret="secret")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 0, "data": "ok"}
        with patch("httpx.post", return_value=mock_resp):
            result = client._post("/test", {})
            assert result["data"] == "ok"

    def test_edit_product_all_fields(self):
        from src.modules.orders.xianguanjia import XianGuanJiaClient
        client = XianGuanJiaClient(app_key="key", app_secret="secret")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 0, "data": {}}
        with patch("httpx.post", return_value=mock_resp):
            result = client.edit_product(
                product_id="p1", price=100, original_price=200,
                stock=10, sku_items=[{"id": "s1"}], extra={"key": "val"}
            )
            assert result["code"] == 0

    def test_edit_product_stock_all_fields(self):
        from src.modules.orders.xianguanjia import XianGuanJiaClient
        client = XianGuanJiaClient(app_key="key", app_secret="secret")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 0, "data": {}}
        with patch("httpx.post", return_value=mock_resp):
            result = client.edit_product_stock(
                product_id="p1", stock=5, sku_items=[{"id": "s1"}], extra={"k": "v"}
            )
            assert result["code"] == 0

    def test_modify_order_price(self):
        from src.modules.orders.xianguanjia import XianGuanJiaClient
        client = XianGuanJiaClient(app_key="key", app_secret="secret")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 0}
        with patch("httpx.post", return_value=mock_resp):
            result = client.modify_order_price(
                order_no="o1", order_price=100, express_fee=10, extra={"k": "v"}
            )
            assert result["code"] == 0

    def test_ship_order_with_optionals(self):
        from src.modules.orders.xianguanjia import XianGuanJiaClient
        client = XianGuanJiaClient(app_key="key", app_secret="secret")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 0}
        with patch("httpx.post", return_value=mock_resp):
            result = client.ship_order(
                order_no="o1", waybill_no="w1", express_code="YTO",
                express_name="圆通", extra={"k": "v"}
            )
            assert result["code"] == 0

    def test_list_express_companies(self):
        from src.modules.orders.xianguanjia import XianGuanJiaClient
        client = XianGuanJiaClient(app_key="key", app_secret="secret")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 0, "data": [{"express_code": "YTO"}]}
        with patch("httpx.post", return_value=mock_resp):
            result = client.list_express_companies()
            assert len(result) == 1

    def test_list_express_companies_no_list(self):
        from src.modules.orders.xianguanjia import XianGuanJiaClient
        client = XianGuanJiaClient(app_key="key", app_secret="secret")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 0, "data": "not a list"}
        with patch("httpx.post", return_value=mock_resp):
            result = client.list_express_companies()
            assert result == []

    def test_find_express_company_found(self):
        from src.modules.orders.xianguanjia import XianGuanJiaClient
        client = XianGuanJiaClient(app_key="key", app_secret="secret")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 0, "data": [
            {"express_code": "YTO", "express_name": "圆通快递"}
        ]}
        with patch("httpx.post", return_value=mock_resp):
            result = client.find_express_company("圆通")
            assert result is not None

    def test_find_express_company_empty_keyword(self):
        from src.modules.orders.xianguanjia import XianGuanJiaClient
        client = XianGuanJiaClient(app_key="key", app_secret="secret")
        assert client.find_express_company("") is None

    def test_find_express_company_not_found(self):
        from src.modules.orders.xianguanjia import XianGuanJiaClient
        client = XianGuanJiaClient(app_key="key", app_secret="secret")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 0, "data": [
            {"express_code": "YTO", "express_name": "圆通快递"}
        ]}
        with patch("httpx.post", return_value=mock_resp):
            result = client.find_express_company("不存在")
            assert result is None

    def test_find_express_company_non_dict_row(self):
        from src.modules.orders.xianguanjia import XianGuanJiaClient
        client = XianGuanJiaClient(app_key="key", app_secret="secret")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 0, "data": ["not a dict"]}
        with patch("httpx.post", return_value=mock_resp):
            result = client.find_express_company("圆通")
            assert result is None


class TestOrderSyncService:
    """Tests for src.modules.orders.sync."""

    def test_extract_orders_list(self):
        from src.modules.orders.sync import OrderSyncService
        result = OrderSyncService._extract_orders([{"order_no": "1"}, "bad", {"order_no": "2"}])
        assert len(result) == 2

    def test_extract_orders_dict_with_list_key(self):
        from src.modules.orders.sync import OrderSyncService
        result = OrderSyncService._extract_orders({"list": [{"order_no": "1"}]})
        assert len(result) == 1

    def test_extract_orders_dict_with_rows_key(self):
        from src.modules.orders.sync import OrderSyncService
        result = OrderSyncService._extract_orders({"rows": [{"id": "1"}]})
        assert len(result) == 1

    def test_extract_orders_dict_with_orders_key(self):
        from src.modules.orders.sync import OrderSyncService
        result = OrderSyncService._extract_orders({"orders": [{"id": "1"}]})
        assert len(result) == 1

    def test_extract_orders_empty(self):
        from src.modules.orders.sync import OrderSyncService
        assert OrderSyncService._extract_orders("string") == []
        assert OrderSyncService._extract_orders(None) == []
        assert OrderSyncService._extract_orders({}) == []

    def test_sync_list_fails(self):
        from src.modules.orders.sync import OrderSyncService
        mock_client = MagicMock()
        mock_store = MagicMock()
        mock_client.list_orders.return_value = MagicMock(ok=False, error_message="fail")
        svc = OrderSyncService(mock_client, mock_store)
        result = svc.sync()
        assert result["ok"] is False

    def test_sync_success(self):
        from src.modules.orders.sync import OrderSyncService
        mock_client = MagicMock()
        mock_store = MagicMock()
        list_resp = MagicMock(ok=True, data=[{"order_no": "o1"}])
        detail_resp = MagicMock(ok=True, data={"order_no": "o1", "status": "paid"})
        mock_client.list_orders.return_value = list_resp
        mock_client.get_order_detail.return_value = detail_resp
        svc = OrderSyncService(mock_client, mock_store)
        result = svc.sync()
        assert result["ok"] is True
        assert result["synced"] == 1

    def test_sync_detail_fails(self):
        from src.modules.orders.sync import OrderSyncService
        mock_client = MagicMock()
        mock_store = MagicMock()
        list_resp = MagicMock(ok=True, data=[{"order_no": "o1"}])
        detail_resp = MagicMock(ok=False)
        mock_client.list_orders.return_value = list_resp
        mock_client.get_order_detail.return_value = detail_resp
        svc = OrderSyncService(mock_client, mock_store)
        result = svc.sync()
        assert result["synced"] == 0

    def test_sync_no_order_no(self):
        from src.modules.orders.sync import OrderSyncService
        mock_client = MagicMock()
        mock_store = MagicMock()
        list_resp = MagicMock(ok=True, data=[{"no_order_no": True}])
        mock_client.list_orders.return_value = list_resp
        svc = OrderSyncService(mock_client, mock_store)
        result = svc.sync()
        assert result["synced"] == 0

    def test_sync_detail_returns_non_dict(self):
        from src.modules.orders.sync import OrderSyncService
        mock_client = MagicMock()
        mock_store = MagicMock()
        list_resp = MagicMock(ok=True, data=[{"order_no": "o1"}])
        detail_resp = MagicMock(ok=True, data="not_a_dict")
        mock_client.list_orders.return_value = list_resp
        mock_client.get_order_detail.return_value = detail_resp
        svc = OrderSyncService(mock_client, mock_store)
        result = svc.sync()
        assert result["synced"] == 1


class TestOrderStore:
    """Tests for src.modules.orders.store line 16."""

    def test_upsert_missing_order_no(self):
        from src.modules.orders.store import OrderStore
        store = OrderStore.__new__(OrderStore)
        store.vg_store = MagicMock()
        with pytest.raises(ValueError, match="missing order_no"):
            store.upsert_from_open_platform_detail({})

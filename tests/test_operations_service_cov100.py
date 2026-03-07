from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest


@pytest.fixture
def mock_api_response_ok():
    resp = MagicMock()
    resp.ok = True
    resp.data = {"list": []}
    resp.error_message = None
    return resp


@pytest.fixture
def mock_api_response_fail():
    resp = MagicMock()
    resp.ok = False
    resp.error_message = "api_error"
    return resp


@pytest.fixture
def mock_api_client(mock_api_response_ok):
    client = MagicMock()
    client.edit_product.return_value = mock_api_response_ok
    client.unpublish_product.return_value = mock_api_response_ok
    client.publish_product.return_value = mock_api_response_ok
    client.list_products.return_value = mock_api_response_ok
    client.modify_order_price.return_value = mock_api_response_ok
    return client


def _make_ops_service(api_client=None, config=None, analytics=None, controller=None):
    with patch("src.modules.operations.service.get_compliance_guard") as mock_cg, \
         patch("src.modules.operations.service.get_config") as mock_gc:
        mock_gc.return_value = MagicMock(browser={"delay": {"min": 0.01, "max": 0.02}})
        from src.modules.operations.service import OperationsService
        svc = OperationsService(
            controller=controller,
            config=config or {},
            analytics=analytics,
            api_client=api_client,
        )
    return svc


class TestBuildApiClient:
    def test_no_config(self):
        svc = _make_ops_service(config={})
        assert svc._build_api_client() is None

    def test_not_enabled(self):
        svc = _make_ops_service(config={"xianguanjia": {"enabled": False}})
        assert svc._build_api_client() is None

    def test_missing_keys(self):
        svc = _make_ops_service(config={"xianguanjia": {"enabled": True, "app_key": "", "app_secret": "s"}})
        result = svc._build_api_client()
        assert result is None

    def test_missing_secret(self):
        svc = _make_ops_service(config={"xianguanjia": {"enabled": True, "app_key": "k", "app_secret": ""}})
        result = svc._build_api_client()
        assert result is None

    def test_success(self):
        with patch("src.modules.operations.service.OpenPlatformClient") as MockClient:
            MockClient.return_value = MagicMock()
            svc = _make_ops_service(config={"xianguanjia": {
                "enabled": True, "app_key": "k", "app_secret": "s",
                "base_url": "https://test.com", "timeout": 10,
            }})
            result = svc._build_api_client()
            assert result is not None

    def test_exception(self):
        with patch("src.modules.operations.service.OpenPlatformClient", side_effect=RuntimeError("init fail")):
            svc = _make_ops_service(config={"xianguanjia": {
                "enabled": True, "app_key": "k", "app_secret": "s",
            }})
            result = svc._build_api_client()
            assert result is None


class TestRandomDelay:
    def test_random_delay(self):
        svc = _make_ops_service()
        d = svc._random_delay(min_factor=1.0, max_factor=1.0)
        assert isinstance(d, float)
        assert d >= 0


class TestTryUpdatePriceViaApi:
    @pytest.mark.asyncio
    async def test_no_api_client(self):
        svc = _make_ops_service(api_client=None)
        result, error = await svc._try_update_price_via_api("prod1", 10.0)
        assert result is None
        assert error == "api_client_not_configured"

    @pytest.mark.asyncio
    async def test_success(self, mock_api_client):
        svc = _make_ops_service(api_client=mock_api_client)
        result, error = await svc._try_update_price_via_api("prod1", 10.0, 12.0)
        assert result is not None
        assert result["success"] is True
        assert error is None

    @pytest.mark.asyncio
    async def test_api_call_failed(self, mock_api_client, mock_api_response_fail):
        mock_api_client.edit_product.return_value = mock_api_response_fail
        svc = _make_ops_service(api_client=mock_api_client)
        result, error = await svc._try_update_price_via_api("prod1", 10.0)
        assert result is None
        assert error == "api_error"

    @pytest.mark.asyncio
    async def test_exception(self, mock_api_client):
        mock_api_client.edit_product.side_effect = RuntimeError("timeout")
        svc = _make_ops_service(api_client=mock_api_client)
        result, error = await svc._try_update_price_via_api("prod1", 10.0)
        assert result is None
        assert "timeout" in error


class TestModifyOrderPrice:
    @pytest.mark.asyncio
    async def test_no_api_client(self):
        svc = _make_ops_service(api_client=None)
        result = await svc.modify_order_price("order1", 100)
        assert result["success"] is False
        assert result["error"] == "api_client_not_configured"

    @pytest.mark.asyncio
    async def test_success(self, mock_api_client):
        svc = _make_ops_service(api_client=mock_api_client)
        result = await svc.modify_order_price("order1", 100, express_fee=10)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_api_fail(self, mock_api_client, mock_api_response_fail):
        mock_api_client.modify_order_price.return_value = mock_api_response_fail
        svc = _make_ops_service(api_client=mock_api_client)
        result = await svc.modify_order_price("order1", 100)
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_exception(self, mock_api_client):
        mock_api_client.modify_order_price.side_effect = RuntimeError("network")
        svc = _make_ops_service(api_client=mock_api_client)
        result = await svc.modify_order_price("order1", 100)
        assert result["success"] is False
        assert "network" in result["error"]


class TestDelist:
    @pytest.mark.asyncio
    async def test_no_api_client(self):
        svc = _make_ops_service(api_client=None)
        result = await svc.delist("prod1")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_success(self, mock_api_client):
        svc = _make_ops_service(api_client=mock_api_client)
        result = await svc.delist("prod1", reason="test")
        assert result["success"] is True
        assert result["channel"] == "xianguanjia_api"

    @pytest.mark.asyncio
    async def test_api_fail(self, mock_api_client, mock_api_response_fail):
        mock_api_client.unpublish_product.return_value = mock_api_response_fail
        svc = _make_ops_service(api_client=mock_api_client)
        result = await svc.delist("prod1")
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_with_analytics(self, mock_api_client):
        analytics = MagicMock()
        analytics.log_operation = AsyncMock()
        svc = _make_ops_service(api_client=mock_api_client, analytics=analytics)
        result = await svc.delist("prod1")
        assert result["success"] is True
        analytics.log_operation.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception(self, mock_api_client):
        mock_api_client.unpublish_product.side_effect = RuntimeError("net")
        svc = _make_ops_service(api_client=mock_api_client)
        result = await svc.delist("prod1")
        assert result["success"] is False
        assert "net" in result["error"]


class TestRelist:
    @pytest.mark.asyncio
    async def test_no_api_client(self):
        svc = _make_ops_service(api_client=None)
        result = await svc.relist("prod1")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_success(self, mock_api_client):
        svc = _make_ops_service(api_client=mock_api_client)
        result = await svc.relist("prod1")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_api_fail(self, mock_api_client, mock_api_response_fail):
        mock_api_client.publish_product.return_value = mock_api_response_fail
        svc = _make_ops_service(api_client=mock_api_client)
        result = await svc.relist("prod1")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_with_analytics(self, mock_api_client):
        analytics = MagicMock()
        analytics.log_operation = AsyncMock()
        svc = _make_ops_service(api_client=mock_api_client, analytics=analytics)
        result = await svc.relist("prod1")
        analytics.log_operation.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception(self, mock_api_client):
        mock_api_client.publish_product.side_effect = RuntimeError("err")
        svc = _make_ops_service(api_client=mock_api_client)
        result = await svc.relist("prod1")
        assert result["success"] is False


class TestRefreshInventory:
    @pytest.mark.asyncio
    async def test_no_api_client(self):
        svc = _make_ops_service(api_client=None)
        result = await svc.refresh_inventory()
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_success(self, mock_api_client, mock_api_response_ok):
        mock_api_response_ok.data = {"list": [{"id": "1"}, {"id": "2"}]}
        svc = _make_ops_service(api_client=mock_api_client)
        result = await svc.refresh_inventory()
        assert result["success"] is True
        assert result["total_items"] == 2

    @pytest.mark.asyncio
    async def test_api_fail(self, mock_api_client, mock_api_response_fail):
        mock_api_client.list_products.return_value = mock_api_response_fail
        svc = _make_ops_service(api_client=mock_api_client)
        result = await svc.refresh_inventory()
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_exception(self, mock_api_client):
        mock_api_client.list_products.side_effect = RuntimeError("fail")
        svc = _make_ops_service(api_client=mock_api_client)
        result = await svc.refresh_inventory()
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_data_not_dict(self, mock_api_client, mock_api_response_ok):
        mock_api_response_ok.data = None
        svc = _make_ops_service(api_client=mock_api_client)
        result = await svc.refresh_inventory()
        assert result["success"] is True
        assert result["total_items"] == 0


class TestGetListingStats:
    @pytest.mark.asyncio
    async def test_no_api_client(self):
        svc = _make_ops_service(api_client=None)
        result = await svc.get_listing_stats()
        assert result.get("error") == "api_client_not_configured"

    @pytest.mark.asyncio
    async def test_success(self, mock_api_client, mock_api_response_ok):
        mock_api_response_ok.data = {"list": [
            {"status": 1, "view_count": 10, "want_count": 2},
            {"status": "on_sale", "view_count": 5, "want_count": 3},
        ]}
        svc = _make_ops_service(api_client=mock_api_client)
        result = await svc.get_listing_stats()
        assert result["total"] == 2
        assert result["active"] == 2
        assert result["total_views"] == 15

    @pytest.mark.asyncio
    async def test_api_fail(self, mock_api_client, mock_api_response_fail):
        mock_api_client.list_products.return_value = mock_api_response_fail
        svc = _make_ops_service(api_client=mock_api_client)
        result = await svc.get_listing_stats()
        assert "error" in result

    @pytest.mark.asyncio
    async def test_exception(self, mock_api_client):
        mock_api_client.list_products.side_effect = RuntimeError("net")
        svc = _make_ops_service(api_client=mock_api_client)
        result = await svc.get_listing_stats()
        assert "error" in result

    @pytest.mark.asyncio
    async def test_items_not_list(self, mock_api_client, mock_api_response_ok):
        mock_api_response_ok.data = {"list": "not_a_list"}
        svc = _make_ops_service(api_client=mock_api_client)
        result = await svc.get_listing_stats()
        assert result["total"] == 0


class TestTimestampAndContract:
    def test_ts(self):
        from src.modules.operations.service import OperationsService
        ts = OperationsService._ts()
        assert "T" in ts
        assert ts.endswith("Z")

    def test_exec_contract(self):
        from src.modules.operations.service import OperationsService
        result = OperationsService._exec_contract(
            ok=True, action="test", code="OK", message="success",
            data={"k": "v"}, errors=[{"e": "err"}],
        )
        assert result["ok"] is True
        assert result["action"] == "test"
        assert result["data"]["k"] == "v"
        assert len(result["errors"]) == 1
        assert "ts" in result


class TestExecuteProductAction:
    @pytest.mark.asyncio
    async def test_without_listing_id(self, mock_api_client):
        svc = _make_ops_service(api_client=mock_api_client)
        with patch("src.modules.operations.service.ListingService") as MockLS:
            mock_ls = MagicMock()
            mock_ls.execute_product_action = AsyncMock(return_value={"ok": True})
            MockLS.return_value = mock_ls
            result = await svc.execute_product_action("edit", payload={"title": "T"})
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_with_listing_id(self, mock_api_client):
        svc = _make_ops_service(api_client=mock_api_client)
        with patch("src.modules.operations.service.ListingService") as MockLS:
            mock_ls = MagicMock()
            mock_ls.execute_product_action = AsyncMock(return_value={"ok": True})
            MockLS.return_value = mock_ls
            result = await svc.execute_product_action(
                "edit",
                payload={"title": "T", "price": 10, "images": ["img.png"]},
                internal_listing_id="lid1",
            )
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_with_custom_api_client(self, mock_api_client):
        svc = _make_ops_service(api_client=None)
        with patch("src.modules.operations.service.ListingService") as MockLS:
            mock_ls = MagicMock()
            mock_ls.execute_product_action = AsyncMock(return_value={"ok": True})
            MockLS.return_value = mock_ls
            result = await svc.execute_product_action(
                "edit", api_client=mock_api_client,
            )
        assert result["ok"] is True


class TestPolishListing:
    @pytest.mark.asyncio
    async def test_disabled(self, mock_api_client):
        svc = _make_ops_service(api_client=mock_api_client)
        result = await svc.polish_listing("prod1")
        assert result["success"] is False
        assert result["error"] == "feature_disabled"


class TestBatchPolish:
    @pytest.mark.asyncio
    async def test_disabled(self, mock_api_client):
        svc = _make_ops_service(api_client=mock_api_client)
        result = await svc.batch_polish()
        assert result["blocked"] is True


class TestUpdatePrice:
    @pytest.mark.asyncio
    async def test_success_with_analytics(self, mock_api_client):
        analytics = MagicMock()
        analytics.log_operation = AsyncMock()
        svc = _make_ops_service(api_client=mock_api_client, analytics=analytics)
        result = await svc.update_price("prod1", 10.0, 12.0)
        assert result["success"] is True
        analytics.log_operation.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure_with_analytics(self, mock_api_client):
        mock_api_client.edit_product.return_value = MagicMock(ok=False, error_message="fail")
        analytics = MagicMock()
        analytics.log_operation = AsyncMock()
        svc = _make_ops_service(api_client=mock_api_client, analytics=analytics)
        result = await svc.update_price("prod1", 10.0)
        assert result["success"] is False
        assert result["channel"] == "xianguanjia_api"
        analytics.log_operation.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure_no_analytics(self):
        svc = _make_ops_service(api_client=None)
        result = await svc.update_price("prod1", 10.0)
        assert result["success"] is False


class TestBatchUpdatePrice:
    @pytest.mark.asyncio
    async def test_batch_success(self, mock_api_client):
        svc = _make_ops_service(api_client=mock_api_client)
        updates = [
            {"product_id": "p1", "new_price": 10.0},
            {"product_id": "p2", "new_price": 20.0},
        ]
        result = await svc.batch_update_price(updates, delay_range=(0.001, 0.002))
        assert result["total"] == 2
        assert result["success"] >= 0

    @pytest.mark.asyncio
    async def test_batch_with_exception(self, mock_api_client):
        svc = _make_ops_service(api_client=mock_api_client)
        with patch.object(svc, "update_price", new_callable=AsyncMock, side_effect=RuntimeError("update boom")):
            updates = [{"product_id": "p1", "new_price": 10.0}]
            result = await svc.batch_update_price(updates, delay_range=(0.001, 0.002))
        assert result["total"] == 1
        assert result["failed"] == 1

    @pytest.mark.asyncio
    async def test_batch_with_analytics(self, mock_api_client):
        analytics = MagicMock()
        analytics.log_operation = AsyncMock()
        svc = _make_ops_service(api_client=mock_api_client, analytics=analytics)
        updates = [{"product_id": "p1", "new_price": 10.0}]
        result = await svc.batch_update_price(updates, delay_range=(0.001, 0.002))
        analytics.log_operation.assert_called()


class TestAutoAdjustPrice:
    @pytest.mark.asyncio
    async def test_invalid_max_discount(self, mock_api_client):
        svc = _make_ops_service(api_client=mock_api_client)
        result = await svc.auto_adjust_price("prod1", 100.0, max_discount_pct=1.5)
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_restore_strategy(self, mock_api_client):
        svc = _make_ops_service(api_client=mock_api_client)
        result = await svc.auto_adjust_price("prod1", 100.0, strategy="restore")
        assert result is not None

    @pytest.mark.asyncio
    async def test_price_at_floor(self, mock_api_client):
        svc = _make_ops_service(api_client=mock_api_client)
        result = await svc.auto_adjust_price("prod1", 100.0, step_amount=0, min_price=100.0)
        assert result["success"] is False
        assert result["error"] == "price_at_floor"

    @pytest.mark.asyncio
    async def test_step_down(self, mock_api_client):
        svc = _make_ops_service(api_client=mock_api_client)
        result = await svc.auto_adjust_price("prod1", 100.0, step_amount=5.0, min_price=90.0)
        assert result.get("action") == "auto_adjust_price"
        assert result.get("strategy") == "step_down"
        assert result.get("price_change") == 5.0

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from src.modules.listing.models import Listing, PublishResult
from src.modules.listing.service import ListingService


def _make_service(**kwargs):
    """Create ListingService with mocked dependencies."""
    with patch("src.modules.listing.service.get_compliance_guard") as mock_cg, \
         patch("src.modules.listing.service.get_config") as mock_gc:
        mock_cg.return_value = MagicMock()
        mock_config = MagicMock()
        mock_config.browser = {"delay": {"min": 0.001, "max": 0.002}}
        mock_gc.return_value = mock_config
        return ListingService(**kwargs)


def _make_listing(**kwargs):
    defaults = {"title": "Test Item", "description": "Desc", "price": 9.9}
    defaults.update(kwargs)
    return Listing(**defaults)


class TestBuildOpenPlatformClient:
    def test_returns_none_when_no_config(self):
        svc = _make_service()
        assert svc._build_open_platform_client() is None

    def test_returns_none_when_disabled(self):
        svc = _make_service(config={"xianguanjia": {"enabled": False}})
        assert svc._build_open_platform_client() is None

    def test_returns_none_when_missing_keys(self):
        svc = _make_service(config={"xianguanjia": {"enabled": True, "app_key": "", "app_secret": "s"}})
        assert svc._build_open_platform_client() is None

    def test_returns_none_when_missing_secret(self):
        svc = _make_service(config={"xianguanjia": {"enabled": True, "app_key": "k", "app_secret": ""}})
        assert svc._build_open_platform_client() is None

    def test_returns_client_when_configured(self):
        svc = _make_service(config={"xianguanjia": {"enabled": True, "app_key": "k", "app_secret": "s"}})
        client = svc._build_open_platform_client()
        assert client is not None


class TestBuildMappingStore:
    def test_no_db_path(self):
        svc = _make_service(config={})
        assert svc._build_mapping_store() is None

    def test_db_path_init_fails(self):
        with patch("src.modules.listing.service.VirtualGoodsStore", side_effect=Exception("db err")):
            svc = _make_service(config={"db_path": "/tmp/test.db"})
            result = svc._build_mapping_store()
            assert result is None


class TestResolveMappingStatus:
    def test_no_store(self):
        svc = _make_service()
        svc.mapping_store = None
        status, found = svc._resolve_mapping_status(internal_listing_id="x", product_id="y")
        assert status == "inactive"
        assert found is False

    def test_mapping_found_by_product_id(self):
        svc = _make_service()
        store = MagicMock()
        store.get_listing_product_mapping.return_value = {"mapping_status": "mapped"}
        svc.mapping_store = store
        status, found = svc._resolve_mapping_status(internal_listing_id=None, product_id="p1")
        assert status == "active"
        assert found is True

    def test_mapping_found_by_internal_id(self):
        svc = _make_service()
        store = MagicMock()
        store.get_listing_product_mapping.side_effect = [None, {"mapping_status": "syncing"}]
        svc.mapping_store = store
        status, found = svc._resolve_mapping_status(internal_listing_id="lid", product_id="pid")
        assert status == "pending_sync"

    def test_exception_returns_inactive(self):
        svc = _make_service()
        store = MagicMock()
        store.get_listing_product_mapping.side_effect = Exception("db err")
        svc.mapping_store = store
        status, found = svc._resolve_mapping_status(internal_listing_id="x", product_id="y")
        assert status == "inactive"
        assert found is False

    def test_no_mapping_found(self):
        svc = _make_service()
        store = MagicMock()
        store.get_listing_product_mapping.return_value = None
        svc.mapping_store = store
        status, found = svc._resolve_mapping_status(internal_listing_id=None, product_id=None)
        assert status == "inactive"


class TestPersistListingMapping:
    def test_missing_args(self):
        svc = _make_service()
        svc.mapping_store = MagicMock()
        assert svc._persist_listing_mapping(internal_listing_id=None, product_id="p") is None
        assert svc._persist_listing_mapping(internal_listing_id="i", product_id=None) is None
        svc.mapping_store = None
        assert svc._persist_listing_mapping(internal_listing_id="i", product_id="p") is None

    def test_exception(self):
        svc = _make_service()
        store = MagicMock()
        store.upsert_listing_product_mapping.side_effect = Exception("err")
        svc.mapping_store = store
        assert svc._persist_listing_mapping(internal_listing_id="i", product_id="p") is None


class TestToContractMappingStatus:
    def test_active_variants(self):
        assert ListingService._to_contract_mapping_status("mapped") == "active"
        assert ListingService._to_contract_mapping_status("active") == "active"

    def test_syncing(self):
        assert ListingService._to_contract_mapping_status("syncing") == "pending_sync"
        assert ListingService._to_contract_mapping_status("pending_sync") == "pending_sync"

    def test_failed(self):
        assert ListingService._to_contract_mapping_status("failed") == "sync_failed"
        assert ListingService._to_contract_mapping_status("sync_failed") == "sync_failed"

    def test_unknown(self):
        assert ListingService._to_contract_mapping_status(None) == "inactive"
        assert ListingService._to_contract_mapping_status("xyz") == "inactive"


class TestExecuteProductAction:
    @pytest.mark.asyncio
    async def test_unsupported_action(self):
        svc = _make_service()
        result = await svc.execute_product_action("unknown_action")
        assert result["ok"] is False
        assert result["code"] == "UNSUPPORTED_ACTION"

    @pytest.mark.asyncio
    async def test_no_client(self):
        svc = _make_service()
        result = await svc.execute_product_action("create")
        assert result["ok"] is False
        assert result["code"] == "API_CLIENT_NOT_CONFIGURED"

    @pytest.mark.asyncio
    async def test_api_success_create(self):
        svc = _make_service()
        svc.mapping_store = None
        mock_client = MagicMock()
        resp = MagicMock()
        resp.ok = True
        resp.data = {"xianyu_product_id": "pid123"}
        resp.to_dict.return_value = {"ok": True}
        mock_client.create_product.return_value = resp
        listing = _make_listing(images=["img.jpg"])
        result = await svc.execute_product_action("create", listing=listing, api_client=mock_client)
        assert result["ok"] is True
        assert result["data"]["xianyu_product_id"] == "pid123"

    @pytest.mark.asyncio
    async def test_api_success_edit(self):
        svc = _make_service()
        svc.mapping_store = None
        mock_client = MagicMock()
        resp = MagicMock()
        resp.ok = True
        resp.data = {"product_id": "p2"}
        resp.to_dict.return_value = {}
        mock_client.edit_product.return_value = resp
        result = await svc.execute_product_action("edit", payload={"product_id": "p2"}, api_client=mock_client)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_api_failure_no_fallback(self):
        svc = _make_service()
        svc.mapping_store = None
        mock_client = MagicMock()
        resp = MagicMock()
        resp.ok = False
        resp.error_code = "ERR_1"
        resp.error_message = "something went wrong"
        mock_client.create_product.return_value = resp
        result = await svc.execute_product_action("create", api_client=mock_client)
        assert result["ok"] is False
        assert result["code"] == "ERR_1"

    @pytest.mark.asyncio
    async def test_api_failure_with_fallback(self):
        svc = _make_service()
        svc.mapping_store = None
        mock_client = MagicMock()
        resp = MagicMock()
        resp.ok = False
        resp.error_code = "ERR_2"
        resp.error_message = "fail"
        mock_client.create_product.return_value = resp
        result = await svc.execute_product_action("create", api_client=mock_client, allow_dom_fallback=True)
        assert result["ok"] is False
        assert result["code"] == "DOM_FALLBACK_USED"


class TestCreateListing:
    @pytest.mark.asyncio
    async def test_exception_path(self):
        svc = _make_service()
        svc.compliance = MagicMock()
        svc.compliance.evaluate_content.side_effect = Exception("boom")
        listing = _make_listing()
        result = await svc.create_listing(listing)
        assert result.success is False
        assert result.code == "PUBLISH_FAILED"


class TestExecutePublish:
    @pytest.mark.asyncio
    async def test_dom_flow(self):
        controller = AsyncMock()
        controller.new_page.return_value = "page1"
        controller.execute_script.return_value = "https://goofish.com/success/12345"
        svc = _make_service(controller=controller)
        product_id, product_url = await svc._execute_publish(
            _make_listing(images=["img.jpg"], tags=["全新"])
        )
        assert product_id == "12345"
        controller.close_page.assert_called_once()

    @pytest.mark.asyncio
    async def test_dom_flow_verify_failure(self):
        controller = AsyncMock()
        controller.new_page.return_value = "page1"
        controller.execute_script.return_value = "https://goofish.com/other"
        svc = _make_service(controller=controller)
        from src.core.error_handler import BrowserError
        with pytest.raises(BrowserError):
            await svc._execute_publish(_make_listing(images=[]))


class TestGetMyListings:
    @pytest.mark.asyncio
    async def test_no_client(self):
        svc = _make_service()
        result = await svc.get_my_listings()
        assert result == []

    @pytest.mark.asyncio
    async def test_api_failure(self):
        svc = _make_service(config={"xianguanjia": {"enabled": True, "app_key": "k", "app_secret": "s"}})
        with patch.object(ListingService, "_build_open_platform_client") as mock_build:
            mock_client = MagicMock()
            resp = MagicMock()
            resp.ok = False
            resp.error_message = "fail"
            mock_client.list_products.return_value = resp
            mock_build.return_value = mock_client
            result = await svc.get_my_listings()
            assert result == []

    @pytest.mark.asyncio
    async def test_api_success(self):
        svc = _make_service()
        with patch.object(ListingService, "_build_open_platform_client") as mock_build:
            mock_client = MagicMock()
            resp = MagicMock()
            resp.ok = True
            resp.data = {"list": [{"id": "1"}, {"id": "2"}]}
            mock_client.list_products.return_value = resp
            mock_build.return_value = mock_client
            result = await svc.get_my_listings()
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_api_not_list(self):
        svc = _make_service()
        with patch.object(ListingService, "_build_open_platform_client") as mock_build:
            mock_client = MagicMock()
            resp = MagicMock()
            resp.ok = True
            resp.data = {"list": "not_a_list"}
            mock_client.list_products.return_value = resp
            mock_build.return_value = mock_client
            result = await svc.get_my_listings()
            assert result == []

    @pytest.mark.asyncio
    async def test_api_exception(self):
        svc = _make_service()
        with patch.object(ListingService, "_build_open_platform_client") as mock_build:
            mock_client = MagicMock()
            mock_client.list_products.side_effect = Exception("boom")
            mock_build.return_value = mock_client
            result = await svc.get_my_listings()
            assert result == []


class TestStepVerifySuccess:
    @pytest.mark.asyncio
    async def test_success_url(self):
        controller = AsyncMock()
        controller.execute_script.return_value = "https://goofish.com/success/99"
        svc = _make_service(controller=controller)
        pid, purl = await svc._step_verify_success("page1")
        assert pid == "99"

    @pytest.mark.asyncio
    async def test_failure_url(self):
        controller = AsyncMock()
        controller.execute_script.return_value = "https://goofish.com/other"
        svc = _make_service(controller=controller)
        from src.core.error_handler import BrowserError
        with pytest.raises(BrowserError):
            await svc._step_verify_success("page1")


class TestExtractProductId:
    def test_normal_url(self):
        svc = _make_service()
        assert svc._extract_product_id("https://goofish.com/item/12345") == "12345"

    def test_invalid_url(self):
        svc = _make_service()
        result = svc._extract_product_id("")
        assert isinstance(result, str)

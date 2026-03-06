from __future__ import annotations

import pytest

from src.integrations.xianguanjia.models import XianGuanJiaResponse
from src.modules.listing.models import Listing
from src.modules.listing.service import ListingService


class _StubMappingStore:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def upsert_listing_product_mapping(self, **kwargs):
        internal_listing_id = kwargs.get("internal_listing_id")
        row = {
            "xianyu_product_id": kwargs.get("xianyu_product_id"),
            "internal_listing_id": internal_listing_id,
            "mapping_status": kwargs.get("mapping_status", "mapped"),
        }
        self.rows.append(row)
        return dict(row)

    def get_listing_product_mapping(self, **kwargs):
        xianyu_product_id = kwargs.get("xianyu_product_id")
        internal_listing_id = kwargs.get("internal_listing_id")
        for row in reversed(self.rows):
            if xianyu_product_id and row.get("xianyu_product_id") == xianyu_product_id:
                return dict(row)
            if internal_listing_id and row.get("internal_listing_id") == internal_listing_id:
                return dict(row)
        return None


class _StubOpenClient:
    def create_product(self, payload: dict):
        return XianGuanJiaResponse.success(data={"product_id": "xp-200"})

    def edit_product(self, payload: dict):
        return XianGuanJiaResponse.success(data={"product_id": "xp-200"})

    def edit_stock(self, payload: dict):
        return XianGuanJiaResponse.success(data={"product_id": "xp-200"})

    def publish_product(self, payload: dict):
        return XianGuanJiaResponse.success(data={"product_id": "xp-200"})

    def unpublish_product(self, payload: dict):
        return XianGuanJiaResponse.success(data={"product_id": "xp-200"})


@pytest.mark.asyncio
async def test_wave_d_create_execute_generates_internal_listing_id_and_persists_mapping() -> None:
    store = _StubMappingStore()
    svc = ListingService(controller=None, config={}, mapping_store=store)
    listing = Listing(title="t", description="d", price=1.0, internal_listing_id=None)

    out = await svc.execute_product_action("create", payload={}, listing=listing, api_client=_StubOpenClient())

    assert listing.internal_listing_id
    assert out["ok"] is True
    assert out["data"]["internal_listing_id"] == listing.internal_listing_id
    assert out["data"]["mapping_status"] == "active"
    assert store.rows and store.rows[-1]["internal_listing_id"] == listing.internal_listing_id
    assert store.rows[-1]["xianyu_product_id"] == "xp-200"


@pytest.mark.asyncio
async def test_wave_d_create_listing_publish_result_uses_same_generated_internal_listing_id(monkeypatch) -> None:
    """Test that create_listing uses the same internal_listing_id as generated.

    This test mocks compliance checks to avoid test pollution from rate limiting
    set by other tests in the suite.
    """
    store = _StubMappingStore()

    # Create a proper mock controller that won't cause issues
    class MockController:
        pass

    svc = ListingService(controller=MockController(), config={}, mapping_store=store)
    listing = Listing(title="t", description="d", price=1.0, internal_listing_id=None)

    # Mock _execute_publish to avoid browser operations
    async def _fake_execute_publish(_listing):
        return "xp-300", "https://www.goofish.com/item/xp-300"

    monkeypatch.setattr(svc, "_execute_publish", _fake_execute_publish)

    # Mock compliance checks to avoid rate limiting and content checks from other tests
    # evaluate_content is a regular method (not async)
    def _fake_evaluate_content(*texts):
        return {"allowed": True, "blocked": False, "warn": False, "hits": [], "message": ""}

    # evaluate_publish_rate is an async method
    async def _fake_evaluate_publish_rate(key="publish:global"):
        return {"allowed": True, "blocked": False, "warn": False, "message": ""}

    monkeypatch.setattr(svc.compliance, "evaluate_content", _fake_evaluate_content)
    monkeypatch.setattr(svc.compliance, "evaluate_publish_rate", _fake_evaluate_publish_rate)

    result = await svc.create_listing(listing)

    assert result.success is True
    assert listing.internal_listing_id
    assert result.internal_listing_id == listing.internal_listing_id
    assert result.data["internal_listing_id"] == listing.internal_listing_id
    assert store.rows and store.rows[-1]["internal_listing_id"] == listing.internal_listing_id
    assert store.rows[-1]["xianyu_product_id"] == "xp-300"

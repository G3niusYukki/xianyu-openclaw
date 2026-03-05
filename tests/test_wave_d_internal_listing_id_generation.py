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
    store = _StubMappingStore()
    svc = ListingService(controller=object(), config={}, mapping_store=store)
    listing = Listing(title="t", description="d", price=1.0, internal_listing_id=None)

    async def _fake_publish(_listing):
        return "xp-300", "https://www.goofish.com/item/xp-300"

    monkeypatch.setattr(svc, "_execute_publish", _fake_publish)
    result = await svc.create_listing(listing)

    assert result.success is True
    assert listing.internal_listing_id
    assert result.internal_listing_id == listing.internal_listing_id
    assert result.data["internal_listing_id"] == listing.internal_listing_id
    assert store.rows and store.rows[-1]["internal_listing_id"] == listing.internal_listing_id
    assert store.rows[-1]["xianyu_product_id"] == "xp-300"

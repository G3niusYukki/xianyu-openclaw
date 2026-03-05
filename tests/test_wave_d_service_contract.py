from __future__ import annotations

import pytest

from src.integrations.xianguanjia.models import XianGuanJiaResponse
from src.integrations.xianguanjia.open_platform_client import OpenPlatformClient
from src.modules.listing.models import Listing, PublishResult
from src.modules.listing.service import ListingService


def test_wave_d_internal_listing_id_in_listing_and_publish_result() -> None:
    listing = Listing(title="t", description="d", price=1.0, internal_listing_id="in-100")
    payload = listing.to_dict()
    assert payload["internal_listing_id"] == "in-100"

    result = PublishResult(success=True, product_id="xp-100", internal_listing_id="in-100")
    assert result.internal_listing_id == "in-100"
    assert result.data["internal_listing_id"] == "in-100"


def test_wave_d_publish_result_does_not_infer_mapping_status_from_internal_id() -> None:
    with_id = PublishResult(success=True, product_id="xp-1", internal_listing_id="in-1")
    without_id = PublishResult(success=True, product_id="xp-2", internal_listing_id=None)

    assert with_id.data["mapping_status"] == "inactive"
    assert without_id.data["mapping_status"] == "inactive"


@pytest.mark.parametrize(
    ("store_status", "contract_status"),
    [
        ("unmapped", "inactive"),
        ("mapped", "active"),
        ("syncing", "pending_sync"),
        ("failed", "sync_failed"),
        ("disabled", "inactive"),
    ],
)
def test_wave_d_mapping_status_conversion_store_to_service_contract(store_status: str, contract_status: str) -> None:
    assert ListingService._to_contract_mapping_status(store_status) == contract_status


@pytest.mark.asyncio
async def test_wave_d_unified_execute_contract_shape_and_fields() -> None:
    class _OpenClient:
        def publish_product(self, payload: dict):
            return XianGuanJiaResponse.success(data={"product_id": payload.get("product_id") or "xp-1"})

        def create_product(self, payload: dict):
            return XianGuanJiaResponse.success(data={"product_id": "xp-1"})

        def edit_product(self, payload: dict):
            return XianGuanJiaResponse.success(data={"product_id": "xp-1"})

        def edit_stock(self, payload: dict):
            return XianGuanJiaResponse.success(data={"product_id": "xp-1"})

        def unpublish_product(self, payload: dict):
            return XianGuanJiaResponse.success(data={"product_id": "xp-1"})

    svc = ListingService(controller=None, config={})
    listing = Listing(title="t", description="d", price=1.0, internal_listing_id="in-1")

    out = await svc.execute_product_action(
        "publish",
        payload={"product_id": "xp-1"},
        listing=listing,
        api_client=_OpenClient(),
    )

    for key in ("ok", "action", "code", "message", "data", "errors", "ts"):
        assert key in out
    assert out["ok"] is True
    assert out["action"] == "publish"
    assert out["data"]["xianyu_product_id"] == "xp-1"
    assert out["data"]["internal_listing_id"] == "in-1"
    assert out["data"]["mapping_status"] == "inactive"
    assert out["data"]["channel"] == "api_primary"
    assert out["data"]["code"] == "OK"
    assert out["data"]["message"] == "ok_without_mapping"


@pytest.mark.asyncio
async def test_wave_d_create_execute_real_store_persists_mapping_and_contract_reads_status(temp_dir) -> None:
    class _OpenClient:
        def publish_product(self, payload: dict):
            return XianGuanJiaResponse.success(data={"product_id": payload.get("product_id") or "xp-real-1"})

        def create_product(self, payload: dict):
            return XianGuanJiaResponse.success(data={"product_id": "xp-real-1"})

        def edit_product(self, payload: dict):
            return XianGuanJiaResponse.success(data={"product_id": "xp-real-1"})

        def edit_stock(self, payload: dict):
            return XianGuanJiaResponse.success(data={"product_id": "xp-real-1"})

        def unpublish_product(self, payload: dict):
            return XianGuanJiaResponse.success(data={"product_id": "xp-real-1"})

    svc = ListingService(controller=None, config={"db_path": str(temp_dir / "wave_d_listing_contract_real.db")})
    listing = Listing(title="t", description="d", price=1.0, internal_listing_id=None)

    created = await svc.execute_product_action("create", payload={}, listing=listing, api_client=_OpenClient())
    assert created["ok"] is True
    assert listing.internal_listing_id
    assert created["data"]["internal_listing_id"] == listing.internal_listing_id
    assert created["data"]["mapping_status"] == "active"

    mapping = svc.mapping_store.get_listing_product_mapping(xianyu_product_id="xp-real-1")
    assert mapping is not None
    assert mapping["internal_listing_id"] == listing.internal_listing_id
    assert mapping["mapping_status"] == "mapped"

    published = await svc.execute_product_action(
        "publish",
        payload={"product_id": "xp-real-1"},
        listing=listing,
        api_client=_OpenClient(),
    )
    assert published["ok"] is True
    assert published["data"]["mapping_status"] == "active"
    assert published["data"]["message"] == "ok"


def test_wave_d_open_platform_client_protocol_only_no_business_router() -> None:
    assert not hasattr(OpenPlatformClient, "execute_product_action")

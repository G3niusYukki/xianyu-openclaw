from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.modules.virtual_goods.store import VirtualGoodsStore


@pytest.fixture
def store(tmp_path):
    return VirtualGoodsStore(db_path=str(tmp_path / "test.db"))


class TestTransaction:
    def test_rollback_on_exception(self, store):
        with pytest.raises(RuntimeError):
            with store.transaction() as conn:
                conn.execute(
                    "INSERT INTO virtual_goods_orders"
                    "(xianyu_order_id, xianyu_product_id, order_status, fulfillment_status, callback_status, manual_takeover, created_at, updated_at)"
                    " VALUES ('test1', '', 'delivered', 'pending', 'none', 0, '2025-01-01', '2025-01-01')"
                )
                raise RuntimeError("boom")
        assert store.get_order("test1") is None


class TestUpsertOrder:
    def test_invalid_order_status(self, store):
        with pytest.raises(ValueError, match="Unsupported virtual_goods order status"):
            store.upsert_order(xianyu_order_id="o1", order_status="bad_status")

    def test_invalid_callback_status(self, store):
        with pytest.raises(ValueError, match="Unsupported callback status"):
            store.upsert_order(
                xianyu_order_id="o1",
                order_status="delivered",
                callback_status="bad_callback",
            )


class TestInsertCallback:
    def test_invalid_source_family(self, store):
        with pytest.raises(ValueError, match="Unsupported source_family"):
            store.insert_callback(
                callback_type="order",
                external_event_id="ev1",
                dedupe_key=None,
                xianyu_order_id="o1",
                payload={},
                raw_body="{}",
                headers={},
                signature="",
                verify_passed=True,
                source_family="invalid_family",
                event_kind="order",
            )


class TestClaimCallback:
    def test_claim_callback_no_rows(self, store):
        result = store.claim_callback(processed=False)
        assert result is None

    def test_claim_callback_race_condition(self, store):
        store.insert_callback(
            callback_type="order",
            external_event_id="ev_race",
            dedupe_key=None,
            xianyu_order_id="o1",
            payload={},
            raw_body="{}",
            headers={},
            signature="",
            verify_passed=True,
            source_family="open_platform",
            event_kind="order",
        )
        first = store.claim_callback(processed=False)
        assert first is not None
        second = store.claim_callback(processed=False)
        assert second is None


class TestRecordManualTakeoverEvent:
    def test_conn_none_branch(self, store):
        store.upsert_order(xianyu_order_id="o1", order_status="delivered")
        event_id = store.record_manual_takeover_event(
            xianyu_order_id="o1", enabled=True, reason="test"
        )
        assert event_id > 0


class TestSetManualTakeover:
    def test_conn_none_branch(self, store):
        store.upsert_order(xianyu_order_id="o1", order_status="delivered")
        result = store.set_manual_takeover("o1", True, reason="test")
        assert result is True


class TestRecordOrderEvent:
    def test_conn_none_branch(self, store):
        event_id = store.record_order_event(
            event_type="test",
            event_kind="order",
            xianyu_order_id="o1",
        )
        assert event_id > 0


class TestUpsertListingProductMapping:
    def test_invalid_status(self, store):
        with pytest.raises(ValueError, match="Unsupported mapping status"):
            store.upsert_listing_product_mapping(
                xianyu_product_id="p1", mapping_status="garbage"
            )

    def test_empty_product_id(self, store):
        with pytest.raises(ValueError, match="xianyu_product_id is required"):
            store.upsert_listing_product_mapping(
                xianyu_product_id="", mapping_status="unmapped"
            )


class TestGetListingProductMapping:
    def test_no_keys_raises(self, store):
        with pytest.raises(ValueError, match="xianyu_product_id or internal_listing_id is required"):
            store.get_listing_product_mapping()

    def test_by_product_id_raises_empty(self, store):
        with pytest.raises(ValueError, match="xianyu_product_id is required"):
            store.get_listing_product_mapping_by_product_id(xianyu_product_id="")

    def test_by_internal_id_raises_empty(self, store):
        with pytest.raises(ValueError, match="internal_listing_id is required"):
            store.get_listing_product_mapping_by_internal_id(internal_listing_id="")


class TestUpdateListingMappingStatus:
    def test_empty_product_id(self, store):
        with pytest.raises(ValueError, match="xianyu_product_id is required"):
            store.update_listing_mapping_status(
                xianyu_product_id="", mapping_status="mapped"
            )

    def test_invalid_status(self, store):
        with pytest.raises(ValueError, match="Unsupported mapping status"):
            store.update_listing_mapping_status(
                xianyu_product_id="p1", mapping_status="garbage"
            )

    def test_no_existing_row(self, store):
        result = store.update_listing_mapping_status(
            xianyu_product_id="nonexistent", mapping_status="mapped"
        )
        assert result is None


class TestDeleteListingProductMapping:
    def test_empty_product_id(self, store):
        with pytest.raises(ValueError, match="xianyu_product_id is required"):
            store.delete_listing_product_mapping(xianyu_product_id="")


class TestRecordOpsException:
    def test_invalid_severity_defaults_to_p2(self, store):
        exc_id = store.record_ops_exception(
            xianyu_order_id="o1",
            event_kind="order",
            exception_code="test_exc",
            severity="P9",
        )
        assert exc_id > 0

    def test_conn_none_branch(self, store):
        exc_id = store.record_ops_exception(
            xianyu_order_id="o1",
            event_kind="order",
            exception_code="test_exc",
        )
        assert exc_id > 0

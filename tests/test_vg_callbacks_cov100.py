from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.modules.virtual_goods.callbacks import VirtualGoodsCallbackService


def _make_store():
    store = MagicMock()
    store.insert_callback.return_value = (1, True)
    store.get_callback.return_value = {
        "id": 1,
        "verify_passed": 1,
        "processed": 0,
        "verify_error": "",
        "payload_json": "{}",
        "event_kind": "order",
    }
    store.claim_callback_lease.return_value = True
    store.get_order.return_value = {}
    return store


def _make_service(store=None, config=None):
    return VirtualGoodsCallbackService(store=store or _make_store(), config=config)


class TestNormalizeSourceFamily:
    def test_open_platform_aliases(self):
        for alias in ("open", "platform", "openplatform"):
            assert VirtualGoodsCallbackService._normalize_source_family(alias) == "open_platform"

    def test_virtual_supply_aliases(self):
        for alias in ("supply", "virtual", "virtualsupply"):
            assert VirtualGoodsCallbackService._normalize_source_family(alias) == "virtual_supply"

    def test_unknown_family(self):
        assert VirtualGoodsCallbackService._normalize_source_family("garbage") == ""

    def test_known_families(self):
        assert VirtualGoodsCallbackService._normalize_source_family("open_platform") == "open_platform"
        assert VirtualGoodsCallbackService._normalize_source_family("virtual_supply") == "virtual_supply"


class TestResolveTargetStatus:
    def _svc(self):
        return _make_service()

    def test_refund_event_refunded(self):
        svc = self._svc()
        assert svc._resolve_target_status("refund", {"status": "refunded"}) == "refunded"

    def test_refund_event_pending(self):
        svc = self._svc()
        assert svc._resolve_target_status("refund", {"status": "refund_pending"}) == "refund_pending"

    def test_refund_event_fallback(self):
        svc = self._svc()
        assert svc._resolve_target_status("refund", {"status": "something"}) == "refund_pending"

    def test_delivery_fail(self):
        svc = self._svc()
        assert svc._resolve_target_status("delivery", {"status": "failed"}) == "delivery_failed"

    def test_delivery_pending(self):
        svc = self._svc()
        assert svc._resolve_target_status("voucher", {"status": "pending"}) == "paid_waiting_delivery"

    def test_delivery_fallback_delivered(self):
        svc = self._svc()
        assert svc._resolve_target_status("code", {"status": ""}) == "delivered"

    def test_close_event(self):
        svc = self._svc()
        assert svc._resolve_target_status("close", {"status": ""}) == "closed"

    def test_cancel_event(self):
        svc = self._svc()
        assert svc._resolve_target_status("cancel", {"status": ""}) == "closed"

    def test_pay_event_with_valid_status(self):
        svc = self._svc()
        assert svc._resolve_target_status("pay", {"status": "delivered"}) == "delivered"

    def test_pay_event_fallback(self):
        svc = self._svc()
        with patch.object(svc, "_status_from_text", return_value="some_unknown"):
            assert svc._resolve_target_status("order", {"status": "anything"}) == "paid_waiting_delivery"

    def test_unknown_event_fallback(self):
        svc = self._svc()
        assert svc._resolve_target_status("unknown", {"status": "delivered"}) == "delivered"

    def test_delivery_with_raw_status_normalized(self):
        svc = self._svc()
        assert svc._resolve_target_status("delivery", {"status": "delivered"}) == "delivered"


class TestResolveFulfillmentStatus:
    def test_delivery_failed(self):
        assert VirtualGoodsCallbackService._resolve_fulfillment_status("delivery_failed", "") == "failed"

    def test_refunded(self):
        assert VirtualGoodsCallbackService._resolve_fulfillment_status("refunded", "") == "fulfilled"

    def test_previous_fulfilled(self):
        assert VirtualGoodsCallbackService._resolve_fulfillment_status("paid_waiting_delivery", "fulfilled") == "fulfilled"

    def test_previous_failed(self):
        assert VirtualGoodsCallbackService._resolve_fulfillment_status("paid_waiting_delivery", "failed") == "failed"

    def test_previous_manual(self):
        assert VirtualGoodsCallbackService._resolve_fulfillment_status("paid_waiting_delivery", "manual") == "manual"


class TestVerify:
    def test_missing_signature(self):
        svc = _make_service(config={"xianguanjia": {"app_key": "k", "app_secret": "s"}})
        ok, sign, err = svc._verify(source_family="open_platform", raw_body="", headers={}, query_params={})
        assert not ok
        assert err == "missing_signature_or_timestamp"

    @patch("src.modules.virtual_goods.callbacks.verify_open_platform_callback_signature", return_value=False)
    def test_missing_open_platform_secret(self, _mock_verify):
        svc = _make_service(config={})
        ok, sign, err = svc._verify(
            source_family="open_platform",
            raw_body="body",
            headers={"x-sign": "abc", "x-timestamp": "123"},
            query_params={},
        )
        assert not ok
        assert err == "missing_open_platform_secret"

    @patch("src.modules.virtual_goods.callbacks.verify_virtual_supply_callback_signature", return_value=False)
    def test_missing_virtual_supply_secret(self, _mock_verify):
        svc = _make_service(config={"xianguanjia": {"app_secret": "s"}})
        ok, sign, err = svc._verify(
            source_family="virtual_supply",
            raw_body="body",
            headers={"x-sign": "abc", "x-timestamp": "123"},
            query_params={},
        )
        assert not ok
        assert err == "missing_virtual_supply_secret"


class TestProcess:
    def test_non_dict_payload(self):
        store = _make_store()
        svc = _make_service(store=store)
        result = svc.process(
            source_family="open_platform",
            event_kind="order",
            raw_body='"just a string"',
            headers={"x-sign": "s", "x-timestamp": "1"},
        )
        assert "callback_id" in result

    def test_invalid_source_family(self):
        store = _make_store()
        svc = _make_service(store=store)
        result = svc.process(
            source_family="garbage",
            event_kind="order",
            raw_body='{"order_id": "123"}',
            headers={},
        )
        assert result["ok"] is False
        assert result["error"] == "invalid_source_family"

    def test_invalid_source_family_not_inserted(self):
        store = _make_store()
        store.insert_callback.return_value = (1, False)
        svc = _make_service(store=store)
        result = svc.process(
            source_family="garbage",
            event_kind="order",
            raw_body='{"order_id": "123"}',
            headers={},
        )
        assert result["duplicate"] is True

    @patch("src.modules.virtual_goods.callbacks.verify_open_platform_callback_signature", return_value=True)
    def test_claimed_payload_json_decode_error(self, _mock):
        store = _make_store()
        store.get_callback.return_value = {
            "id": 1,
            "verify_passed": 1,
            "processed": 0,
            "verify_error": "",
            "payload_json": "not valid json{{{",
            "event_kind": "order",
        }
        svc = _make_service(
            store=store,
            config={"xianguanjia": {"app_key": "k", "app_secret": "s"}},
        )
        result = svc.process(
            source_family="open_platform",
            event_kind="order",
            raw_body='{"xianyu_order_id": "o1"}',
            headers={"x-sign": "abc", "x-timestamp": "123"},
        )
        assert result["error"] == "missing_order_id"

    @patch("src.modules.virtual_goods.callbacks.verify_open_platform_callback_signature", return_value=True)
    def test_claimed_payload_not_dict(self, _mock):
        store = _make_store()
        store.get_callback.return_value = {
            "id": 1,
            "verify_passed": 1,
            "processed": 0,
            "verify_error": "",
            "payload_json": "[1,2,3]",
            "event_kind": "order",
        }
        svc = _make_service(
            store=store,
            config={"xianguanjia": {"app_key": "k", "app_secret": "s"}},
        )
        result = svc.process(
            source_family="open_platform",
            event_kind="order",
            raw_body='{"xianyu_order_id": "o1"}',
            headers={"x-sign": "abc", "x-timestamp": "123"},
        )
        assert result["error"] == "missing_order_id"

    @patch("src.modules.virtual_goods.callbacks.verify_open_platform_callback_signature", return_value=True)
    def test_claimed_verify_failed(self, _mock):
        store = _make_store()
        call_count = [0]
        def side_effect(cb_id):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    "id": 1,
                    "verify_passed": 1,
                    "processed": 0,
                    "verify_error": "",
                    "payload_json": '{"xianyu_order_id": "o1"}',
                    "event_kind": "order",
                }
            return {
                "id": 1,
                "verify_passed": 0,
                "processed": 0,
                "verify_error": "invalid_signature",
                "payload_json": '{"xianyu_order_id": "o1"}',
                "event_kind": "order",
            }
        store.get_callback.side_effect = side_effect
        svc = _make_service(
            store=store,
            config={"xianguanjia": {"app_key": "k", "app_secret": "s"}},
        )
        result = svc.process(
            source_family="open_platform",
            event_kind="order",
            raw_body='{"xianyu_order_id": "o1"}',
            headers={"x-sign": "abc", "x-timestamp": "123"},
        )
        assert result["error"] == "invalid_signature"

    @patch("src.modules.virtual_goods.callbacks.verify_open_platform_callback_signature", return_value=True)
    def test_claimed_missing_order_id(self, _mock):
        store = _make_store()
        store.get_callback.return_value = {
            "id": 1,
            "verify_passed": 1,
            "processed": 0,
            "verify_error": "",
            "payload_json": '{}',
            "event_kind": "order",
        }
        svc = _make_service(
            store=store,
            config={"xianguanjia": {"app_key": "k", "app_secret": "s"}},
        )
        result = svc.process(
            source_family="open_platform",
            event_kind="order",
            raw_body='{"xianyu_order_id": "o1"}',
            headers={"x-sign": "abc", "x-timestamp": "123"},
        )
        assert result["error"] == "missing_order_id"

    @patch("src.modules.virtual_goods.callbacks.verify_open_platform_callback_signature", return_value=True)
    def test_process_exception_releases_lease(self, _mock):
        store = _make_store()
        store.get_callback.return_value = {
            "id": 1,
            "verify_passed": 1,
            "processed": 0,
            "verify_error": "",
            "payload_json": '{"xianyu_order_id": "o1", "status": "delivered"}',
            "event_kind": "order",
        }
        store.get_order.side_effect = RuntimeError("boom")
        svc = _make_service(
            store=store,
            config={"xianguanjia": {"app_key": "k", "app_secret": "s"}},
        )
        with pytest.raises(RuntimeError, match="boom"):
            svc.process(
                source_family="open_platform",
                event_kind="order",
                raw_body='{"xianyu_order_id": "o1", "status": "delivered"}',
                headers={"x-sign": "abc", "x-timestamp": "123"},
            )
        store.mark_callback_processed.assert_called()

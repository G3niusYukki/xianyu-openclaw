from __future__ import annotations

import hashlib
import json
from typing import Any

from src.integrations.xianguanjia.signing import (
    verify_open_platform_callback_signature,
    verify_virtual_supply_callback_signature,
)

from .models import normalize_order_status
from .store import VirtualGoodsStore


class VirtualGoodsCallbackService:
    def __init__(self, store: VirtualGoodsStore, config: dict[str, Any] | None = None) -> None:
        self.store = store
        self.config = config or {}

    @staticmethod
    def _pick(payload: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = str(payload.get(key) or "").strip()
            if value:
                return value
        return ""

    @staticmethod
    def _dedupe_key(callback_type: str, order_id: str, raw_body: str) -> str:
        return hashlib.md5(f"{callback_type}|{order_id}|{raw_body}".encode()).hexdigest()

    @staticmethod
    def _normalize_source_family(source_family: str) -> str:
        family = str(source_family or "").strip().lower()
        if family in {"open_platform", "virtual_supply"}:
            return family
        if family in {"open", "platform", "openplatform"}:
            return "open_platform"
        if family in {"supply", "virtual", "virtualsupply"}:
            return "virtual_supply"
        return ""

    @staticmethod
    def _normalize_event_kind(event_kind: str) -> str:
        ev = str(event_kind or "").strip().lower()
        return ev or "unknown"

    @staticmethod
    def _status_from_text(raw_status: str) -> str:
        return normalize_order_status(raw_status)

    def _resolve_target_status(self, event_kind: str, payload: dict[str, Any]) -> str:
        raw_status = str(
            payload.get("order_status")
            or payload.get("status")
            or payload.get("tradeStatus")
            or payload.get("refund_status")
            or payload.get("refundStatus")
            or payload.get("voucher_status")
            or payload.get("code_status")
            or ""
        )
        text = raw_status.lower()
        event_kind = self._normalize_event_kind(event_kind)

        if "refund" in event_kind:
            if any(k in text for k in ("refunded", "refund_success", "已退款", "退款成功")):
                return "refunded"
            if any(k in text for k in ("refund_pending", "退款中", "售后中", "processing")):
                return "refund_pending"
            return "refund_pending"

        if any(k in event_kind for k in ("coupon", "voucher", "code", "delivery", "deliver", "ship")):
            if any(k in text for k in ("fail", "failed", "发码失败", "delivery_failed")):
                return "delivery_failed"
            if any(k in text for k in ("pending", "processing", "待发码", "发码中")):
                return "paid_waiting_delivery"
            if raw_status.strip():
                normalized = self._status_from_text(raw_status)
                if normalized in {"paid_waiting_delivery", "delivery_failed", "delivered"}:
                    return normalized
            return "delivered"

        if any(k in event_kind for k in ("close", "cancel")):
            return "closed"

        if any(k in event_kind for k in ("pay", "order", "create")):
            normalized = self._status_from_text(raw_status)
            if normalized in {
                "pending_payment",
                "paid_waiting_delivery",
                "delivered",
                "delivery_failed",
                "refund_pending",
                "refunded",
                "closed",
            }:
                return normalized
            return "paid_waiting_delivery"

        return self._status_from_text(raw_status)

    @staticmethod
    def _resolve_fulfillment_status(target_order_status: str, previous: str) -> str:
        if target_order_status == "delivered":
            return "fulfilled"
        if target_order_status == "delivery_failed":
            return "failed"
        if target_order_status == "refunded":
            return "fulfilled"
        if target_order_status == "refund_pending":
            return "delivering"
        if previous in {"fulfilled", "failed", "manual"}:
            return previous
        return "pending"

    @staticmethod
    def _is_regression_blocked(prev_status: str, next_status: str, event_kind: str) -> bool:
        prev = str(prev_status or "").lower()
        nxt = str(next_status or "").lower()
        ev = str(event_kind or "").lower()

        if prev == "delivered" and nxt == "paid_waiting_delivery":
            return True
        if prev == "refunded" and nxt == "delivered":
            return True
        if (
            prev == "closed"
            and nxt in {"paid_waiting_delivery", "delivered"}
            and any(k in ev for k in ("order", "coupon", "code"))
        ):
            return True
        return False

    def _verify(
        self,
        *,
        source_family: str,
        raw_body: str,
        headers: dict[str, Any],
        query_params: dict[str, Any],
    ) -> tuple[bool, str, str]:
        sign = (
            str(
                headers.get("x-sign")
                or headers.get("sign")
                or query_params.get("x-sign")
                or query_params.get("sign")
                or ""
            )
            .strip()
            .lower()
        )
        ts = str(
            headers.get("x-timestamp")
            or headers.get("timestamp")
            or query_params.get("x-timestamp")
            or query_params.get("timestamp")
            or ""
        ).strip()
        if not sign or not ts:
            return False, sign, "missing_signature_or_timestamp"

        xcfg = self.config.get("xianguanjia", {}) if isinstance(self.config, dict) else {}
        app_key = str(xcfg.get("app_key") or "")
        app_secret = str(xcfg.get("app_secret") or "")
        if source_family == "open_platform":
            if not app_key or not app_secret:
                return False, sign, "missing_open_platform_secret"
            ok = verify_open_platform_callback_signature(
                app_key=app_key,
                app_secret=app_secret,
                timestamp=ts,
                sign=sign,
                body=raw_body,
            )
            return ok, sign, "" if ok else "invalid_signature"

        app_id = str(query_params.get("app_id") or xcfg.get("vs_app_id") or "")
        mch_id = str(query_params.get("mch_id") or xcfg.get("vs_mch_id") or "")
        mch_secret = str(xcfg.get("vs_mch_secret") or "")
        if not app_id or not app_secret or not mch_id or not mch_secret:
            return False, sign, "missing_virtual_supply_secret"
        ok = verify_virtual_supply_callback_signature(
            app_id=app_id,
            app_secret=app_secret,
            mch_id=mch_id,
            mch_secret=mch_secret,
            timestamp=ts,
            sign=sign,
            body=raw_body,
        )
        return ok, sign, "" if ok else "invalid_signature"

    def _release_callback_lease(self, callback_id: int, *, last_error: str | None = None) -> None:
        self.store.mark_callback_processed(int(callback_id), processed=False, last_process_error=last_error)

    def process(
        self,
        *,
        source_family: str,
        event_kind: str,
        raw_body: str,
        headers: dict[str, Any],
        query_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query_params = {k.lower(): v for k, v in dict(query_params or {}).items()}
        payload = json.loads(raw_body or "{}") if raw_body else {}
        if not isinstance(payload, dict):
            payload = {}

        source_family = self._normalize_source_family(source_family)
        event_kind = self._normalize_event_kind(event_kind)
        callback_type = event_kind

        order_id = self._pick(payload, "xianyu_order_id", "order_id", "orderNo", "order_no")
        external_event_id = self._pick(payload, "external_event_id", "event_id", "eventId") or None
        dedupe_key = None if external_event_id else self._dedupe_key(callback_type, order_id, raw_body)

        audit_headers = dict(headers)
        audit_headers["query_params"] = query_params

        if not source_family:
            callback_id, inserted = self.store.insert_callback(
                callback_type=callback_type,
                external_event_id=external_event_id,
                dedupe_key=dedupe_key,
                xianyu_order_id=order_id or None,
                payload=payload,
                raw_body=raw_body,
                headers=audit_headers,
                signature="",
                verify_passed=False,
                verify_error="invalid_source_family",
                source_family="unknown",
                event_kind=event_kind,
            )
            return {
                "ok": False,
                "duplicate": not inserted,
                "processed": False,
                "processed_state": "failed",
                "callback_id": callback_id,
                "error": "invalid_source_family",
            }

        verify_passed, signature, verify_error = self._verify(
            source_family=source_family,
            raw_body=raw_body,
            headers=headers,
            query_params=query_params,
        )

        callback_id, inserted = self.store.insert_callback(
            callback_type=callback_type,
            external_event_id=external_event_id,
            dedupe_key=dedupe_key,
            xianyu_order_id=order_id or None,
            payload=payload,
            raw_body=raw_body,
            headers=audit_headers,
            signature=signature,
            verify_passed=verify_passed,
            verify_error=verify_error,
            source_family=source_family,
            event_kind=event_kind,
        )

        existing_callback = self.store.get_callback(callback_id) or {}
        if not inserted and int(existing_callback.get("processed") or 0) == 1:
            return {
                "ok": True,
                "duplicate": True,
                "processed": False,
                "processed_state": "processed",
                "callback_id": callback_id,
            }

        if int(existing_callback.get("verify_passed") or 0) != 1:
            return {
                "ok": False,
                "duplicate": not inserted,
                "processed": False,
                "processed_state": "failed",
                "callback_id": callback_id,
                "error": str(existing_callback.get("verify_error") or "invalid_signature"),
            }

        claimed_ok = self.store.claim_callback_lease(callback_id=callback_id, processed=False)
        if not claimed_ok:
            return {
                "ok": True,
                "duplicate": not inserted,
                "processed": False,
                "processed_state": "processing",
                "callback_id": callback_id,
                "error": "lease_not_acquired",
            }

        claimed = self.store.get_callback(callback_id) or {}
        claimed_id = int(claimed.get("id") or callback_id)
        claimed_payload = claimed.get("payload_json")
        if isinstance(claimed_payload, str):
            try:
                claimed_payload = json.loads(claimed_payload)
            except json.JSONDecodeError:
                claimed_payload = {}
        if not isinstance(claimed_payload, dict):
            claimed_payload = {}

        claimed_event_kind = str(claimed.get("event_kind") or event_kind)
        claimed_order_id = self._pick(claimed_payload, "xianyu_order_id", "order_id", "orderNo", "order_no")

        try:
            if int(claimed.get("verify_passed") or 0) != 1:
                self._release_callback_lease(claimed_id, last_error="verify_failed")
                return {
                    "ok": False,
                    "duplicate": not inserted,
                    "processed": False,
                    "processed_state": "failed",
                    "callback_id": claimed_id,
                    "error": str(claimed.get("verify_error") or "invalid_signature"),
                }

            if not claimed_order_id:
                self._release_callback_lease(claimed_id, last_error="missing_order_id")
                return {
                    "ok": False,
                    "duplicate": not inserted,
                    "processed": False,
                    "processed_state": "failed",
                    "callback_id": claimed_id,
                    "error": "missing_order_id",
                }

            next_status = self._resolve_target_status(claimed_event_kind, claimed_payload)
            existing = self.store.get_order(claimed_order_id) or {}

            if int(existing.get("manual_takeover") or 0) == 1:
                self._release_callback_lease(claimed_id, last_error="manual_takeover")
                return {
                    "ok": True,
                    "duplicate": not inserted,
                    "processed": False,
                    "processed_state": "received",
                    "callback_id": claimed_id,
                    "status": str(existing.get("order_status") or ""),
                    "blocked": "manual_takeover",
                }

            if self._is_regression_blocked(str(existing.get("order_status") or ""), next_status, claimed_event_kind):
                self._release_callback_lease(claimed_id, last_error="status_regression")
                return {
                    "ok": True,
                    "duplicate": not inserted,
                    "processed": False,
                    "processed_state": "received",
                    "callback_id": claimed_id,
                    "status": str(existing.get("order_status") or ""),
                    "blocked": "status_regression",
                }

            fulfillment_status = self._resolve_fulfillment_status(
                next_status, str(existing.get("fulfillment_status") or "")
            )

            self.store.upsert_order(
                xianyu_order_id=claimed_order_id,
                xianyu_product_id=self._pick(claimed_payload, "xianyu_product_id", "product_id", "item_id"),
                supply_order_no=self._pick(claimed_payload, "supply_order_no", "supplier_order_no") or None,
                session_id=self._pick(claimed_payload, "session_id", "chat_id"),
                order_status=next_status,
                callback_status="processed",
                fulfillment_status=fulfillment_status,
            )
            self.store.mark_callback_processed(claimed_id)
            return {
                "ok": True,
                "duplicate": not inserted,
                "processed": True,
                "processed_state": "processed",
                "callback_id": claimed_id,
                "status": next_status,
                "auto_reissue_code": False,
                "auto_replenish_order": False,
            }
        except Exception as exc:
            self._release_callback_lease(claimed_id, last_error=str(exc))
            raise

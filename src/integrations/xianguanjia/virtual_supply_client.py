"""闲管家虚拟货源 Client 骨架。

已废弃 — 用户业务场景不需要虚拟货源接口（/goofish/* 路径）。
自动发货由闲管家平台完成，不需要自建供货服务。
保留仅为代码完整性，不应在业务流程中调用。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .errors import is_retryable_error, map_error
from .models import XianGuanJiaResponse
from .signing import sign_virtual_supply_request


@dataclass
class VirtualSupplyClient:
    base_url: str
    app_id: str
    app_secret: str
    mch_id: str
    mch_secret: str
    timeout: float = 10.0

    def _post(self, path: str, payload: dict[str, Any]) -> XianGuanJiaResponse:
        url = f"{self.base_url.rstrip('/')}{path}"
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        timestamp = str(int(time.time() * 1000))
        sign = sign_virtual_supply_request(
            app_id=self.app_id,
            app_secret=self.app_secret,
            mch_id=self.mch_id,
            mch_secret=self.mch_secret,
            timestamp=timestamp,
            body=body,
        )
        params = {
            "mch_id": self.mch_id,
            "timestamp": timestamp,
            "sign": sign,
        }
        try:
            resp = httpx.post(
                url,
                params=params,
                content=body.encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )
            raw = resp.json()
            code = raw.get("code")
            if code == 0:
                return XianGuanJiaResponse.success(
                    data=raw.get("data"),
                    request_id=raw.get("request_id"),
                    http_status=resp.status_code,
                    raw_payload=raw,
                )
            normalized = map_error(
                http_status=resp.status_code,
                error_code=code,
                request_id=raw.get("request_id"),
                raw_payload=raw,
                message=raw.get("msg") or "virtual supply business error",
            )
            return XianGuanJiaResponse.failure(
                error_code=str(code) if code is not None else None,
                error_message=str(normalized),
                retryable=is_retryable_error(normalized),
                request_id=raw.get("request_id"),
                http_status=resp.status_code,
                raw_payload=raw,
            )
        except Exception as exc:
            normalized = map_error(exc=exc, message=str(exc))
            return XianGuanJiaResponse.failure(
                error_code=getattr(normalized, "error_code", None),
                error_message=str(normalized),
                retryable=is_retryable_error(normalized),
                request_id=getattr(normalized, "request_id", None),
                http_status=getattr(normalized, "http_status", None),
                raw_payload=getattr(normalized, "raw_payload", None),
            )

    def create_card_order(self, payload: dict[str, Any]) -> XianGuanJiaResponse:
        return self._post("/goofish/order/purchase/create", payload)

    def create_coupon_order(self, payload: dict[str, Any]) -> XianGuanJiaResponse:
        return self._post("/goofish/order/ticket/create", payload)

    def create_recharge_order(self, payload: dict[str, Any]) -> XianGuanJiaResponse:
        return self._post("/goofish/order/recharge/create", payload)

"""闲管家开放平台 Client（支持自研 + 商务对接两种模式）。

自研模式签名: md5("appKey,bodyMd5,timestamp,appSecret")
商务对接签名: md5("appKey,bodyMd5,timestamp,sellerId,appSecret")
Query参数: appid, timestamp, sign, (商务对接模式额外传 seller_id)
时间戳: 秒级 int(time.time())
Body序列化: separators=(",",":") 压缩JSON，不排序 key

参考文档: docs/xianguanjiajieruapi.md
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .errors import is_retryable_error, map_error
from .models import XianGuanJiaResponse
from .signing import sign_open_platform_request, sign_business_request


@dataclass
class OpenPlatformClient:
    base_url: str
    app_key: str
    app_secret: str
    timeout: float = 10.0
    mode: str = "self_developed"
    seller_id: str = ""

    def _post(self, path: str, payload: dict[str, Any]) -> XianGuanJiaResponse:
        url = f"{self.base_url.rstrip('/')}{path}"
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        timestamp = str(int(time.time()))
        if self.mode == "business" and self.seller_id:
            sign = sign_business_request(
                app_key=self.app_key,
                app_secret=self.app_secret,
                seller_id=self.seller_id,
                timestamp=timestamp,
                body=body,
            )
        else:
            sign = sign_open_platform_request(
                app_key=self.app_key,
                app_secret=self.app_secret,
                timestamp=timestamp,
                body=body,
            )
        params: dict[str, str] = {
            "appid": self.app_key,
            "timestamp": timestamp,
            "sign": sign,
        }
        if self.mode == "business" and self.seller_id:
            params["seller_id"] = self.seller_id
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
                message=raw.get("msg") or "open platform business error",
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

    # --- 商品管理 ---

    def create_product(self, payload: dict[str, Any]) -> XianGuanJiaResponse:
        return self._post("/api/open/product/create", payload)

    def batch_create_products(self, payload: dict[str, Any]) -> XianGuanJiaResponse:
        return self._post("/api/open/product/batchCreate", payload)

    def publish_product(self, payload: dict[str, Any]) -> XianGuanJiaResponse:
        return self._post("/api/open/product/publish", payload)

    def unpublish_product(self, payload: dict[str, Any]) -> XianGuanJiaResponse:
        return self._post("/api/open/product/downShelf", payload)

    def edit_product(self, payload: dict[str, Any]) -> XianGuanJiaResponse:
        return self._post("/api/open/product/edit", payload)

    def edit_stock(self, payload: dict[str, Any]) -> XianGuanJiaResponse:
        return self._post("/api/open/product/edit/stock", payload)

    def delete_product(self, payload: dict[str, Any]) -> XianGuanJiaResponse:
        return self._post("/api/open/product/delete", payload)

    def list_products(self, payload: dict[str, Any]) -> XianGuanJiaResponse:
        return self._post("/api/open/product/list", payload)

    def get_product_detail(self, payload: dict[str, Any]) -> XianGuanJiaResponse:
        return self._post("/api/open/product/detail", payload)

    def list_categories(self, payload: dict[str, Any] | None = None) -> XianGuanJiaResponse:
        return self._post("/api/open/product/category/list", payload or {})

    def list_product_attrs(self, payload: dict[str, Any]) -> XianGuanJiaResponse:
        return self._post("/api/open/product/pv/list", payload)

    def list_skus(self, payload: dict[str, Any]) -> XianGuanJiaResponse:
        return self._post("/api/open/product/sku/list", payload)

    # --- 订单管理 ---

    def modify_order_price(self, payload: dict[str, Any]) -> XianGuanJiaResponse:
        return self._post("/api/open/order/modify/price", payload)

    def delivery_order(self, payload: dict[str, Any]) -> XianGuanJiaResponse:
        return self._post("/api/open/order/ship", payload)

    def list_orders(self, payload: dict[str, Any]) -> XianGuanJiaResponse:
        return self._post("/api/open/order/list", payload)

    def get_order_detail(self, payload: dict[str, Any]) -> XianGuanJiaResponse:
        return self._post("/api/open/order/detail", payload)

    def get_order_kam_list(self, payload: dict[str, Any]) -> XianGuanJiaResponse:
        return self._post("/api/open/order/kam/list", payload)

    # --- 用户/授权 ---

    def list_authorized_users(self, payload: dict[str, Any] | None = None) -> XianGuanJiaResponse:
        return self._post("/api/open/user/authorize/list", payload or {})

    # --- 物流 ---

    def list_express_companies(self, payload: dict[str, Any] | None = None) -> XianGuanJiaResponse:
        return self._post("/api/open/express/companies", payload or {})

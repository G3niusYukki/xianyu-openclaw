"""闲管家开放平台 API 适配层。

已废弃 — 请使用 src.integrations.xianguanjia.open_platform_client.OpenPlatformClient。
本文件存在签名 bug（无逗号分隔、毫秒时间戳、sort_keys=True），保留仅为向后兼容。
"""
from __future__ import annotations

import warnings as _warnings
_warnings.warn(
    "orders.xianguanjia.XianGuanJiaClient is deprecated. "
    "Use integrations.xianguanjia.open_platform_client.OpenPlatformClient instead.",
    DeprecationWarning,
    stacklevel=2,
)

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx


def _md5_hex(value: str | bytes) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.md5(data).hexdigest()


def canonical_json(payload: dict[str, Any]) -> str:
    """使用稳定 JSON 序列化，确保签名与请求体一致。"""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def build_sign(
    *,
    app_key: str,
    app_secret: str,
    timestamp: str,
    body: str,
    merchant_id: str | None = None,
) -> str:
    """
    构建闲管家签名。

    文档规则:
    sign = md5(appKey + md5(body) + timestamp + [merchantId] + appSecret)
    """
    pieces = [app_key, _md5_hex(body), timestamp]
    if merchant_id:
        pieces.append(merchant_id)
    pieces.append(app_secret)
    return _md5_hex("".join(pieces))


@dataclass
class XianGuanJiaAPIError(Exception):
    """闲管家 API 返回错误。"""

    message: str
    status_code: int | None = None
    payload: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message


class XianGuanJiaClient:
    """闲管家开放平台最小客户端。"""

    def __init__(
        self,
        *,
        app_key: str,
        app_secret: str,
        base_url: str = "https://open.goofish.pro",
        timeout: float = 30.0,
        merchant_id: str | None = None,
        merchant_query_key: str = "merchantId",
    ) -> None:
        self.app_key = str(app_key).strip()
        self.app_secret = str(app_secret).strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.merchant_id = str(merchant_id).strip() if merchant_id else None
        self.merchant_query_key = merchant_query_key

        if not self.app_key:
            raise ValueError("app_key is required")
        if not self.app_secret:
            raise ValueError("app_secret is required")

    @staticmethod
    def _timestamp_ms() -> str:
        return str(int(time.time() * 1000))

    def _signed_query(self, *, body: str, timestamp: str | None = None) -> dict[str, str]:
        ts = timestamp or self._timestamp_ms()
        query = {
            "appKey": self.app_key,
            "timestamp": ts,
            "sign": build_sign(
                app_key=self.app_key,
                app_secret=self.app_secret,
                timestamp=ts,
                body=body,
                merchant_id=self.merchant_id,
            ),
        }
        if self.merchant_id:
            query[self.merchant_query_key] = self.merchant_id
        return query

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = canonical_json(payload)
        resp = httpx.post(
            f"{self.base_url}{path}",
            params=self._signed_query(body=body),
            content=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise XianGuanJiaAPIError(f"HTTP {resp.status_code}", status_code=resp.status_code)

        data = resp.json()
        if not isinstance(data, dict):
            raise XianGuanJiaAPIError("Invalid response payload", status_code=resp.status_code)

        code = data.get("code")
        if code not in (None, 0, "0"):
            msg = str(data.get("msg") or data.get("message") or "XianGuanJia API error")
            raise XianGuanJiaAPIError(msg, status_code=resp.status_code, payload=data)
        return data

    def edit_product(
        self,
        *,
        product_id: str | int,
        price: int | None = None,
        original_price: int | None = None,
        stock: int | None = None,
        sku_items: list[dict[str, Any]] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"product_id": str(product_id)}
        if price is not None:
            payload["price"] = int(price)
        if original_price is not None:
            payload["original_price"] = int(original_price)
        if stock is not None:
            payload["stock"] = int(stock)
        if sku_items is not None:
            payload["sku_items"] = sku_items
        if extra:
            payload.update(extra)
        return self._post("/api/open/product/edit", payload)

    def edit_product_stock(
        self,
        *,
        product_id: str | int,
        stock: int | None = None,
        sku_items: list[dict[str, Any]] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"product_id": str(product_id)}
        if stock is not None:
            payload["stock"] = int(stock)
        if sku_items is not None:
            payload["sku_items"] = sku_items
        if extra:
            payload.update(extra)
        return self._post("/api/open/product/edit/stock", payload)

    def modify_order_price(
        self,
        *,
        order_no: str,
        order_price: int,
        express_fee: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "order_no": str(order_no),
            "order_price": int(order_price),
        }
        if express_fee is not None:
            payload["express_fee"] = int(express_fee)
        if extra:
            payload.update(extra)
        return self._post("/api/open/order/modify/price", payload)

    def ship_order(
        self,
        *,
        order_no: str,
        waybill_no: str,
        express_code: str,
        express_name: str | None = None,
        ship_name: str | None = None,
        ship_mobile: str | None = None,
        ship_province: str | None = None,
        ship_city: str | None = None,
        ship_area: str | None = None,
        ship_address: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "order_no": str(order_no),
            "waybill_no": str(waybill_no),
            "express_code": str(express_code),
        }
        optional = {
            "express_name": express_name,
            "ship_name": ship_name,
            "ship_mobile": ship_mobile,
            "ship_province": ship_province,
            "ship_city": ship_city,
            "ship_area": ship_area,
            "ship_address": ship_address,
        }
        for key, value in optional.items():
            if value:
                payload[key] = str(value)
        if extra:
            payload.update(extra)
        return self._post("/api/open/order/ship", payload)

    def list_express_companies(self) -> list[dict[str, Any]]:
        data = self._post("/api/open/logistics/company/list", {})
        rows = data.get("data")
        return rows if isinstance(rows, list) else []

    def find_express_company(self, keyword: str) -> dict[str, Any] | None:
        text = str(keyword).strip().lower()
        if not text:
            return None
        for row in self.list_express_companies():
            if not isinstance(row, dict):
                continue
            code = str(row.get("express_code", "")).lower()
            name = str(row.get("express_name", "")).lower()
            if text in {code, name} or text in code or text in name:
                return row
        return None

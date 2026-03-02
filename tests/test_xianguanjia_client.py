from __future__ import annotations

import hashlib
import json

import httpx
import pytest

from src.modules.orders.xianguanjia import (
    XianGuanJiaAPIError,
    XianGuanJiaClient,
    build_sign,
    canonical_json,
)


def test_build_sign_matches_doc_formula_without_merchant() -> None:
    body = '{"product_id":"219530767978565"}'
    sign = build_sign(
        app_key="A1B2C3D4",
        app_secret="SECRET",
        timestamp="1740380565356",
        body=body,
    )

    body_md5 = hashlib.md5(body.encode("utf-8")).hexdigest()
    expected = hashlib.md5(f"A1B2C3D4{body_md5}1740380565356SECRET".encode("utf-8")).hexdigest()
    assert sign == expected


def test_edit_product_posts_signed_compact_json(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    def fake_post(url: str, **kwargs):
        calls["url"] = url
        calls["params"] = kwargs["params"]
        calls["content"] = kwargs["content"]
        calls["headers"] = kwargs["headers"]
        return httpx.Response(200, json={"code": 0, "data": {"task_id": "t1"}})

    monkeypatch.setattr("src.modules.orders.xianguanjia.httpx.post", fake_post)
    client = XianGuanJiaClient(
        app_key="A1B2C3D4",
        app_secret="SECRET",
        base_url="https://example.test",
        merchant_id="M001",
    )

    out = client.edit_product(product_id=123, price=999, stock=5, extra={"title": "测试商品"})

    assert out["data"]["task_id"] == "t1"
    assert calls["url"] == "https://example.test/api/open/product/edit"
    assert calls["headers"] == {"Content-Type": "application/json"}
    body = calls["content"].decode("utf-8")
    assert body == canonical_json({"product_id": "123", "price": 999, "stock": 5, "title": "测试商品"})
    assert calls["params"]["appKey"] == "A1B2C3D4"
    assert calls["params"]["merchantId"] == "M001"
    assert len(calls["params"]["sign"]) == 32


def test_order_modify_ship_and_express_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[tuple[str, dict[str, object]]] = []

    def fake_post(url: str, **kwargs):
        requests.append((url, kwargs))
        if url.endswith("/api/open/logistics/company/list"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": [
                        {"express_code": "YTO", "express_name": "圆通"},
                        {"express_code": "STO", "express_name": "申通"},
                    ],
                },
            )
        return httpx.Response(200, json={"code": 0, "data": {"ok": True}})

    monkeypatch.setattr("src.modules.orders.xianguanjia.httpx.post", fake_post)
    client = XianGuanJiaClient(app_key="A1", app_secret="B2", base_url="https://example.test")

    modify = client.modify_order_price(order_no="O001", order_price=1999, express_fee=300)
    ship = client.ship_order(
        order_no="O001",
        waybill_no="WB123",
        express_code="YTO",
        ship_name="张三",
        ship_mobile="13800138000",
    )
    company = client.find_express_company("圆通")

    assert modify["data"]["ok"] is True
    assert ship["data"]["ok"] is True
    assert company == {"express_code": "YTO", "express_name": "圆通"}
    modify_payload = json.loads(requests[0][1]["content"].decode("utf-8"))
    ship_payload = json.loads(requests[1][1]["content"].decode("utf-8"))
    assert modify_payload == {"express_fee": 300, "order_no": "O001", "order_price": 1999}
    assert ship_payload["order_no"] == "O001"
    assert ship_payload["waybill_no"] == "WB123"
    assert ship_payload["express_code"] == "YTO"
    assert ship_payload["ship_name"] == "张三"


def test_client_raises_on_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(url: str, **kwargs):
        _ = (url, kwargs)
        return httpx.Response(200, json={"code": 4001, "msg": "bad request"})

    monkeypatch.setattr("src.modules.orders.xianguanjia.httpx.post", fake_post)
    client = XianGuanJiaClient(app_key="A1", app_secret="B2", base_url="https://example.test")

    with pytest.raises(XianGuanJiaAPIError, match="bad request"):
        client.edit_product(product_id="1", price=100)

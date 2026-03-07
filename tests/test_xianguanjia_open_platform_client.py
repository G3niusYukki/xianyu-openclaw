from __future__ import annotations

import httpx

from src.integrations.xianguanjia.models import XianGuanJiaResponse
from src.integrations.xianguanjia.open_platform_client import OpenPlatformClient


def test_open_platform_success_response_and_signed_request_surface(monkeypatch) -> None:
    called = []
    sign_calls = []

    def fake_sign_open_platform_request(**kwargs):
        sign_calls.append(kwargs)
        return "sig-op"

    def fake_post(url: str, params: dict, content: bytes, headers: dict, timeout: float):
        called.append((url, params, content, headers, timeout))
        return httpx.Response(200, json={"code": 0, "data": {"ok": True}, "request_id": "rid-1"})

    monkeypatch.setattr(
        "src.integrations.xianguanjia.open_platform_client.sign_open_platform_request",
        fake_sign_open_platform_request,
    )
    monkeypatch.setattr("src.integrations.xianguanjia.open_platform_client.httpx.post", fake_post)
    client = OpenPlatformClient(
        base_url="https://xg.test",
        app_key="ak-1",
        app_secret="as-1",
    )

    methods_with_path = [
        (client.create_product, "/api/open/product/create"),
        (client.publish_product, "/api/open/product/publish"),
        (client.unpublish_product, "/api/open/product/downShelf"),
        (client.edit_product, "/api/open/product/edit"),
        (client.edit_stock, "/api/open/product/edit/stock"),
        (client.modify_order_price, "/api/open/order/modify/price"),
        (client.delivery_order, "/api/open/order/ship"),
        (client.list_orders, "/api/open/order/list"),
        (client.get_order_detail, "/api/open/order/detail"),
    ]
    for method, expected_path in methods_with_path:
        res = method({"a": 1})
        assert isinstance(res, XianGuanJiaResponse)
        assert res.ok is True
        assert called[-1][0] == f"https://xg.test{expected_path}"

    assert len(called) == 9
    assert len(sign_calls) == 9

    _, params, content, headers, _ = called[0]
    assert params["appid"] == "ak-1"
    assert params["sign"] == "sig-op"
    assert "timestamp" in params
    assert headers["Content-Type"] == "application/json"
    assert content == b'{"a":1}'


def test_open_platform_error_uses_map_error(monkeypatch) -> None:
    def fake_sign_open_platform_request(**kwargs):
        _ = kwargs
        return "sig-op"

    def fake_post(url: str, params: dict, content: bytes, headers: dict, timeout: float):
        _ = (url, params, content, headers, timeout)
        return httpx.Response(200, json={"code": "E429", "msg": "too many", "request_id": "rid-2"})

    monkeypatch.setattr(
        "src.integrations.xianguanjia.open_platform_client.sign_open_platform_request",
        fake_sign_open_platform_request,
    )
    monkeypatch.setattr("src.integrations.xianguanjia.open_platform_client.httpx.post", fake_post)
    client = OpenPlatformClient(base_url="https://xg.test", app_key="ak-1", app_secret="as-1")
    res = client.list_orders({"page": 1})

    assert isinstance(res, XianGuanJiaResponse)
    assert res.ok is False
    assert res.retryable is True
    assert res.error_code == "E429"


def test_open_platform_transport_error_no_network(monkeypatch) -> None:
    def fake_sign_open_platform_request(**kwargs):
        _ = kwargs
        return "sig-op"

    def fake_post(url: str, params: dict, content: bytes, headers: dict, timeout: float):
        _ = (url, params, content, headers, timeout)
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(
        "src.integrations.xianguanjia.open_platform_client.sign_open_platform_request",
        fake_sign_open_platform_request,
    )
    monkeypatch.setattr("src.integrations.xianguanjia.open_platform_client.httpx.post", fake_post)
    client = OpenPlatformClient(base_url="https://xg.test", app_key="ak-1", app_secret="as-1")
    res = client.get_order_detail({"order_no": "1"})

    assert isinstance(res, XianGuanJiaResponse)
    assert res.ok is False
    assert res.retryable is True

"""Dashboard 闲管家集成测试。"""

from __future__ import annotations

from unittest.mock import Mock

from src.dashboard_server import MimicOps


class _Console:
    def status(self, **_kwargs):
        return {"modules": {}, "alive_count": 0, "total_modules": 0}

    def control(self, **_kwargs):
        return {"success": True}


def test_mimic_ops_save_and_get_xianguanjia_settings(tmp_path) -> None:
    ops = MimicOps(project_root=tmp_path, module_console=_Console())

    saved = ops.save_xianguanjia_settings(
        {
            "app_key": "ak_123",
            "app_secret": "secret_123456",
            "merchant_id": "m_1",
            "base_url": "https://open.goofish.pro",
            "auto_price_enabled": True,
            "auto_ship_enabled": True,
            "auto_ship_on_paid": False,
        }
    )

    assert saved["success"] is True
    assert saved["configured"] is True
    current = ops.get_xianguanjia_settings()
    assert current["app_key"] == "ak_123"
    assert current["merchant_id"] == "m_1"
    assert current["auto_ship_on_paid"] is False
    assert current["callback_url"] == "/api/orders/callback"


def test_mimic_ops_order_callback_auto_ships_when_enabled(tmp_path, monkeypatch) -> None:
    ops = MimicOps(project_root=tmp_path, module_console=_Console())
    ops.save_xianguanjia_settings(
        {
            "app_key": "ak_123",
            "app_secret": "secret_123456",
            "auto_ship_enabled": True,
            "auto_ship_on_paid": True,
        }
    )

    fake_api = Mock()
    fake_api.list_express_companies = Mock(return_value=Mock(ok=True, data=[{"express_code": "YTO", "express_name": "圆通"}]))
    fake_api.delivery_order = Mock(return_value=Mock(ok=True))
    monkeypatch.setattr("src.modules.orders.service.OrderFulfillmentService._build_shipping_api_client", lambda self: fake_api)

    out = ops.handle_order_callback(
        {
            "order_id": "cb_1",
            "status": "已付款",
            "item_type": "physical",
            "shipping_info": {"waybill_no": "YT123456789", "express_name": "圆通"},
        }
    )

    assert out["success"] is True
    assert out["auto_delivery_triggered"] is True
    assert out["delivery"]["delivery"]["channel"] == "xianguanjia_api"
    fake_api.delivery_order.assert_called_once()


def test_mimic_ops_retry_price_uses_operations_service(tmp_path, monkeypatch) -> None:
    ops = MimicOps(project_root=tmp_path, module_console=_Console())
    ops.save_xianguanjia_settings({"app_key": "ak_123", "app_secret": "secret_123456"})

    async def fake_update_price(self, product_id, new_price, original_price=None):
        assert product_id == "p001"
        assert new_price == 19.9
        assert original_price == 29.9
        return {"success": True, "channel": "xianguanjia_api", "product_id": product_id}

    monkeypatch.setattr("src.modules.operations.service.OperationsService.update_price", fake_update_price)

    out = ops.retry_xianguanjia_price({"product_id": "p001", "new_price": 19.9, "original_price": 29.9})

    assert out["success"] is True
    assert out["channel"] == "xianguanjia_api"

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from src.modules.operations.service import OperationsService


@pytest.mark.asyncio
async def test_operations_update_price_prefers_xianguanjia_api() -> None:
    api = Mock()
    api.edit_product = Mock(return_value={"code": 0, "data": {"task_id": "t1"}})
    analytics = Mock(log_operation=AsyncMock())
    svc = OperationsService(controller=None, analytics=analytics, price_api_client=api)

    out = await svc.update_price("pid-1", 9.9, 12.3)

    assert out["success"] is True
    assert out["channel"] == "xianguanjia_api"
    assert out["api_response"]["data"]["task_id"] == "t1"
    api.edit_product.assert_called_once_with(product_id="pid-1", price=990, original_price=1230)
    analytics.log_operation.assert_awaited_once()


@pytest.mark.asyncio
async def test_operations_update_price_falls_back_to_dom_when_api_fails() -> None:
    api = Mock()
    api.edit_product = Mock(side_effect=RuntimeError("api boom"))

    controller = Mock()
    controller.new_page = AsyncMock(return_value="p1")
    controller.navigate = AsyncMock(return_value=True)
    controller.click = AsyncMock(side_effect=[True, True])
    controller.type_text = AsyncMock(return_value=True)
    controller.close_page = AsyncMock(return_value=True)

    analytics = Mock(log_operation=AsyncMock())
    svc = OperationsService(controller=controller, analytics=analytics, price_api_client=api)
    svc._random_delay = Mock(return_value=0)

    out = await svc.update_price("pid-2", 8.8, 10.0)

    assert out["success"] is True
    assert out["channel"] == "dom"
    assert out["api_error"] == "api boom"
    controller.type_text.assert_awaited_once_with("p1", svc.selectors.PRICE_INPUT, "8.8")
    controller.close_page.assert_awaited_once_with("p1")
    analytics.log_operation.assert_awaited_once()


@pytest.mark.asyncio
async def test_operations_update_price_returns_api_error_without_dom_fallback() -> None:
    api = Mock()
    api.edit_product = Mock(side_effect=RuntimeError("api boom"))
    analytics = Mock(log_operation=AsyncMock())
    svc = OperationsService(controller=None, analytics=analytics, price_api_client=api)

    out = await svc.update_price("pid-3", 7.7)

    assert out["success"] is False
    assert out["channel"] == "xianguanjia_api"
    assert out["error"] == "api boom"
    assert out["new_price"] == 7.7
    analytics.log_operation.assert_awaited_once()

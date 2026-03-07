from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.modules.operations.service import OperationsService


@pytest.mark.asyncio
async def test_operations_update_price_prefers_xianguanjia_api() -> None:
    api = Mock()
    api.edit_product = Mock(
        return_value=SimpleNamespace(ok=True, data={"task_id": "t1"}, error_message=None)
    )
    analytics = Mock(log_operation=AsyncMock())
    svc = OperationsService(controller=None, analytics=analytics, api_client=api)

    out = await svc.update_price("pid-1", 9.9, 12.3)

    assert out["success"] is True
    assert out["channel"] == "xianguanjia_api"
    api.edit_product.assert_called_once_with(
        {"product_id": "pid-1", "price": 990, "original_price": 1230}
    )
    analytics.log_operation.assert_awaited_once()


@pytest.mark.asyncio
async def test_operations_update_price_api_failure_returns_error() -> None:
    api = Mock()
    api.edit_product = Mock(side_effect=RuntimeError("api boom"))
    analytics = Mock(log_operation=AsyncMock())
    svc = OperationsService(controller=None, analytics=analytics, api_client=api)

    out = await svc.update_price("pid-2", 8.8, 10.0)

    assert out["success"] is False
    assert out["channel"] == "xianguanjia_api"
    assert out["error"] == "api boom"
    assert out["new_price"] == 8.8
    analytics.log_operation.assert_awaited_once()


@pytest.mark.asyncio
async def test_operations_update_price_returns_error_without_api_client() -> None:
    analytics = Mock(log_operation=AsyncMock())
    svc = OperationsService(controller=None, analytics=analytics)

    out = await svc.update_price("pid-3", 7.7)

    assert out["success"] is False
    assert out["channel"] == "xianguanjia_api"
    assert out["error"] == "api_client_not_configured"
    assert out["new_price"] == 7.7
    analytics.log_operation.assert_awaited_once()

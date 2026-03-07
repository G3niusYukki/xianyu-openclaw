from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.modules.orders.price_execution import PriceExecutionService


@pytest.fixture
def svc(tmp_path):
    return PriceExecutionService(db_path=str(tmp_path / "test.db"))


class TestDecideTargetPrice:
    def test_buyer_not_lower(self):
        result = PriceExecutionService.decide_target_price(
            from_price=100.0, buyer_offer_price=120.0, min_price=80.0
        )
        assert result["reason"] == "buyer_offer_not_lower"
        assert result["target_price"] == 100.0

    def test_buyer_equal(self):
        result = PriceExecutionService.decide_target_price(
            from_price=100.0, buyer_offer_price=100.0, min_price=80.0
        )
        assert result["reason"] == "buyer_offer_not_lower"


class TestCreateJob:
    def test_unsupported_scope(self, svc):
        with pytest.raises(ValueError, match="Unsupported price_scope"):
            svc.create_job(
                session_id="s1",
                product_id="p1",
                from_price=100,
                buyer_offer_price=80,
                min_price=70,
                price_scope="weird",
            )

    def test_order_scope_no_order_id(self, svc):
        with pytest.raises(ValueError, match="order_id is required"):
            svc.create_job(
                session_id="s1",
                product_id="p1",
                from_price=100,
                buyer_offer_price=80,
                min_price=70,
                price_scope="order",
            )

    def test_product_scope_no_product_id(self, svc):
        with pytest.raises(ValueError, match="product_id is required"):
            svc.create_job(
                session_id="s1",
                product_id="",
                from_price=100,
                buyer_offer_price=80,
                min_price=70,
                price_scope="product",
            )


class TestPriceScopeFor:
    def test_order_id_fallback(self):
        assert PriceExecutionService._price_scope_for({"order_id": "o1"}) == "order"

    def test_product_fallback(self):
        assert PriceExecutionService._price_scope_for({}) == "product"

    def test_strategy_scope(self):
        assert PriceExecutionService._price_scope_for(
            {"strategy": {"price_scope": "order"}}
        ) == "order"


class TestAwaitIfNeeded:
    @pytest.mark.asyncio
    async def test_non_awaitable(self):
        svc = PriceExecutionService.__new__(PriceExecutionService)
        result = await svc._await_if_needed(42)
        assert result == 42


class TestInvokeWithSupportedKwargs:
    @pytest.mark.asyncio
    async def test_uninspectable_func(self):
        svc = PriceExecutionService.__new__(PriceExecutionService)
        func = MagicMock(return_value={"success": True})
        func.__signature__ = None
        del func.__signature__
        with patch.object(inspect, "signature", side_effect=TypeError):
            result = await svc._invoke_with_supported_kwargs(func, [{"a": 1}])
        assert result == {"success": True}

    @pytest.mark.asyncio
    async def test_no_matching_params(self):
        svc = PriceExecutionService.__new__(PriceExecutionService)

        def strict_func(x: int, y: int) -> dict:
            return {}

        with pytest.raises(TypeError, match="No supported parameter combination"):
            await svc._invoke_with_supported_kwargs(strict_func, [{"a": 1}, {"b": 2}])


class TestNormalizeResult:
    def test_product_price_on_order_flow(self):
        result = PriceExecutionService._normalize_result(
            result={"channel": "product_price_api"},
            price_scope="order",
            order_id="o1",
            product_id="p1",
        )
        assert result["success"] is False
        assert result["error"] == "product_price_result_on_order_flow"

    def test_price_update_action_on_order_flow(self):
        result = PriceExecutionService._normalize_result(
            result={"action": "price_update"},
            price_scope="order",
            order_id="o1",
            product_id="p1",
        )
        assert result["success"] is False

    def test_order_price_on_product_flow(self):
        result = PriceExecutionService._normalize_result(
            result={"channel": "order_price_api"},
            price_scope="product",
            order_id="",
            product_id="p1",
        )
        assert result["success"] is False
        assert result["error"] == "order_price_result_on_product_flow"


class TestGetJob:
    def test_not_found(self, svc):
        assert svc.get_job(9999) is None


class TestExecuteJob:
    @pytest.mark.asyncio
    async def test_job_not_found(self, svc):
        with pytest.raises(ValueError, match="Job not found"):
            await svc.execute_job(9999, MagicMock())

    @pytest.mark.asyncio
    async def test_exception_path(self, svc):
        job = svc.create_job(
            session_id="s1",
            product_id="p1",
            from_price=100,
            buyer_offer_price=80,
            min_price=70,
        )
        job_id = job["id"]

        ops = MagicMock()
        ops.update_price = MagicMock(side_effect=RuntimeError("boom"))

        result = await svc.execute_job(job_id, ops)
        assert result["job"]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_product_price_unsupported(self, svc):
        job = svc.create_job(
            session_id="s1",
            product_id="p1",
            from_price=100,
            buyer_offer_price=80,
            min_price=70,
        )
        job_id = job["id"]

        ops = MagicMock(spec=[])

        result = await svc.execute_job(job_id, ops)
        assert result["job"]["status"] == "failed"


class TestNotifyFailure:
    @pytest.mark.asyncio
    async def test_no_send_text(self, svc):
        svc.notifier = MagicMock(spec=[])
        await svc._notify_failure(job_id=1, job={}, error="err")

    @pytest.mark.asyncio
    async def test_send_text_exception(self, svc):
        notifier = MagicMock()
        notifier.send_text.side_effect = RuntimeError("fail")
        svc.notifier = notifier
        await svc._notify_failure(job_id=1, job={}, error="err")

    @pytest.mark.asyncio
    async def test_send_text_awaitable(self, svc):
        notifier = MagicMock()
        notifier.send_text = AsyncMock(return_value=None)
        svc.notifier = notifier
        await svc._notify_failure(job_id=1, job={"session_id": "s"}, error="err")
        notifier.send_text.assert_called_once()


class TestReplayJob:
    def test_not_found(self, svc):
        with pytest.raises(ValueError, match="Job not found"):
            svc.replay_job(9999)

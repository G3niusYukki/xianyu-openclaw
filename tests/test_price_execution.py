from __future__ import annotations

import asyncio

import pytest

from src.modules.orders.price_execution import PriceExecutionService


class DummyOrderOpsSuccess:
    async def modify_order_price(self, order_id: str, order_price: int):
        return {
            "success": True,
            "order_id": order_id,
            "order_price": order_price,
        }


class DummyOrderOpsFail:
    async def modify_order_price(self, order_no: str, order_price: int):
        return {
            "success": False,
            "order_no": order_no,
            "order_price": order_price,
            "channel": "dom",
            "error": "dom_not_found",
        }


class DummyNotifier:
    def __init__(self):
        self.messages = []

    async def send_text(self, text: str):
        self.messages.append(str(text))
        return True


def test_decide_target_price_floor_guard():
    d = PriceExecutionService.decide_target_price(from_price=100, buyer_offer_price=80, min_price=88)
    assert d["target_price"] == 88
    assert d["reason"] == "respect_floor_price"


@pytest.mark.asyncio
async def test_price_execution_defaults_to_order_price_flow(temp_dir):
    svc = PriceExecutionService(db_path=str(temp_dir / "orders.db"))
    job = svc.create_job(
        session_id="sess-order-default",
        order_id="ord-default",
        product_id="prod-default",
        from_price=100,
        buyer_offer_price=93,
        min_price=90,
    )

    replay = await svc.execute_job(job_id=int(job["id"]), operations_service=DummyOrderOpsSuccess())

    assert replay["job"]["status"] == "success"
    assert replay["job"]["result"]["action"] == "modify_order_price"
    assert replay["job"]["result"]["channel"] == "order_price_api"


@pytest.mark.asyncio
async def test_price_execution_success_replay(temp_dir):
    svc = PriceExecutionService(db_path=str(temp_dir / "orders.db"))
    job = svc.create_job(
        session_id="sess-1",
        order_id="ord-1",
        product_id="prod-1",
        from_price=100,
        buyer_offer_price=93,
        min_price=90,
    )

    replay = await svc.execute_job(job_id=int(job["id"]), operations_service=DummyOrderOpsSuccess())

    assert replay["job"]["status"] == "success"
    assert replay["job"]["result"]["action"] == "modify_order_price"
    assert replay["job"]["result"]["channel"] == "order_price_api"
    assert [e["event_type"] for e in replay["events"]] == [
        "strategy_decided",
        "execution_started",
        "execution_finished",
    ]


@pytest.mark.asyncio
async def test_price_execution_failure_alert_and_replay(temp_dir):
    notifier = DummyNotifier()
    svc = PriceExecutionService(db_path=str(temp_dir / "orders.db"), notifier=notifier)
    job = svc.create_job(
        session_id="sess-2",
        order_id="ord-2",
        product_id="prod-2",
        from_price=120,
        buyer_offer_price=90,
        min_price=95,
    )

    replay = await svc.execute_job(job_id=int(job["id"]), operations_service=DummyOrderOpsFail())

    assert replay["job"]["status"] == "failed"
    assert replay["job"]["last_error"] == "dom_not_found"
    assert replay["job"]["result"]["action"] == "modify_order_price"
    assert replay["job"]["result"]["channel"] == "dom"
    assert replay["events"][-1]["event_type"] == "execution_finished"
    assert replay["events"][-1]["status"] == "failed"
    assert notifier.messages
    assert "改价执行失败" in notifier.messages[0]


class DummyOrderOpsSlowSuccess:
    def __init__(self):
        self.calls = 0

    async def modify_order_price(self, order_id: str, order_price: int):
        self.calls += 1
        await asyncio.sleep(0.05)
        return {
            "success": True,
            "order_id": order_id,
            "order_price": order_price,
        }


@pytest.mark.asyncio
async def test_execute_job_cas_gate_prevents_reentrant_double_run(temp_dir):
    svc = PriceExecutionService(db_path=str(temp_dir / "orders.db"))
    job = svc.create_job(
        session_id="sess-cas",
        product_id="prod-cas",
        from_price=100,
        buyer_offer_price=91,
        min_price=90,
        order_id="ord-cas",
    )

    ops = DummyOrderOpsSlowSuccess()
    replay1, replay2 = await asyncio.gather(
        svc.execute_job(job_id=int(job["id"]), operations_service=ops),
        svc.execute_job(job_id=int(job["id"]), operations_service=ops),
    )

    assert replay1["job"]["status"] in {"running", "success"}
    assert replay2["job"]["status"] in {"running", "success"}
    assert ops.calls == 1

    final = svc.replay_job(int(job["id"]))
    assert final["job"]["status"] == "success"
    assert final["job"]["attempts"] == 1
    assert [e["event_type"] for e in final["events"]] == [
        "strategy_decided",
        "execution_started",
        "execution_finished",
    ]


@pytest.mark.asyncio
async def test_execute_job_idempotent_replay_after_finished(temp_dir):
    svc = PriceExecutionService(db_path=str(temp_dir / "orders.db"))
    job = svc.create_job(
        session_id="sess-idempotent",
        product_id="prod-idempotent",
        from_price=100,
        buyer_offer_price=91,
        min_price=90,
        order_id="ord-idempotent",
    )

    ops = DummyOrderOpsSuccess()
    await svc.execute_job(job_id=int(job["id"]), operations_service=ops)
    replay = await svc.execute_job(job_id=int(job["id"]), operations_service=ops)

    assert replay["job"]["status"] == "success"
    assert replay["job"]["attempts"] == 1
    assert [e["event_type"] for e in replay["events"]] == [
        "strategy_decided",
        "execution_started",
        "execution_finished",
    ]


class DummyProductOpsSuccess:
    def __init__(self) -> None:
        self.calls = 0

    async def update_price(self, product_id: str, new_price: float, original_price: float | None = None):
        self.calls += 1
        return {
            "success": True,
            "product_id": product_id,
            "old_price": original_price,
            "new_price": new_price,
            "action": "price_update",
            "channel": "xianguanjia_api",
        }


@pytest.mark.asyncio
async def test_price_execution_product_scope_uses_product_channel(temp_dir):
    svc = PriceExecutionService(db_path=str(temp_dir / "orders_product.db"))
    job = svc.create_job(
        session_id="sess-product",
        product_id="prod-product",
        from_price=100,
        buyer_offer_price=92,
        min_price=90,
        price_scope="product",
    )

    replay = await svc.execute_job(job_id=int(job["id"]), operations_service=DummyProductOpsSuccess())

    assert replay["job"]["status"] == "success"
    assert replay["job"]["result"]["action"] == "edit_product_price"
    assert replay["job"]["result"]["channel"] == "product_price_api"


@pytest.mark.asyncio
async def test_price_execution_never_uses_product_update_for_order_flow(temp_dir):
    svc = PriceExecutionService(db_path=str(temp_dir / "orders_guard.db"))
    job = svc.create_job(
        session_id="sess-guard",
        order_id="ord-guard",
        product_id="prod-guard",
        from_price=100,
        buyer_offer_price=91,
        min_price=90,
    )

    ops = DummyProductOpsSuccess()
    replay = await svc.execute_job(job_id=int(job["id"]), operations_service=ops)

    assert replay["job"]["status"] == "failed"
    assert replay["job"]["last_error"] == "order_price_unsupported"
    assert replay["job"]["result"]["action"] == "modify_order_price"
    assert replay["job"]["result"]["channel"] == "order_price_api"
    assert ops.calls == 0

import pytest

from src.modules.orders.price_execution import PriceExecutionService


class DummyOpsSuccess:
    async def update_price(self, product_id: str, new_price: float, original_price: float | None = None):
        return {
            "success": True,
            "product_id": product_id,
            "old_price": original_price,
            "new_price": new_price,
            "action": "price_update",
        }


class DummyOpsFail:
    async def update_price(self, product_id: str, new_price: float, original_price: float | None = None):
        return {
            "success": False,
            "product_id": product_id,
            "old_price": original_price,
            "new_price": new_price,
            "action": "price_update",
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
async def test_price_execution_success_replay(temp_dir):
    svc = PriceExecutionService(db_path=str(temp_dir / "orders.db"))
    job = svc.create_job(
        session_id="sess-1",
        product_id="prod-1",
        from_price=100,
        buyer_offer_price=93,
        min_price=90,
        order_id="ord-1",
    )

    replay = await svc.execute_job(job_id=int(job["id"]), operations_service=DummyOpsSuccess())

    assert replay["job"]["status"] == "success"
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
        product_id="prod-2",
        from_price=120,
        buyer_offer_price=90,
        min_price=95,
        order_id="ord-2",
    )

    replay = await svc.execute_job(job_id=int(job["id"]), operations_service=DummyOpsFail())

    assert replay["job"]["status"] == "failed"
    assert replay["job"]["last_error"] == "dom_not_found"
    assert replay["events"][-1]["event_type"] == "execution_finished"
    assert replay["events"][-1]["status"] == "failed"
    assert notifier.messages
    assert "改价执行失败" in notifier.messages[0]

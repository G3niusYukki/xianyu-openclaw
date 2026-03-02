from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.modules.messages.service import MessagesService
from src.modules.orders.price_execution import PriceExecutionService
from src.modules.orders.service import OrderFulfillmentService


class _OpsSuccess:
    async def update_price(self, product_id: str, new_price: float, original_price: float | None = None):
        return {
            "success": True,
            "product_id": product_id,
            "old_price": original_price,
            "new_price": new_price,
            "action": "price_update",
        }


def _make_messages_service(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> MessagesService:
    cfg = SimpleNamespace(
        browser={"delay": {"min": 0.0, "max": 0.0}},
        accounts=[{"enabled": True, "cookie": "unb=10001; _m_h5_tk=tk_1"}],
    )

    def get_section(name, default=None):
        if name == "messages":
            return {
                "transport": "dom",
                "quote": {"preferred_couriers": ["圆通", "中通"]},
                "strict_format_reply_enabled": False,
                "context_memory_enabled": True,
                "send_confirm_delay_seconds": [0.0, 0.0],
            }
        if name == "quote":
            return {}
        if name == "content":
            return {"templates": {"path": str(tmp_path)}}
        return default or {}

    cfg.get_section = get_section

    class Guard:
        def evaluate_content(self, _text):
            return {"blocked": False}

    monkeypatch.setattr("src.modules.messages.service.get_config", lambda: cfg)
    monkeypatch.setattr("src.modules.messages.service.get_compliance_guard", lambda: Guard())
    return MessagesService(controller=None, config={})


@pytest.mark.asyncio
async def test_minimal_e2e_inquiry_reprice_callback_writeback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """最小闭环：询价 -> 改价 -> 回调(状态同步) -> 结果回写。"""
    db_path = tmp_path / "orders_e2e.db"

    # 1) 询价
    messages = _make_messages_service(monkeypatch, tmp_path)
    reply, meta = await messages._generate_reply_with_quote("杭州到上海 1kg 圆通报价", session_id="sid-e2e")
    assert isinstance(reply, str) and reply
    assert meta.get("is_quote") is True

    quote_snapshot = {
        "quote_result": meta.get("quote_result", {}),
        "quote_all_couriers": meta.get("quote_all_couriers", []),
    }

    # 2) 改价执行
    pe = PriceExecutionService(db_path=str(db_path))
    job = pe.create_job(
        session_id="sid-e2e",
        product_id="pid-e2e",
        from_price=100.0,
        buyer_offer_price=92.0,
        min_price=90.0,
        order_id="ord-e2e",
        strategy_meta={"source": "e2e"},
    )
    replay = await pe.execute_job(int(job["id"]), _OpsSuccess())
    assert replay["job"]["status"] == "success"
    assert any(ev["event_type"] == "execution_finished" for ev in replay["events"])

    # 3) 回调（用订单状态同步模拟支付回调入站）
    ofs = OrderFulfillmentService(db_path=str(db_path))
    ofs.upsert_order(
        order_id="ord-e2e",
        raw_status="已付款",
        session_id="sid-e2e",
        quote_snapshot=quote_snapshot,
        item_type="virtual",
    )

    # 4) 结果回写校验
    trace = ofs.trace_order("ord-e2e")
    assert trace["order"]["status"] == "paid"
    assert trace["order"]["quote_snapshot"] == quote_snapshot
    assert any(ev["event_type"] == "status_sync" for ev in trace["events"])

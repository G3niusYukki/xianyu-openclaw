from __future__ import annotations

from typing import Any

from src.modules.virtual_goods.models import normalize_order_status
from src.modules.virtual_goods.store import VirtualGoodsStore


class OrderStore:
    def __init__(self, db_path: str = "data/orders.db") -> None:
        self.vg_store = VirtualGoodsStore(db_path=db_path)

    def upsert_from_open_platform_detail(self, detail: dict[str, Any]) -> dict[str, Any]:
        order_id = str(detail.get("order_no") or detail.get("order_id") or detail.get("id") or "").strip()
        if not order_id:
            raise ValueError("missing order_no")
        status = normalize_order_status(str(detail.get("status") or detail.get("order_status") or ""))
        return self.vg_store.upsert_order(
            xianyu_order_id=order_id,
            xianyu_product_id=str(detail.get("product_id") or detail.get("item_id") or ""),
            supply_order_no=str(detail.get("supply_order_no") or "").strip() or None,
            session_id=str(detail.get("session_id") or detail.get("chat_id") or ""),
            order_status=status,
            callback_status="received",
            fulfillment_status=str(detail.get("fulfillment_status") or "pending"),
            manual_takeover=bool(detail.get("manual_takeover") or False),
        )

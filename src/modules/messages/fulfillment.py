"""
订单履约确认辅助
Order fulfillment confirmation helper
"""

from __future__ import annotations

from typing import Any


DEFAULT_ORDER_INTENT_KEYWORDS = [
    "下单",
    "已下单",
    "拍下",
    "已拍",
    "拍了",
    "已拍下",
    "付款",
    "已付款",
    "付了",
]

DEFAULT_FULFILLMENT_ACK_TEMPLATE = (
    "收到你的订单，我这边开始处理，结果会优先在闲鱼聊天内同步，请耐心等我一下。"
)


class FulfillmentHelper:
    """识别订单确认意图并生成履约确认回复。"""

    def __init__(self, config: dict[str, Any] | None = None):
        cfg = config or {}
        self.enabled = bool(cfg.get("fulfillment_confirm_enabled", True))

        keywords = cfg.get("order_intent_keywords")
        if isinstance(keywords, list):
            parsed = [str(item).strip().lower() for item in keywords if str(item).strip()]
        else:
            parsed = []
        self.order_intent_keywords = parsed or list(DEFAULT_ORDER_INTENT_KEYWORDS)

        self.ack_template = str(cfg.get("fulfillment_ack_template", DEFAULT_FULFILLMENT_ACK_TEMPLATE)).strip()
        if not self.ack_template:
            self.ack_template = DEFAULT_FULFILLMENT_ACK_TEMPLATE

    def is_order_intent(self, message_text: str) -> bool:
        if not self.enabled:
            return False
        text = str(message_text or "").strip().lower()
        if not text:
            return False
        return any(keyword in text for keyword in self.order_intent_keywords)

    def build_ack_reply(self, item_title: str = "") -> str:
        reply = self.ack_template
        if "{item_title}" in reply:
            reply = reply.replace("{item_title}", str(item_title or "商品"))
        return reply

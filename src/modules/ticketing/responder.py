"""Second-stage text response generation for ticketing workflows."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import TicketPurchaseResult, TicketQuote, TicketSelection


class ITicketTextResponder(ABC):
    """Converts structured ticket data into a buyer-facing reply."""

    @abstractmethod
    async def compose_pre_sale_reply(self, selection: TicketSelection, quote: TicketQuote, needs_manual_review: bool) -> str:
        pass

    @abstractmethod
    async def compose_post_purchase_reply(self, result: TicketPurchaseResult) -> str:
        pass


class RuleBasedTicketResponder(ITicketTextResponder):
    """Deterministic responder that only consumes structured outputs."""

    async def compose_pre_sale_reply(
        self, selection: TicketSelection, quote: TicketQuote, needs_manual_review: bool
    ) -> str:
        if needs_manual_review:
            return (
                f"已识别到截图需求：{selection.cinema} {selection.showtime} {selection.seat}，"
                "但当前识别置信度偏低，我先转人工复核，确认后再给你最终报价。"
            )

        return (
            f"已识别：{selection.cinema} {selection.showtime} {selection.seat}，"
            f"共 {selection.count} 张。当前报价 ¥{quote.final_price:.2f}，"
            "确认无误可直接拍下，我会按识别结果安排代下单。"
        )

    async def compose_post_purchase_reply(self, result: TicketPurchaseResult) -> str:
        if not result.success:
            return "上游出票暂未成功，我已转人工跟进，请稍等我确认处理结果。"

        if result.ticket_code:
            return f"已完成代下单，票码/取票信息：{result.ticket_code}"

        return "已完成代下单，票务信息已准备好，我马上通过会话发给你。"

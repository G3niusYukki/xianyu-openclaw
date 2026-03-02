"""Ticketing orchestration service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import TicketListingDraft, TicketPurchaseRequest, TicketPurchaseResult, TicketQuote, TicketSelection
from .pricing import TicketPricingPolicy
from .providers import ITicketProvider
from .recognizer import ITicketRecognizer
from .responder import ITicketTextResponder, RuleBasedTicketResponder


@dataclass(slots=True)
class TicketingDecision:
    """End-to-end structured output for the two-stage pipeline."""

    selection: TicketSelection
    quote: TicketQuote
    reply_text: str
    needs_manual_review: bool


class TicketingService:
    """Coordinates recognition, quoting, listing draft generation, and post-purchase fulfillment."""

    def __init__(
        self,
        *,
        recognizer: ITicketRecognizer,
        provider: ITicketProvider,
        pricing: TicketPricingPolicy | None = None,
        responder: ITicketTextResponder | None = None,
        review_confidence_threshold: float = 0.75,
    ) -> None:
        self.recognizer = recognizer
        self.provider = provider
        self.pricing = pricing or TicketPricingPolicy()
        self.responder = responder or RuleBasedTicketResponder()
        self.review_confidence_threshold = max(0.0, min(1.0, float(review_confidence_threshold)))

    async def recognize(self, image_bytes: bytes, mime_type: str = "image/png") -> TicketSelection:
        return await self.recognizer.recognize(image_bytes, mime_type=mime_type)

    async def quote(self, selection: TicketSelection) -> TicketQuote:
        upstream_quote = await self.provider.quote_ticket(selection)
        return self.pricing.quote(selection, upstream_quote)

    async def quote_from_screenshot(self, image_bytes: bytes, mime_type: str = "image/png") -> tuple[TicketSelection, TicketQuote]:
        selection = await self.recognize(image_bytes, mime_type=mime_type)
        quote = await self.quote(selection)
        return selection, quote

    def build_listing_draft(self, selection: TicketSelection, quote: TicketQuote) -> TicketListingDraft:
        title = f"{selection.cinema} {selection.showtime} 代买代订"
        description = (
            f"影院：{selection.cinema}\n"
            f"场次：{selection.showtime}\n"
            f"座位：{selection.seat}\n"
            f"数量：{selection.count}\n"
            f"报价：¥{quote.final_price:.2f}\n"
            "拍下后按截图信息代下单，成功后回传票码/取票信息。"
        )
        tags = ["电影票", "代下单", "自动报价", "截图识别"]
        metadata = {
            "cinema": selection.cinema,
            "showtime": selection.showtime,
            "seat": selection.seat,
            "count": selection.count,
            "provider": quote.provider,
            "channel_price": quote.channel_price,
        }
        return TicketListingDraft(
            title=title,
            description=description,
            price=quote.final_price,
            tags=tags,
            metadata=metadata,
        )

    async def prepare_listing_from_screenshot(
        self, image_bytes: bytes, mime_type: str = "image/png"
    ) -> tuple[TicketSelection, TicketQuote, TicketListingDraft]:
        selection, quote = await self.quote_from_screenshot(image_bytes, mime_type=mime_type)
        draft = self.build_listing_draft(selection, quote)
        return selection, quote, draft

    def needs_manual_review(self, selection: TicketSelection) -> bool:
        return float(selection.confidence) < self.review_confidence_threshold

    async def analyze_and_reply(self, image_bytes: bytes, mime_type: str = "image/png") -> TicketingDecision:
        selection, quote = await self.quote_from_screenshot(image_bytes, mime_type=mime_type)
        manual_review = self.needs_manual_review(selection)
        reply_text = await self.responder.compose_pre_sale_reply(selection, quote, manual_review)
        return TicketingDecision(
            selection=selection,
            quote=quote,
            reply_text=reply_text,
            needs_manual_review=manual_review,
        )

    async def fulfill_order(
        self,
        *,
        order_id: str,
        selection: TicketSelection,
        quote: TicketQuote,
        buyer_requirements: dict[str, Any] | None = None,
    ) -> TicketPurchaseResult:
        request = TicketPurchaseRequest(
            order_id=order_id,
            selection=selection,
            quote=quote,
            buyer_requirements=dict(buyer_requirements or {}),
        )
        return await self.provider.create_purchase(request)

    async def compose_post_purchase_reply(self, result: TicketPurchaseResult) -> str:
        return await self.responder.compose_post_purchase_reply(result)

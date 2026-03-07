from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.ticketing.models import (
    TicketPurchaseRequest,
    TicketPurchaseResult,
    TicketQuote,
    TicketSelection,
)


class TestTicketResponder:
    """Cover uncovered lines in responder.py."""

    async def test_compose_pre_sale_reply_normal(self):
        from src.modules.ticketing.responder import RuleBasedTicketResponder
        responder = RuleBasedTicketResponder()
        selection = TicketSelection(cinema="万达影城", showtime="19:00", seat="A1", count=2)
        quote = TicketQuote(
            provider="static", face_value=50.0, channel_price=45.0,
            seat_premium=0.0, service_fee=0.0, final_price=45.0,
        )
        reply = await responder.compose_pre_sale_reply(selection, quote, needs_manual_review=False)
        assert "已识别" in reply
        assert "45.00" in reply

    async def test_compose_pre_sale_reply_manual_review(self):
        from src.modules.ticketing.responder import RuleBasedTicketResponder
        responder = RuleBasedTicketResponder()
        selection = TicketSelection(cinema="万达影城", showtime="19:00", seat="A1", count=2)
        quote = TicketQuote(
            provider="static", face_value=50.0, channel_price=45.0,
            seat_premium=0.0, service_fee=0.0, final_price=45.0,
        )
        reply = await responder.compose_pre_sale_reply(selection, quote, needs_manual_review=True)
        assert "人工复核" in reply

    async def test_compose_post_purchase_reply_success_with_code(self):
        from src.modules.ticketing.responder import RuleBasedTicketResponder
        responder = RuleBasedTicketResponder()
        result = TicketPurchaseResult(
            success=True, provider="static", ticket_code="TICKET-123"
        )
        reply = await responder.compose_post_purchase_reply(result)
        assert "TICKET-123" in reply

    async def test_compose_post_purchase_reply_success_no_code(self):
        from src.modules.ticketing.responder import RuleBasedTicketResponder
        responder = RuleBasedTicketResponder()
        result = TicketPurchaseResult(success=True, provider="static", ticket_code="")
        reply = await responder.compose_post_purchase_reply(result)
        assert "已完成" in reply

    async def test_compose_post_purchase_reply_failure(self):
        from src.modules.ticketing.responder import RuleBasedTicketResponder
        responder = RuleBasedTicketResponder()
        result = TicketPurchaseResult(success=False, provider="static")
        reply = await responder.compose_post_purchase_reply(result)
        assert "人工" in reply


class TestTicketPricingPolicy:
    """Cover uncovered lines 49-50 in pricing.py."""

    def test_resolve_seat_premium_hit(self):
        from src.modules.ticketing.pricing import TicketPricingPolicy
        policy = TicketPricingPolicy(seat_premium_rules={"VIP": 10.0, "A": 5.0})
        assert policy._resolve_seat_premium("VIP1") == 10.0
        assert policy._resolve_seat_premium("A3") == 5.0

    def test_resolve_seat_premium_no_hit(self):
        from src.modules.ticketing.pricing import TicketPricingPolicy
        policy = TicketPricingPolicy(seat_premium_rules={"VIP": 10.0})
        assert policy._resolve_seat_premium("B1") == 0.0


class TestTicketProviders:
    """Cover uncovered lines in providers.py."""

    async def test_static_provider_quote(self):
        from src.modules.ticketing.providers import StaticTicketProvider
        provider = StaticTicketProvider(default_channel_price=30.0)
        selection = TicketSelection(cinema="万达", showtime="19:00", seat="A1", count=1)
        quote = await provider.quote_ticket(selection)
        assert quote.channel_price == 30.0
        assert quote.provider == "static"

    async def test_static_provider_create_purchase(self):
        from src.modules.ticketing.providers import StaticTicketProvider
        provider = StaticTicketProvider()
        selection = TicketSelection(cinema="万达", showtime="19:00", seat="A1", count=1)
        quote = TicketQuote(
            provider="static", face_value=50.0, channel_price=45.0,
            seat_premium=0.0, service_fee=0.0, final_price=45.0,
        )
        request = TicketPurchaseRequest(order_id="o1", selection=selection, quote=quote)
        result = await provider.create_purchase(request)
        assert result.success is True

    async def test_static_provider_health_check(self):
        from src.modules.ticketing.providers import StaticTicketProvider
        provider = StaticTicketProvider()
        assert await provider.health_check() is True

    async def test_iticker_provider_abstract(self):
        from src.modules.ticketing.providers import ITicketProvider
        with pytest.raises(TypeError):
            ITicketProvider()


class TestTicketingService:
    """Cover uncovered lines 87-89, 122 in service.py."""

    async def test_prepare_listing_from_screenshot(self):
        from src.modules.ticketing.service import TicketingService
        mock_recognizer = AsyncMock()
        mock_provider = AsyncMock()
        selection = TicketSelection(
            cinema="万达影城", showtime="19:00", seat="A1", count=2, confidence=0.9
        )
        quote = TicketQuote(
            provider="static", face_value=50.0, channel_price=45.0,
            seat_premium=0.0, service_fee=0.0, final_price=45.0,
        )
        mock_recognizer.recognize = AsyncMock(return_value=selection)
        mock_provider.quote_ticket = AsyncMock(return_value=quote)

        svc = TicketingService(recognizer=mock_recognizer, provider=mock_provider)
        sel, q, draft = await svc.prepare_listing_from_screenshot(b"img_data")
        assert draft.title.startswith("万达影城")
        assert draft.price > 0

    async def test_compose_post_purchase_reply(self):
        from src.modules.ticketing.service import TicketingService
        mock_recognizer = AsyncMock()
        mock_provider = AsyncMock()
        svc = TicketingService(recognizer=mock_recognizer, provider=mock_provider)
        result = TicketPurchaseResult(success=True, provider="static", ticket_code="T123")
        reply = await svc.compose_post_purchase_reply(result)
        assert "T123" in reply

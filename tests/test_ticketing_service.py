"""Tests for the ticketing module skeleton."""

import asyncio

from src.modules.ticketing import RegexTicketRecognizer, StaticTicketProvider, TicketPricingPolicy, TicketingService


def test_ticketing_flow_builds_listing_and_purchase() -> None:
    text = (
        "影院：万达影城五角场店\n"
        "场次：2026-03-05 19:30\n"
        "座位：5排6座、5排7座\n"
    )

    recognizer = RegexTicketRecognizer()
    provider = StaticTicketProvider(provider_name="maoyan", default_face_value=39.9, default_channel_price=35.0)
    pricing = TicketPricingPolicy(fixed_markup=4.0, percentage_markup=0.1, default_service_fee=2.0)
    service = TicketingService(recognizer=recognizer, provider=provider, pricing=pricing)

    selection = asyncio.run(service.recognize(text.encode("utf-8")))
    quote = asyncio.run(service.quote(selection))
    draft = service.build_listing_draft(selection, quote)
    purchase = asyncio.run(service.fulfill_order(order_id="ORDER123", selection=selection, quote=quote))

    assert selection.cinema == "万达影城五角场店"
    assert selection.count == 2
    assert quote.provider == "maoyan"
    assert quote.final_price == 45.4
    assert "代买代订" in draft.title
    assert draft.price == quote.final_price
    assert purchase.success is True
    assert purchase.ticket_code == "TICKET-ORDER123"


def test_ticketing_two_stage_reply_uses_structured_output() -> None:
    text = (
        "影院：万达影城五角场店\n"
        "场次：2026-03-05 19:30\n"
        "座位：5排6座、5排7座\n"
    )
    service = TicketingService(
        recognizer=RegexTicketRecognizer(),
        provider=StaticTicketProvider(provider_name="maoyan", default_face_value=39.9, default_channel_price=35.0),
        pricing=TicketPricingPolicy(fixed_markup=4.0, percentage_markup=0.1, default_service_fee=2.0),
        review_confidence_threshold=0.9,
    )

    decision = asyncio.run(service.analyze_and_reply(text.encode("utf-8")))

    assert decision.selection.intent == "ticket_booking"
    assert decision.needs_manual_review is False
    assert "当前报价" in decision.reply_text
    assert "自由发挥" not in decision.reply_text


def test_ticketing_two_stage_reply_falls_back_to_manual_review_when_confidence_low() -> None:
    service = TicketingService(
        recognizer=RegexTicketRecognizer(),
        provider=StaticTicketProvider(provider_name="maoyan", default_face_value=39.9, default_channel_price=35.0),
        pricing=TicketPricingPolicy(),
        review_confidence_threshold=0.99,
    )
    selection = asyncio.run(service.recognize("影院：万达影城\n场次：2026-03-05 19:30\n座位：5排6座\n".encode("utf-8")))

    assert service.needs_manual_review(selection) is True

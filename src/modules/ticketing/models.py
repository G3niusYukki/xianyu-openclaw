"""Ticketing domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TicketSelection:
    """Structured ticket request extracted from a screenshot."""

    cinema: str
    showtime: str
    seat: str
    count: int
    intent: str = "ticket_booking"
    confidence: float = 0.0
    raw_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TicketQuote:
    """Quoted sale price for a ticket request."""

    provider: str
    face_value: float
    channel_price: float
    seat_premium: float
    service_fee: float
    final_price: float
    currency: str = "CNY"
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TicketListingDraft:
    """Draft listing content to be published on Xianyu."""

    title: str
    description: str
    price: float
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TicketPurchaseRequest:
    """Purchase request sent to an upstream ticket provider."""

    order_id: str
    selection: TicketSelection
    quote: TicketQuote
    buyer_requirements: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TicketPurchaseResult:
    """Result returned by an upstream ticket provider."""

    success: bool
    provider: str
    reservation_id: str = ""
    ticket_code: str = ""
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

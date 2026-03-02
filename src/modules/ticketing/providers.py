"""Upstream ticketing provider abstractions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models import TicketPurchaseRequest, TicketPurchaseResult, TicketQuote, TicketSelection


class TicketingProviderError(RuntimeError):
    """Raised when the upstream provider cannot serve the request."""


class ITicketProvider(ABC):
    """Provider interface for upstream quoting and purchasing."""

    @abstractmethod
    async def quote_ticket(self, selection: TicketSelection) -> TicketQuote:
        pass

    @abstractmethod
    async def create_purchase(self, request: TicketPurchaseRequest) -> TicketPurchaseResult:
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        pass


class StaticTicketProvider(ITicketProvider):
    """Deterministic provider useful for dry-run flows and tests."""

    def __init__(
        self,
        *,
        provider_name: str = "static",
        default_face_value: float = 0.0,
        default_channel_price: float = 0.0,
        per_cinema_channel_price: dict[str, float] | None = None,
    ) -> None:
        self.provider_name = str(provider_name or "static").strip()
        self.default_face_value = float(default_face_value)
        self.default_channel_price = float(default_channel_price)
        self.per_cinema_channel_price = {str(k): float(v) for k, v in (per_cinema_channel_price or {}).items()}

    async def quote_ticket(self, selection: TicketSelection) -> TicketQuote:
        channel_price = self.per_cinema_channel_price.get(selection.cinema, self.default_channel_price)
        face_value = self.default_face_value or channel_price
        return TicketQuote(
            provider=self.provider_name,
            face_value=round(face_value, 2),
            channel_price=round(channel_price, 2),
            seat_premium=0.0,
            service_fee=0.0,
            final_price=round(channel_price, 2),
            details={"source": "static_provider"},
        )

    async def create_purchase(self, request: TicketPurchaseRequest) -> TicketPurchaseResult:
        code = f"TICKET-{request.order_id}"
        return TicketPurchaseResult(
            success=True,
            provider=self.provider_name,
            reservation_id=f"RES-{request.order_id}",
            ticket_code=code,
            message="Purchase simulated successfully",
            payload={
                "selection": {
                    "cinema": request.selection.cinema,
                    "showtime": request.selection.showtime,
                    "seat": request.selection.seat,
                    "count": request.selection.count,
                },
                "quoted_price": request.quote.final_price,
            },
        )

    async def health_check(self) -> bool:
        return True

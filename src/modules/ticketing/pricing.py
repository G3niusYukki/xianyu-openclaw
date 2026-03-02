"""Ticketing pricing policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import TicketQuote, TicketSelection


@dataclass(slots=True)
class TicketPricingPolicy:
    """Transforms an upstream quote into a sale price."""

    fixed_markup: float = 0.0
    percentage_markup: float = 0.0
    default_service_fee: float = 0.0
    seat_premium_rules: dict[str, float] = field(default_factory=dict)

    def quote(self, selection: TicketSelection, upstream_quote: TicketQuote) -> TicketQuote:
        seat_premium = self._resolve_seat_premium(selection.seat)
        channel_price = float(upstream_quote.channel_price)
        base_price = max(channel_price, float(upstream_quote.face_value or 0.0))
        marked_up = base_price + self.fixed_markup + (channel_price * self.percentage_markup)
        final_price = round(marked_up + self.default_service_fee + seat_premium, 2)

        details = dict(upstream_quote.details)
        details.update(
            {
                "fixed_markup": self.fixed_markup,
                "percentage_markup": self.percentage_markup,
                "seat_premium_rule_hit": seat_premium > 0,
            }
        )

        return TicketQuote(
            provider=upstream_quote.provider,
            face_value=round(float(upstream_quote.face_value), 2),
            channel_price=round(channel_price, 2),
            seat_premium=round(seat_premium, 2),
            service_fee=round(self.default_service_fee, 2),
            final_price=final_price,
            currency=upstream_quote.currency,
            details=details,
        )

    def _resolve_seat_premium(self, seat: str) -> float:
        normalized = str(seat or "").upper()
        for prefix, premium in self.seat_premium_rules.items():
            if normalized.startswith(str(prefix).upper()):
                return float(premium)
        return 0.0

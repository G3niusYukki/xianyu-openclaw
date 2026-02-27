"""
自动报价数据模型
Quote Models
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class QuoteRequest:
    """报价请求参数。"""

    destination_city: str | None = None
    weight_kg: float | None = None
    pieces: int = 1
    urgency: bool = False
    origin_city: str | None = None
    raw_message: str = ""


@dataclass(slots=True)
class QuoteParseResult:
    """询价解析结果。"""

    is_quote_intent: bool
    request: QuoteRequest
    missing_fields: list[str] = field(default_factory=list)


@dataclass(slots=True)
class QuoteResult:
    """报价结果。"""

    total_fee: float
    base_fee: float
    additional_fee: float
    service_fee: float
    eta_minutes: int
    currency: str = "CNY"
    provider: str = "rule_engine"
    confidence: float = 0.9
    valid_minutes: int = 15
    explain: str = ""

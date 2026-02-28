"""自动报价领域模型。"""

from dataclasses import dataclass, field
import re
from typing import Any

DEFAULT_QUOTE_REPLY_TEMPLATE = (
    "您好，{origin} 到 {destination}，预估报价 ¥{price}（{price_breakdown}）。"
    "预计时效约 {eta_days}。"
)


@dataclass(slots=True)
class QuoteRequest:
    """报价请求。"""

    origin: str
    destination: str
    weight: float
    volume: float = 0.0
    volume_weight: float = 0.0
    service_level: str = "standard"
    courier: str = "auto"
    item_type: str = "general"
    time_window: str = "normal"

    def cache_key(self) -> str:
        weight_bucket = round(self.weight * 2) / 2
        volume_bucket = round(float(self.volume or 0.0) / 500.0) * 500
        volume_weight_bucket = round(float(self.volume_weight or 0.0) * 2) / 2
        return (
            f"{self.origin}|{self.destination}|{self.courier}|{weight_bucket:.1f}|"
            f"{volume_bucket:.0f}|{volume_weight_bucket:.1f}|{self.service_level}"
        ).lower()


@dataclass(slots=True)
class QuoteResult:
    """报价结果。"""

    provider: str
    base_fee: float
    surcharges: dict[str, float] = field(default_factory=dict)
    total_fee: float = 0.0
    currency: str = "CNY"
    eta_minutes: int = 0
    confidence: float = 0.8
    explain: dict[str, Any] = field(default_factory=dict)
    fallback_used: bool = False
    cache_hit: bool = False
    stale: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "base_fee": round(self.base_fee, 2),
            "surcharges": {k: round(v, 2) for k, v in self.surcharges.items()},
            "total_fee": round(self.total_fee, 2),
            "currency": self.currency,
            "eta_minutes": self.eta_minutes,
            "confidence": round(self.confidence, 3),
            "explain": self.explain,
            "fallback_used": self.fallback_used,
            "cache_hit": self.cache_hit,
            "stale": self.stale,
        }

    @staticmethod
    def _format_days_from_minutes(minutes: int | float | None) -> str:
        raw = float(minutes or 0)
        if raw <= 0:
            return "1天"
        days = max(1.0, raw / 1440.0)
        rounded = round(days, 1)
        if abs(rounded - round(rounded)) < 1e-9:
            return f"{int(round(rounded))}天"
        return f"{rounded:.1f}天"

    @staticmethod
    def _strip_validity_clause(text: str) -> str:
        cleaned = re.sub(r"[，,]?\s*报价有效期\s*\d+\s*分钟[。.]?", "", str(text or ""))
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        if cleaned and cleaned[-1] not in "。！？!?":
            cleaned = f"{cleaned}。"
        return cleaned

    def compose_reply(self, validity_minutes: int = 30, template: str | None = None) -> str:
        parts = " + ".join([f"{name} ¥{value:.2f}" for name, value in self.surcharges.items()])
        price_breakdown = f"基础运费 ¥{self.base_fee:.2f}"
        if parts:
            price_breakdown = f"{price_breakdown} + {parts}"

        explain = self.explain if isinstance(self.explain, dict) else {}
        origin = str(explain.get("matched_origin") or explain.get("normalized_origin") or "寄件地")
        destination = str(explain.get("matched_destination") or explain.get("normalized_destination") or "收件地")
        courier = str(explain.get("matched_courier") or explain.get("courier") or "当前渠道")
        divisor = explain.get("volume_divisor")
        volume_formula = f"体积(cm³)/{int(divisor)}" if isinstance(divisor, (int, float)) and divisor else "体积重规则"
        eta_days = self._format_days_from_minutes(self.eta_minutes)
        tpl = str(template or DEFAULT_QUOTE_REPLY_TEMPLATE)
        try:
            rendered = tpl.format(
                origin=origin,
                destination=destination,
                weight=explain.get("actual_weight_kg", ""),
                billing_weight=explain.get("billing_weight_kg", ""),
                courier=courier,
                price=f"{self.total_fee:.2f}",
                currency=self.currency,
                price_breakdown=price_breakdown,
                eta_days=eta_days,
                validity_minutes=int(validity_minutes),
                volume_formula=volume_formula,
            )
            return self._strip_validity_clause(rendered)
        except Exception:
            # 模板异常时保底返回标准文案，避免中断自动回复链路
            fallback = (
                f"您好，{origin} 到 {destination}，预估报价 ¥{self.total_fee:.2f}（{price_breakdown}）。"
                f"预计时效约 {eta_days}。"
            )
            return self._strip_validity_clause(fallback)

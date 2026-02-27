"""自动报价领域模型。"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class QuoteRequest:
    """报价请求。"""

    origin: str
    destination: str
    weight: float
    volume: float = 0.0
    service_level: str = "standard"
    courier: str = "auto"
    item_type: str = "general"
    time_window: str = "normal"

    def cache_key(self) -> str:
        weight_bucket = round(self.weight * 2) / 2
        return (f"{self.origin}|{self.destination}|{self.courier}|{weight_bucket:.1f}|{self.service_level}").lower()


@dataclass(slots=True)
class QuoteSnapshot:
    """报价快照：成本来源与规则版本追溯。"""

    cost_source: str = ""
    cost_version: str = ""
    pricing_rule_version: str = "v1"
    latency_ms: int = 0
    provider_chain: list[str] = field(default_factory=list)
    fallback_reason: str = ""


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
    snapshot: QuoteSnapshot | None = None

    def to_dict(self) -> dict[str, Any]:
        snapshot_data = None
        if self.snapshot:
            snapshot_data = {
                "cost_source": self.snapshot.cost_source,
                "cost_version": self.snapshot.cost_version,
                "pricing_rule_version": self.snapshot.pricing_rule_version,
                "latency_ms": self.snapshot.latency_ms,
                "provider_chain": self.snapshot.provider_chain,
                "fallback_reason": self.snapshot.fallback_reason,
            }
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
            "snapshot": snapshot_data,
        }

    def compose_reply(self, validity_minutes: int = 30) -> str:
        parts = " + ".join([f"{name} ¥{value:.2f}" for name, value in self.surcharges.items()])
        split_text = f"基础运费 ¥{self.base_fee:.2f}"
        if parts:
            split_text = f"{split_text} + {parts}"
        return (
            f"为您预估报价：{self.total_fee:.2f} {self.currency}（{split_text}）。"
            f"预计时效约 {self.eta_minutes} 分钟，报价有效期 {validity_minutes} 分钟。"
        )

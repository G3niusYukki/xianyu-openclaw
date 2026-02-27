"""自动报价 provider 适配层。"""

import asyncio
import random
from abc import ABC, abstractmethod

from src.modules.quote.models import QuoteRequest, QuoteResult


class QuoteProviderError(RuntimeError):
    """报价 provider 错误。"""


class IQuoteProvider(ABC):
    """报价 provider 接口。"""

    @abstractmethod
    async def get_quote(self, request: QuoteRequest, timeout_ms: int = 3000) -> QuoteResult:
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        pass


class RuleTableQuoteProvider(IQuoteProvider):
    """本地规则表报价 provider。"""

    def __init__(self) -> None:
        self.remote_area_keywords = {"西藏", "新疆", "青海", "内蒙古", "甘肃", "宁夏", "海南", "偏远"}

    async def get_quote(self, request: QuoteRequest, timeout_ms: int = 3000) -> QuoteResult:
        service_level = request.service_level.lower()
        base_table = {
            "standard": 8.0,
            "express": 12.0,
            "urgent": 18.0,
        }
        eta_table = {
            "standard": 48 * 60,
            "express": 24 * 60,
            "urgent": 12 * 60,
        }

        base_fee = base_table.get(service_level, 8.0)
        eta_minutes = eta_table.get(service_level, 48 * 60)

        same_city = request.origin.strip() == request.destination.strip()
        distance_fee = 0.0 if same_city else 4.0
        if request.origin[:2] != request.destination[:2] and not same_city:
            distance_fee += 3.0

        extra_weight = max(0.0, request.weight - 1.0)
        weight_fee = extra_weight * 2.0

        remote_fee = 0.0
        text = f"{request.origin}{request.destination}"
        if any(keyword in text for keyword in self.remote_area_keywords):
            remote_fee = 8.0
            eta_minutes += 24 * 60

        surcharges = {
            "distance": distance_fee,
            "weight": weight_fee,
        }
        if remote_fee > 0:
            surcharges["remote"] = remote_fee

        total = base_fee + sum(surcharges.values())
        return QuoteResult(
            provider="rule_table",
            base_fee=base_fee,
            surcharges=surcharges,
            total_fee=round(total, 2),
            eta_minutes=eta_minutes,
            confidence=0.88,
            explain={
                "service_level": service_level,
                "same_city": same_city,
                "weight_kg": request.weight,
            },
        )

    async def health_check(self) -> bool:
        return True


class RemoteQuoteProvider(IQuoteProvider):
    """外部运价 provider 占位实现（mock）。"""

    def __init__(
        self,
        *,
        enabled: bool = True,
        simulated_latency_ms: int = 120,
        failure_rate: float = 0.0,
    ):
        self.enabled = enabled
        self.simulated_latency_ms = max(0, simulated_latency_ms)
        self.failure_rate = min(max(failure_rate, 0.0), 1.0)

    async def get_quote(self, request: QuoteRequest, timeout_ms: int = 3000) -> QuoteResult:
        if not self.enabled:
            raise QuoteProviderError("Remote provider disabled")

        budget_ms = max(50, timeout_ms)
        await asyncio.sleep(min(self.simulated_latency_ms, budget_ms) / 1000)

        if self.simulated_latency_ms > budget_ms:
            raise QuoteProviderError("Remote provider timeout")
        if random.random() < self.failure_rate:
            raise QuoteProviderError("Remote provider temporary failure")

        base_fee = 10.0 if request.service_level != "urgent" else 16.0
        dynamic = (request.weight * 2.2) + (0 if request.origin == request.destination else 3.5)
        fuel = round((base_fee + dynamic) * 0.08, 2)
        total = round(base_fee + dynamic + fuel, 2)
        eta = 16 * 60 if request.service_level == "express" else 30 * 60

        return QuoteResult(
            provider="remote_mock",
            base_fee=round(base_fee, 2),
            surcharges={"dynamic": round(dynamic, 2), "fuel": fuel},
            total_fee=total,
            eta_minutes=eta,
            confidence=0.93,
            explain={
                "source": "remote_mock",
                "origin": request.origin,
                "destination": request.destination,
                "weight_kg": request.weight,
            },
        )

    async def health_check(self) -> bool:
        return self.enabled

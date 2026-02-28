"""自动报价 provider 适配层。"""

from __future__ import annotations

import asyncio
import os
import random
from abc import ABC, abstractmethod
from typing import Any

import httpx

from src.modules.quote.cost_table import CostTableRepository, normalize_courier_name
from src.modules.quote.models import QuoteRequest, QuoteResult

DEFAULT_MARKUP_RULE: dict[str, float] = {
    "normal_first_add": 0.50,
    "member_first_add": 0.25,
    "normal_extra_add": 0.50,
    "member_extra_add": 0.30,
}


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

    def __init__(self, *, volume_divisor_default: float = 6000.0) -> None:
        self.remote_area_keywords = {"西藏", "新疆", "青海", "内蒙古", "甘肃", "宁夏", "海南", "偏远"}
        self.volume_divisor_default = float(volume_divisor_default or 6000.0)

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

        actual_weight = max(0.0, float(request.weight or 0.0))
        volume_weight = _derive_volume_weight_kg(
            volume_cm3=float(request.volume or 0.0),
            explicit_volume_weight=float(request.volume_weight or 0.0),
            divisor=self.volume_divisor_default,
        )
        billing_weight = max(actual_weight, volume_weight)
        extra_weight = max(0.0, billing_weight - 1.0)
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
                "actual_weight_kg": round(actual_weight, 3),
                "volume_weight_kg": round(volume_weight, 3),
                "billing_weight_kg": round(billing_weight, 3),
                "volume_divisor": self.volume_divisor_default if self.volume_divisor_default > 0 else None,
            },
        )

    async def health_check(self) -> bool:
        return True


class CostTableMarkupQuoteProvider(IQuoteProvider):
    """成本表 + 加价规则 provider。"""

    def __init__(
        self,
        *,
        table_dir: str = "data/quote_costs",
        include_patterns: list[str] | None = None,
        markup_rules: dict[str, Any] | None = None,
        pricing_profile: str = "normal",
        volume_divisor_default: float | None = None,
    ):
        self.repo = CostTableRepository(table_dir=table_dir, include_patterns=include_patterns or ["*.xlsx", "*.csv"])
        self.pricing_profile = "member" if str(pricing_profile).strip().lower() == "member" else "normal"
        self.markup_rules = _normalize_markup_rules(markup_rules or {})
        self.volume_divisor_default = float(volume_divisor_default or 0.0) if volume_divisor_default else 0.0

    async def get_quote(self, request: QuoteRequest, timeout_ms: int = 3000) -> QuoteResult:
        requested_courier = _requested_courier(request.courier)
        candidates = self.repo.find_candidates(
            origin=request.origin,
            destination=request.destination,
            courier=requested_courier,
            limit=8,
        )
        if not candidates:
            raise QuoteProviderError(
                f"No matched cost table records for route: {request.origin}->{request.destination}"
            )

        row = candidates[0]
        markup = _resolve_markup(self.markup_rules, row.courier)
        first_add, extra_add = _profile_markup(markup, self.pricing_profile)

        actual_weight = max(0.0, float(request.weight))
        divisor = _first_positive(row.throw_ratio, self.volume_divisor_default)
        volume_weight = _derive_volume_weight_kg(
            volume_cm3=float(request.volume or 0.0),
            explicit_volume_weight=float(request.volume_weight or 0.0),
            divisor=divisor,
        )
        billing_weight = max(actual_weight, volume_weight)
        extra_weight = max(0.0, billing_weight - 1.0)
        sale_first = max(0.0, float(row.first_cost) + first_add)
        sale_extra = max(0.0, float(row.extra_cost) + extra_add)
        extra_fee = extra_weight * sale_extra

        surcharges: dict[str, float] = {}
        if extra_fee > 0:
            surcharges["续重"] = round(extra_fee, 2)

        return QuoteResult(
            provider="cost_table_markup",
            base_fee=round(sale_first, 2),
            surcharges=surcharges,
            total_fee=round(sale_first + extra_fee, 2),
            eta_minutes=_eta_by_service_level(request.service_level),
            confidence=0.92,
            explain={
                "pricing_profile": self.pricing_profile,
                "matched_courier": row.courier,
                "matched_origin": row.origin,
                "matched_destination": row.destination,
                "cost_first": row.first_cost,
                "cost_extra": row.extra_cost,
                "actual_weight_kg": round(actual_weight, 3),
                "billing_weight_kg": round(billing_weight, 3),
                "volume_cm3": round(float(request.volume or 0.0), 3),
                "volume_weight_kg": round(volume_weight, 3),
                "volume_divisor": divisor if divisor > 0 else None,
                "markup_first_add": first_add,
                "markup_extra_add": extra_add,
                "source_file": row.source_file,
                "source_sheet": row.source_sheet,
            },
        )

    async def health_check(self) -> bool:
        stats = self.repo.get_stats(max_files=10)
        return int(stats.get("total_records", 0)) > 0


class ApiCostMarkupQuoteProvider(IQuoteProvider):
    """API 成本价 + 加价规则 provider。"""

    def __init__(
        self,
        *,
        api_url: str = "",
        api_key_env: str = "QUOTE_COST_API_KEY",
        markup_rules: dict[str, Any] | None = None,
        pricing_profile: str = "normal",
        volume_divisor_default: float | None = None,
    ):
        self.api_url = str(api_url or "").strip()
        self.api_key_env = str(api_key_env or "").strip()
        self.markup_rules = _normalize_markup_rules(markup_rules or {})
        self.pricing_profile = "member" if str(pricing_profile).strip().lower() == "member" else "normal"
        self.volume_divisor_default = float(volume_divisor_default or 0.0) if volume_divisor_default else 0.0

    async def get_quote(self, request: QuoteRequest, timeout_ms: int = 3000) -> QuoteResult:
        if not self.api_url:
            raise QuoteProviderError("cost_api_url is empty")

        headers = {"Content-Type": "application/json"}
        api_key = os.getenv(self.api_key_env, "").strip() if self.api_key_env else ""
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            headers["X-API-Key"] = api_key

        payload = {
            "origin": request.origin,
            "destination": request.destination,
            "weight": request.weight,
            "volume": request.volume,
            "courier": request.courier,
            "service_level": request.service_level,
            "item_type": request.item_type,
            "time_window": request.time_window,
        }

        timeout_seconds = max(0.2, float(timeout_ms) / 1000.0)
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(self.api_url, json=payload, headers=headers)
        except Exception as exc:
            raise QuoteProviderError(f"Remote cost api request failed: {exc}") from exc

        if response.status_code >= 400:
            raise QuoteProviderError(f"Remote cost api http {response.status_code}")

        try:
            body = response.json()
        except Exception as exc:
            raise QuoteProviderError(f"Remote cost api invalid json: {exc}") from exc

        parsed = _parse_cost_api_response(body)
        courier = normalize_courier_name(parsed.get("courier") or request.courier)
        first_cost = _to_float(parsed.get("first_cost"))
        extra_cost = _to_float(parsed.get("extra_cost"))
        total_cost = _to_float(parsed.get("total_cost"))

        if first_cost is None and total_cost is None:
            raise QuoteProviderError("Remote cost api missing first_cost/total_cost")

        volume_weight = _derive_volume_weight_kg(
            volume_cm3=float(request.volume or 0.0),
            explicit_volume_weight=float(request.volume_weight or 0.0),
            divisor=self.volume_divisor_default,
        )
        api_billable_weight = _to_float(parsed.get("billable_weight"))
        billing_weight = max(
            float(request.weight or 0.0),
            float(api_billable_weight or 0.0),
            float(volume_weight or 0.0),
        )
        extra_weight = max(0.0, billing_weight - 1.0)
        if first_cost is None:
            first_cost = max(0.0, float(total_cost or 0.0) - (extra_weight * float(extra_cost or 0.0)))
        if extra_cost is None:
            extra_cost = 0.0

        markup = _resolve_markup(self.markup_rules, courier)
        first_add, extra_add = _profile_markup(markup, self.pricing_profile)

        sale_first = max(0.0, first_cost + first_add)
        sale_extra = max(0.0, extra_cost + extra_add)
        extra_fee = extra_weight * sale_extra
        surcharges: dict[str, float] = {}
        if extra_fee > 0:
            surcharges["续重"] = round(extra_fee, 2)

        provider_name = str(parsed.get("provider") or "api_cost_markup")
        return QuoteResult(
            provider=provider_name,
            base_fee=round(sale_first, 2),
            surcharges=surcharges,
            total_fee=round(sale_first + extra_fee, 2),
            eta_minutes=int(parsed.get("eta_minutes") or _eta_by_service_level(request.service_level)),
            confidence=float(parsed.get("confidence") or 0.93),
            explain={
                "pricing_profile": self.pricing_profile,
                "api_url": self.api_url,
                "cost_first": first_cost,
                "cost_extra": extra_cost,
                "cost_total_raw": total_cost,
                "actual_weight_kg": round(float(request.weight or 0.0), 3),
                "billing_weight_kg": round(billing_weight, 3),
                "volume_cm3": round(float(request.volume or 0.0), 3),
                "volume_weight_kg": round(volume_weight, 3),
                "api_billable_weight_kg": api_billable_weight,
                "volume_divisor": self.volume_divisor_default if self.volume_divisor_default > 0 else None,
                "markup_first_add": first_add,
                "markup_extra_add": extra_add,
                "api_provider": provider_name,
            },
        )

    async def health_check(self) -> bool:
        return bool(self.api_url)


class RemoteQuoteProvider(IQuoteProvider):
    """外部运价 provider 占位实现（mock）。"""

    def __init__(
        self,
        *,
        enabled: bool = True,
        simulated_latency_ms: int = 120,
        failure_rate: float = 0.0,
        volume_divisor_default: float = 6000.0,
    ):
        self.enabled = enabled
        self.simulated_latency_ms = max(0, simulated_latency_ms)
        self.failure_rate = min(max(failure_rate, 0.0), 1.0)
        self.volume_divisor_default = float(volume_divisor_default or 6000.0)

    async def get_quote(self, request: QuoteRequest, timeout_ms: int = 3000) -> QuoteResult:
        if not self.enabled:
            raise QuoteProviderError("Remote provider disabled")

        budget_ms = max(50, timeout_ms)
        await asyncio.sleep(min(self.simulated_latency_ms, budget_ms) / 1000)

        if self.simulated_latency_ms > budget_ms:
            raise QuoteProviderError("Remote provider timeout")
        if random.random() < self.failure_rate:
            raise QuoteProviderError("Remote provider temporary failure")

        actual_weight = max(0.0, float(request.weight or 0.0))
        volume_weight = _derive_volume_weight_kg(
            volume_cm3=float(request.volume or 0.0),
            explicit_volume_weight=float(request.volume_weight or 0.0),
            divisor=self.volume_divisor_default,
        )
        billing_weight = max(actual_weight, volume_weight)

        base_fee = 10.0 if request.service_level != "urgent" else 16.0
        dynamic = (billing_weight * 2.2) + (0 if request.origin == request.destination else 3.5)
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
                "actual_weight_kg": round(actual_weight, 3),
                "volume_weight_kg": round(volume_weight, 3),
                "billing_weight_kg": round(billing_weight, 3),
                "volume_divisor": self.volume_divisor_default if self.volume_divisor_default > 0 else None,
            },
        )

    async def health_check(self) -> bool:
        return self.enabled


def _requested_courier(courier: str | None) -> str | None:
    text = str(courier or "").strip()
    if not text or text.lower() == "auto":
        return None
    return text


def _normalize_markup_rules(raw_rules: dict[str, Any]) -> dict[str, dict[str, float]]:
    rules: dict[str, dict[str, float]] = {"default": dict(DEFAULT_MARKUP_RULE)}
    if not isinstance(raw_rules, dict):
        return rules

    for key, value in raw_rules.items():
        if not isinstance(value, dict):
            continue
        courier_key = normalize_courier_name(str(key).strip()) if str(key).strip() else "default"
        target = dict(DEFAULT_MARKUP_RULE)
        for field_name in DEFAULT_MARKUP_RULE:
            if field_name in value:
                target[field_name] = float(value[field_name])
        rules[courier_key or "default"] = target

    if "default" not in rules:
        rules["default"] = dict(DEFAULT_MARKUP_RULE)
    return rules


def _resolve_markup(markup_rules: dict[str, dict[str, float]], courier: str | None) -> dict[str, float]:
    normalized = normalize_courier_name(courier)
    if normalized in markup_rules:
        return markup_rules[normalized]
    return markup_rules.get("default", dict(DEFAULT_MARKUP_RULE))


def _profile_markup(markup: dict[str, float], pricing_profile: str) -> tuple[float, float]:
    profile = str(pricing_profile or "normal").strip().lower()
    if profile == "member":
        return float(markup.get("member_first_add", 0.0)), float(markup.get("member_extra_add", 0.0))
    return float(markup.get("normal_first_add", 0.0)), float(markup.get("normal_extra_add", 0.0))


def _eta_by_service_level(service_level: str) -> int:
    text = str(service_level or "").strip().lower()
    if text == "urgent":
        return 12 * 60
    if text == "express":
        return 24 * 60
    return 48 * 60


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        return None


def _parse_cost_api_response(data: Any) -> dict[str, Any]:
    if isinstance(data, dict):
        payload = data.get("data") if isinstance(data.get("data"), dict) else data
    elif isinstance(data, list) and data:
        payload = data[0] if isinstance(data[0], dict) else {}
    else:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    return {
        "provider": payload.get("provider") or payload.get("source"),
        "courier": payload.get("courier") or payload.get("carrier"),
        "first_cost": payload.get("first_cost")
        or payload.get("first_price")
        or payload.get("base_fee")
        or payload.get("base_price"),
        "extra_cost": payload.get("extra_cost")
        or payload.get("continue_cost")
        or payload.get("extra_price")
        or payload.get("续重"),
        "total_cost": payload.get("total_cost") or payload.get("total_fee") or payload.get("price"),
        "billable_weight": payload.get("billable_weight")
        or payload.get("chargeable_weight")
        or payload.get("计费重")
        or payload.get("weight_billable"),
        "eta_minutes": payload.get("eta_minutes") or payload.get("eta"),
        "confidence": payload.get("confidence"),
    }


def _first_positive(*values: Any) -> float:
    for value in values:
        v = _to_float(value)
        if v is not None and v > 0:
            return float(v)
    return 0.0


def _derive_volume_weight_kg(volume_cm3: float, explicit_volume_weight: float, divisor: float) -> float:
    explicit = _to_float(explicit_volume_weight)
    if explicit is not None and explicit > 0:
        return float(explicit)
    volume = _to_float(volume_cm3)
    div = _to_float(divisor)
    if volume is None or volume <= 0 or div is None or div <= 0:
        return 0.0
    return round(float(volume) / float(div), 3)

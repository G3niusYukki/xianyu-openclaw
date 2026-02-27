"""自动报价引擎。"""

import asyncio
import time
from copy import deepcopy
from typing import Any

from src.core.logger import get_logger
from src.modules.analytics.service import AnalyticsService
from src.modules.quote.cache import QuoteCache
from src.modules.quote.models import QuoteRequest, QuoteResult
from src.modules.quote.providers import IQuoteProvider, QuoteProviderError, RemoteQuoteProvider, RuleTableQuoteProvider
from src.modules.quote.route import normalize_request_route


class AutoQuoteEngine:
    """自动报价引擎，支持 provider 适配层、缓存与回退。"""

    def __init__(self, config: dict[str, Any] | None = None):
        cfg = config or {}
        providers_cfg = cfg.get("providers", {})

        self.logger = get_logger()
        self.enabled = bool(cfg.get("enabled", True))
        self.mode = str(cfg.get("mode", "rule_only")).lower()
        self.timeout_ms = int(cfg.get("timeout_ms", 3000))
        self.retry_times = int(cfg.get("retry_times", 1))
        self.safety_margin = float(cfg.get("safety_margin", 0.0))
        self.validity_minutes = int(cfg.get("validity_minutes", 30))
        self.circuit_fail_threshold = int(cfg.get("circuit_fail_threshold", 3))
        self.circuit_open_seconds = int(cfg.get("circuit_open_seconds", 30))
        self._remote_failures = 0
        self._circuit_open_until = 0.0

        self.rule_provider: IQuoteProvider = RuleTableQuoteProvider()
        self.remote_provider: IQuoteProvider = RemoteQuoteProvider(
            enabled=bool(providers_cfg.get("remote", {}).get("enabled", False)),
            simulated_latency_ms=int(providers_cfg.get("remote", {}).get("simulated_latency_ms", 120)),
            failure_rate=float(providers_cfg.get("remote", {}).get("failure_rate", 0.0)),
        )

        self.cache = QuoteCache(
            ttl_seconds=int(cfg.get("ttl_seconds", 90)),
            max_stale_seconds=int(cfg.get("max_stale_seconds", 300)),
        )

        self._analytics: AnalyticsService | None = None
        self._analytics_enabled = bool(cfg.get("analytics_log_enabled", True))

    async def get_quote(self, request: QuoteRequest) -> QuoteResult:
        if not self.enabled:
            raise QuoteProviderError("Quote engine is disabled")

        normalized_request = normalize_request_route(request)
        key = normalized_request.cache_key()
        cached, fresh_hit, stale_hit = self.cache.get(key)
        if cached and fresh_hit:
            return deepcopy(cached)

        if stale_hit and cached:
            asyncio.create_task(self._refresh_cache_in_background(normalized_request, key))
            return deepcopy(cached)

        start = time.perf_counter()
        result = await self._quote_with_fallback(normalized_request)
        result.total_fee = round(result.total_fee * (1 + self.safety_margin), 2)
        result.explain = {
            **result.explain,
            "normalized_origin": normalized_request.origin,
            "normalized_destination": normalized_request.destination,
            "courier": normalized_request.courier,
        }
        self.cache.set(key, result)

        await self._log_quote(normalized_request, result, latency_ms=int((time.perf_counter() - start) * 1000))
        return deepcopy(result)

    async def _quote_with_fallback(self, request: QuoteRequest) -> QuoteResult:
        if self.mode == "rule_only":
            return await self.rule_provider.get_quote(request, timeout_ms=self.timeout_ms)

        if self._is_circuit_open():
            remote_error: Exception | None = QuoteProviderError("remote_circuit_open")
            return await self._fallback_quote(request, remote_error)

        remote_error: Exception | None = None
        for _ in range(max(1, self.retry_times)):
            try:
                result = await self.remote_provider.get_quote(request, timeout_ms=self.timeout_ms)
                self._remote_failures = 0
                self._circuit_open_until = 0.0
                return result
            except Exception as exc:
                remote_error = exc
                self._remote_failures += 1
                if self._remote_failures >= self.circuit_fail_threshold:
                    self._circuit_open_until = time.time() + self.circuit_open_seconds

        return await self._fallback_quote(request, remote_error)

    async def _fallback_quote(self, request: QuoteRequest, remote_error: Exception | None) -> QuoteResult:
        try:
            fallback = await self.rule_provider.get_quote(request, timeout_ms=self.timeout_ms)
            fallback.fallback_used = True
            fallback.explain = {
                **fallback.explain,
                "fallback_reason": str(remote_error) if remote_error else "provider_unavailable",
                "failure_class": self._classify_failure(remote_error),
            }
            return fallback
        except Exception as rule_exc:
            raise QuoteProviderError(f"Quote failed: remote={remote_error}, rule={rule_exc}") from rule_exc

    def _is_circuit_open(self) -> bool:
        return self._circuit_open_until > time.time()

    @staticmethod
    def _classify_failure(error: Exception | None) -> str:
        if error is None:
            return "unknown"
        text = str(error).lower()
        if "timeout" in text:
            return "timeout"
        if "disabled" in text or "circuit" in text:
            return "unavailable"
        if "temporary" in text:
            return "transient"
        return "provider_error"

    async def _refresh_cache_in_background(self, request: QuoteRequest, key: str) -> None:
        try:
            latest = await self._quote_with_fallback(request)
            latest.total_fee = round(latest.total_fee * (1 + self.safety_margin), 2)
            latest.cache_hit = False
            latest.stale = False
            self.cache.set(key, latest)
        except Exception as exc:  # pragma: no cover - defensive path
            self.logger.warning(f"Quote background refresh failed: {exc}")

    async def _log_quote(self, request: QuoteRequest, result: QuoteResult, latency_ms: int) -> None:
        if not self._analytics_enabled:
            return

        try:
            if self._analytics is None:
                self._analytics = AnalyticsService()
            await self._analytics.log_operation(
                operation_type="quote",
                details={
                    "request": {
                        "origin": request.origin,
                        "destination": request.destination,
                        "weight": request.weight,
                        "service_level": request.service_level,
                    },
                    "result": result.to_dict(),
                    "latency_ms": latency_ms,
                },
                status="success",
            )
        except Exception as exc:
            self.logger.warning(f"Quote log failed: {exc}")

    async def health_check(self) -> dict[str, bool]:
        return {
            "rule_provider": await self.rule_provider.health_check(),
            "remote_provider": await self.remote_provider.health_check(),
        }

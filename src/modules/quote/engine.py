"""自动报价引擎。"""

import asyncio
import contextlib
import time
from copy import deepcopy
from typing import Any

from src.core.logger import get_logger
from src.modules.analytics.service import AnalyticsService
from src.modules.quote.cache import QuoteCache
from src.modules.quote.models import QuoteRequest, QuoteResult
from src.modules.quote.providers import (
    ApiCostMarkupQuoteProvider,
    CostTableMarkupQuoteProvider,
    IQuoteProvider,
    QuoteProviderError,
    RemoteQuoteProvider,
    RuleTableQuoteProvider,
)
from src.modules.quote.route import normalize_request_route


class AutoQuoteEngine:
    """自动报价引擎，支持 provider 适配层、缓存与回退。"""

    def __init__(self, config: dict[str, Any] | None = None):
        cfg = config or {}
        providers_cfg = cfg.get("providers", {})

        self.logger = get_logger()
        self.enabled = bool(cfg.get("enabled", True))
        self.mode = self._normalize_mode(str(cfg.get("mode", "rule_only")).lower())
        self.timeout_ms = int(cfg.get("timeout_ms", 3000))
        self.retry_times = int(cfg.get("retry_times", 1))
        self.safety_margin = float(cfg.get("safety_margin", 0.0))
        self.validity_minutes = int(cfg.get("validity_minutes", 30))
        self.circuit_fail_threshold = int(cfg.get("circuit_fail_threshold", 3))
        self.circuit_open_seconds = int(cfg.get("circuit_open_seconds", 30))
        self.api_fallback_to_table_parallel = bool(cfg.get("api_fallback_to_table_parallel", True))
        self.api_prefer_max_wait_seconds = max(0.05, float(cfg.get("api_prefer_max_wait_seconds", 1.2)))
        self.volume_divisor_default = float(cfg.get("volume_divisor_default", 6000) or 6000)
        self._remote_failures = 0
        self._circuit_open_until = 0.0

        self.rule_provider: IQuoteProvider = RuleTableQuoteProvider(
            volume_divisor_default=self.volume_divisor_default
        )
        self.cost_table_provider: IQuoteProvider = CostTableMarkupQuoteProvider(
            table_dir=str(cfg.get("cost_table_dir", "data/quote_costs")),
            include_patterns=cfg.get("cost_table_patterns", ["*.xlsx", "*.csv"]),
            markup_rules=cfg.get("markup_rules", {}),
            pricing_profile=str(cfg.get("pricing_profile", "normal")),
            volume_divisor_default=self.volume_divisor_default,
        )
        self.api_cost_provider: IQuoteProvider = ApiCostMarkupQuoteProvider(
            api_url=str(cfg.get("cost_api_url", "")),
            api_key_env=self._resolve_api_key_env_name(cfg),
            markup_rules=cfg.get("markup_rules", {}),
            pricing_profile=str(cfg.get("pricing_profile", "normal")),
            volume_divisor_default=self.volume_divisor_default,
        )
        self.remote_provider: IQuoteProvider = RemoteQuoteProvider(
            enabled=bool(providers_cfg.get("remote", {}).get("enabled", False)),
            simulated_latency_ms=int(providers_cfg.get("remote", {}).get("simulated_latency_ms", 120)),
            failure_rate=float(providers_cfg.get("remote", {}).get("failure_rate", 0.0)),
            volume_divisor_default=self.volume_divisor_default,
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
        if self.mode == "cost_table_plus_markup":
            try:
                return await self.cost_table_provider.get_quote(request, timeout_ms=self.timeout_ms)
            except Exception as table_error:
                fallback = await self.rule_provider.get_quote(request, timeout_ms=self.timeout_ms)
                fallback.fallback_used = True
                fallback.explain = {
                    **fallback.explain,
                    "fallback_reason": str(table_error),
                    "fallback_source": "rule",
                }
                return fallback

        if self.mode == "api_cost_plus_markup":
            return await self._quote_api_cost_plus_markup(request)

        if self.mode == "rule_only":
            return await self.rule_provider.get_quote(request, timeout_ms=self.timeout_ms)

        if self.mode == "remote_only":
            if self._is_circuit_open():
                raise QuoteProviderError("remote_circuit_open")
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
            raise QuoteProviderError(f"Remote quote failed: {remote_error}")

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

    async def _quote_api_cost_plus_markup(self, request: QuoteRequest) -> QuoteResult:
        if not self.api_fallback_to_table_parallel:
            try:
                return await self.api_cost_provider.get_quote(request, timeout_ms=self.timeout_ms)
            except Exception as api_error:
                try:
                    fallback = await self.cost_table_provider.get_quote(request, timeout_ms=self.timeout_ms)
                    fallback.fallback_used = True
                    fallback.explain = {
                        **fallback.explain,
                        "fallback_reason": str(api_error),
                        "fallback_source": "cost_table",
                    }
                    return fallback
                except Exception as table_error:
                    fallback = await self.rule_provider.get_quote(request, timeout_ms=self.timeout_ms)
                    fallback.fallback_used = True
                    fallback.explain = {
                        **fallback.explain,
                        "fallback_reason": f"api={api_error}; table={table_error}",
                        "fallback_source": "rule",
                    }
                    return fallback

        api_task = asyncio.create_task(self.api_cost_provider.get_quote(request, timeout_ms=self.timeout_ms))
        table_task = asyncio.create_task(self.cost_table_provider.get_quote(request, timeout_ms=self.timeout_ms))

        try:
            done, _ = await asyncio.wait({api_task}, timeout=self.api_prefer_max_wait_seconds)
            if api_task in done:
                api_result = api_task.result()
                table_task.cancel()
                with contextlib.suppress(Exception):
                    await table_task
                return api_result

            try:
                fallback = await table_task
            except Exception as table_error:
                try:
                    return await api_task
                except Exception as api_error:
                    fallback = await self.rule_provider.get_quote(request, timeout_ms=self.timeout_ms)
                    fallback.fallback_used = True
                    fallback.explain = {
                        **fallback.explain,
                        "fallback_reason": f"api={api_error}; table={table_error}",
                        "fallback_source": "rule",
                    }
                    return fallback

            if not api_task.done():
                api_task.cancel()
                with contextlib.suppress(Exception):
                    await api_task
                fallback.fallback_used = True
                fallback.explain = {
                    **fallback.explain,
                    "fallback_reason": "api_slow",
                    "fallback_source": "cost_table",
                }
                return fallback

            with contextlib.suppress(Exception):
                return api_task.result()

            fallback.fallback_used = True
            fallback.explain = {
                **fallback.explain,
                "fallback_reason": "api_failed_after_wait",
                "fallback_source": "cost_table",
            }
            return fallback
        finally:
            if not api_task.done():
                api_task.cancel()
            if not table_task.done():
                table_task.cancel()

    def _is_circuit_open(self) -> bool:
        return self._circuit_open_until > time.time()

    @staticmethod
    def _normalize_mode(mode: str) -> str:
        text = str(mode or "").strip().lower()
        mapping = {
            "hybrid": "remote_then_rule",
            "provider_only": "remote_only",
        }
        normalized = mapping.get(text, text)
        valid = {
            "rule_only",
            "remote_only",
            "remote_then_rule",
            "cost_table_plus_markup",
            "api_cost_plus_markup",
        }
        if normalized not in valid:
            return "rule_only"
        return normalized

    @staticmethod
    def _resolve_api_key_env_name(cfg: dict[str, Any]) -> str:
        explicit = str(cfg.get("cost_api_key_env", "")).strip()
        if explicit:
            return explicit

        raw = str(cfg.get("cost_api_key", "")).strip()
        if raw.startswith("${") and raw.endswith("}") and len(raw) > 3:
            return raw[2:-1]
        return "QUOTE_COST_API_KEY"

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
            "cost_table_provider": await self.cost_table_provider.health_check(),
            "api_cost_provider": await self.api_cost_provider.health_check(),
            "remote_provider": await self.remote_provider.health_check(),
        }

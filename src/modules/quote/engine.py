"""自动报价引擎：多源容灾、缓存预热与追溯。"""

from __future__ import annotations

import asyncio
import contextlib
import sqlite3
import time
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.logger import get_logger
from src.modules.analytics.service import AnalyticsService
from src.modules.quote.cache import QuoteCache
from src.modules.quote.models import QuoteRequest, QuoteResult, QuoteSnapshot
from src.modules.quote.providers import (
    ApiCostMarkupQuoteProvider,
    CostTableMarkupQuoteProvider,
    IQuoteProvider,
    QuoteProviderError,
    RemoteQuoteProvider,
    RuleTableQuoteProvider,
)
from src.modules.quote.route import normalize_request_route


@dataclass(slots=True)
class CircuitBreakerState:
    failures: int = 0
    last_failure_ts: float = 0.0
    open_until: float = 0.0
    half_open: bool = False


class QuoteSnapshotStore:
    """报价快照持久化。"""

    def __init__(self, db_path: str = "data/quote_snapshots.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS quote_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cache_key TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    cost_source TEXT,
                    cost_version TEXT,
                    pricing_rule_version TEXT,
                    total_fee REAL NOT NULL,
                    latency_ms INTEGER NOT NULL,
                    provider_chain TEXT,
                    fallback_reason TEXT,
                    created_at INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_snapshots_key ON quote_snapshots(cache_key, created_at DESC);
                """
            )

    def save(self, cache_key: str, result: QuoteResult) -> None:
        if not result.snapshot:
            return
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO quote_snapshots(
                    cache_key, provider, cost_source, cost_version, pricing_rule_version,
                    total_fee, latency_ms, provider_chain, fallback_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cache_key,
                    result.provider,
                    result.snapshot.cost_source,
                    result.snapshot.cost_version,
                    result.snapshot.pricing_rule_version,
                    result.total_fee,
                    result.snapshot.latency_ms,
                    ",".join(result.snapshot.provider_chain),
                    result.snapshot.fallback_reason,
                    now,
                ),
            )

    def get_latest(self, cache_key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM quote_snapshots WHERE cache_key=? ORDER BY id DESC LIMIT 1",
                (cache_key,),
            ).fetchone()
            return dict(row) if row else None


class AutoQuoteEngine:
    """自动报价引擎，支持多源容灾、缓存预热与追溯。"""

    SOURCE_PRIORITY = ["api", "hot_cache", "cost_table", "fallback_template"]
    PRICING_RULE_VERSION = "v1.2"

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
        self.half_open_success_threshold = int(cfg.get("half_open_success_threshold", 2))
        self.hot_cache_ttl_seconds = int(cfg.get("hot_cache_ttl_seconds", 300))
        self.api_fallback_to_table_parallel = bool(cfg.get("api_fallback_to_table_parallel", True))
        self.api_prefer_max_wait_seconds = max(0.05, float(cfg.get("api_prefer_max_wait_seconds", 1.2)))

        self._circuit_breakers: dict[str, CircuitBreakerState] = {}
        self._hot_cache: dict[str, tuple[QuoteResult, float]] = {}
        self._version = cfg.get("version", "v2.0")

        self.rule_provider: IQuoteProvider = RuleTableQuoteProvider()
        self.cost_table_provider: IQuoteProvider = CostTableMarkupQuoteProvider(
            table_dir=str(cfg.get("cost_table_dir", "data/quote_costs")),
            include_patterns=cfg.get("cost_table_patterns", ["*.xlsx", "*.csv"]),
            markup_rules=cfg.get("markup_rules", {}),
            pricing_profile=str(cfg.get("pricing_profile", "normal")),
        )
        self.api_cost_provider: IQuoteProvider = ApiCostMarkupQuoteProvider(
            api_url=str(cfg.get("cost_api_url", "")),
            api_key_env=self._resolve_api_key_env_name(cfg),
            markup_rules=cfg.get("markup_rules", {}),
            pricing_profile=str(cfg.get("pricing_profile", "normal")),
        )
        self.remote_provider: IQuoteProvider = RemoteQuoteProvider(
            enabled=bool(providers_cfg.get("remote", {}).get("enabled", False)),
            simulated_latency_ms=int(providers_cfg.get("remote", {}).get("simulated_latency_ms", 120)),
            failure_rate=float(providers_cfg.get("remote", {}).get("failure_rate", 0.0)),
        )

        self.cache = QuoteCache(
            ttl_seconds=int(cfg.get("ttl_seconds", 90)),
            max_stale_seconds=int(cfg.get("max_stale_seconds", 300)),
        )

        self.snapshot_store = QuoteSnapshotStore(db_path=cfg.get("snapshot_db_path", "data/quote_snapshots.db"))

        self._analytics: AnalyticsService | None = None
        self._analytics_enabled = bool(cfg.get("analytics_log_enabled", True))
        self._top_routes: list[tuple[str, str]] = []

    async def get_quote(self, request: QuoteRequest) -> QuoteResult:
        if not self.enabled:
            raise QuoteProviderError("Quote engine is disabled")

        normalized_request = normalize_request_route(request)
        key = normalized_request.cache_key()

        hot_cached = self._get_hot_cache(key)
        if hot_cached:
            hot_cached.cache_hit = True
            return deepcopy(hot_cached)

        cached, fresh_hit, stale_hit = self.cache.get(key)
        if cached and fresh_hit:
            return deepcopy(cached)

        if stale_hit and cached:
            asyncio.create_task(self._refresh_cache_in_background(normalized_request, key))
            return deepcopy(cached)

        start = time.perf_counter()
        result = await self._quote_multi_source(normalized_request)
        latency_ms = int((time.perf_counter() - start) * 1000)

        result.total_fee = round(result.total_fee * (1 + self.safety_margin), 2)
        result.explain = {
            **result.explain,
            "normalized_origin": normalized_request.origin,
            "normalized_destination": normalized_request.destination,
            "courier": normalized_request.courier,
            "engine_version": self._version,
        }

        if result.snapshot:
            result.snapshot.latency_ms = latency_ms

        self.cache.set(key, result)
        self._set_hot_cache(key, result)
        self.snapshot_store.save(key, result)

        await self._log_quote(normalized_request, result, latency_ms=latency_ms)
        return deepcopy(result)

    def _get_hot_cache(self, key: str) -> QuoteResult | None:
        entry = self._hot_cache.get(key)
        if not entry:
            return None
        result, expires_at = entry
        if time.time() > expires_at:
            self._hot_cache.pop(key, None)
            return None
        return result

    def _set_hot_cache(self, key: str, result: QuoteResult) -> None:
        expires_at = time.time() + self.hot_cache_ttl_seconds
        self._hot_cache[key] = (result, expires_at)

    def _with_snapshot(
        self,
        result: QuoteResult,
        *,
        cost_source: str,
        cost_version: str,
        provider_chain: list[str],
        fallback_reason: str = "",
    ) -> QuoteResult:
        result.snapshot = QuoteSnapshot(
            cost_source=cost_source,
            cost_version=cost_version,
            pricing_rule_version=self.PRICING_RULE_VERSION,
            provider_chain=list(provider_chain),
            fallback_reason=fallback_reason,
        )
        return result

    async def _quote_multi_source(self, request: QuoteRequest) -> QuoteResult:
        provider_chain: list[str] = []

        if self.mode == "cost_table_plus_markup":
            try:
                result = await self.cost_table_provider.get_quote(request, timeout_ms=self.timeout_ms)
                return self._with_snapshot(
                    result,
                    cost_source="cost_table",
                    cost_version="local",
                    provider_chain=["cost_table"],
                )
            except Exception as table_error:
                fallback = await self.rule_provider.get_quote(request, timeout_ms=self.timeout_ms)
                fallback.fallback_used = True
                fallback.explain = {
                    **fallback.explain,
                    "fallback_reason": str(table_error),
                    "fallback_source": "rule",
                }
                return self._with_snapshot(
                    fallback,
                    cost_source="rule_table",
                    cost_version="builtin",
                    provider_chain=["cost_table", "rule_table"],
                    fallback_reason=str(table_error),
                )

        if self.mode == "api_cost_plus_markup":
            return await self._quote_api_cost_plus_markup(request)

        if self.mode == "rule_only":
            result = await self.rule_provider.get_quote(request, timeout_ms=self.timeout_ms)
            return self._with_snapshot(
                result,
                cost_source="rule_table",
                cost_version="builtin",
                provider_chain=["rule_table"],
            )

        circuit = self._get_circuit_breaker("remote")

        if self.mode == "remote_only":
            if circuit.open_until > time.time() and not circuit.half_open:
                raise QuoteProviderError("remote_circuit_open")

            remote_error: Exception | None = None
            for _ in range(max(1, self.retry_times)):
                try:
                    result = await self.remote_provider.get_quote(request, timeout_ms=self.timeout_ms)
                    self._record_success(circuit)
                    return self._with_snapshot(
                        result,
                        cost_source="api",
                        cost_version="live",
                        provider_chain=["api"],
                    )
                except Exception as exc:
                    remote_error = exc
                    self._record_failure(circuit)
            raise QuoteProviderError(f"Remote quote failed: {remote_error}")

        if circuit.half_open:
            try:
                result = await self.remote_provider.get_quote(request, timeout_ms=self.timeout_ms)
                self._record_success(circuit)
                return self._with_snapshot(
                    result,
                    cost_source="api",
                    cost_version="live",
                    provider_chain=["api"],
                )
            except Exception:
                self._record_failure(circuit)
                return await self._fallback_chain(request, provider_chain, QuoteProviderError("half_open_failed"))

        if circuit.open_until > time.time():
            return await self._fallback_chain(request, provider_chain, QuoteProviderError("remote_circuit_open"))

        remote_error: Exception | None = None
        for _ in range(max(1, self.retry_times)):
            try:
                result = await self.remote_provider.get_quote(request, timeout_ms=self.timeout_ms)
                self._record_success(circuit)
                return self._with_snapshot(
                    result,
                    cost_source="api",
                    cost_version="live",
                    provider_chain=["api"],
                )
            except Exception as exc:
                remote_error = exc
                self._record_failure(circuit)

        return await self._fallback_chain(request, provider_chain, remote_error)

    async def _fallback_chain(
        self,
        request: QuoteRequest,
        provider_chain: list[str],
        remote_error: Exception | None,
    ) -> QuoteResult:
        provider_chain.append("hot_cache_miss")

        hot_cached = self._get_hot_cache(request.cache_key())
        if hot_cached:
            hot_cached.fallback_used = True
            hot_cached.snapshot = QuoteSnapshot(
                cost_source="hot_cache",
                cost_version="cached",
                pricing_rule_version=self.PRICING_RULE_VERSION,
                provider_chain=[*provider_chain, "hot_cache"],
                fallback_reason=str(remote_error) if remote_error else "api_unavailable",
            )
            return hot_cached

        provider_chain.append("cost_table")
        try:
            result = await self.rule_provider.get_quote(request, timeout_ms=self.timeout_ms)
            result.fallback_used = True
            result.snapshot = QuoteSnapshot(
                cost_source="cost_table",
                cost_version="local",
                pricing_rule_version=self.PRICING_RULE_VERSION,
                provider_chain=provider_chain,
                fallback_reason=str(remote_error) if remote_error else "api_unavailable",
            )
            return result
        except Exception as rule_exc:
            provider_chain.append("fallback_template")
            return self._fallback_template_quote(request, provider_chain, remote_error, rule_exc)

    def _fallback_template_quote(
        self,
        request: QuoteRequest,
        provider_chain: list[str],
        remote_error: Exception | None,
        rule_error: Exception | None,
    ) -> QuoteResult:
        base_fee = 12.0
        distance_fee = 5.0 if request.origin[:2] != request.destination[:2] else 0.0
        weight_fee = max(0.0, request.weight - 1.0) * 2.5
        remote_fee = (
            8.0 if any(k in f"{request.origin}{request.destination}" for k in ["西藏", "新疆", "青海"]) else 0.0
        )
        total = base_fee + distance_fee + weight_fee + remote_fee

        return QuoteResult(
            provider="fallback_template",
            base_fee=base_fee,
            surcharges={
                "distance": distance_fee,
                "weight": weight_fee,
                **({"remote": remote_fee} if remote_fee else {}),
            },
            total_fee=round(total, 2),
            eta_minutes=72 * 60,
            confidence=0.5,
            fallback_used=True,
            explain={"mode": "fallback_template", "remote_error": str(remote_error), "rule_error": str(rule_error)},
            snapshot=QuoteSnapshot(
                cost_source="fallback_template",
                cost_version="hardcoded",
                pricing_rule_version=self.PRICING_RULE_VERSION,
                provider_chain=provider_chain,
                fallback_reason=f"all_sources_failed: remote={remote_error}, rule={rule_error}",
            ),
        )

    def _get_circuit_breaker(self, name: str) -> CircuitBreakerState:
        if name not in self._circuit_breakers:
            self._circuit_breakers[name] = CircuitBreakerState()
        return self._circuit_breakers[name]

    def _record_failure(self, circuit: CircuitBreakerState) -> None:
        circuit.failures += 1
        circuit.last_failure_ts = time.time()
        if circuit.failures >= self.circuit_fail_threshold:
            circuit.open_until = time.time() + self.circuit_open_seconds
            circuit.half_open = False
            self.logger.warning(f"Circuit breaker opened after {circuit.failures} failures")

    def _record_success(self, circuit: CircuitBreakerState) -> None:
        if circuit.half_open:
            circuit.half_open = False
            self.logger.info("Circuit breaker recovered from half-open")
        circuit.failures = 0
        circuit.open_until = 0.0

    def try_half_open(self) -> bool:
        circuit = self._get_circuit_breaker("remote")
        if circuit.open_until > 0 and time.time() >= circuit.open_until:
            circuit.half_open = True
            circuit.open_until = 0.0
            self.logger.info("Circuit breaker entering half-open state")
            return True
        return False

    async def prewarm_cache(self, routes: list[tuple[str, str]] | None = None) -> int:
        routes = routes or self._top_routes
        if not routes:
            return 0

        warmed = 0
        for origin, destination in routes[:20]:
            request = QuoteRequest(
                origin=origin,
                destination=destination,
                weight=1.0,
                service_level="standard",
            )
            try:
                await self.get_quote(request)
                warmed += 1
            except Exception as exc:
                self.logger.warning(f"Prewarm failed for {origin}->{destination}: {exc}")

        self.logger.info(f"Prewarmed {warmed}/{len(routes)} routes")
        return warmed

    def set_top_routes(self, routes: list[tuple[str, str]]) -> None:
        self._top_routes = routes[:50]

    async def _quote_api_cost_plus_markup(self, request: QuoteRequest) -> QuoteResult:
        if not self.api_fallback_to_table_parallel:
            try:
                result = await self.api_cost_provider.get_quote(request, timeout_ms=self.timeout_ms)
                return self._with_snapshot(
                    result,
                    cost_source="api_cost",
                    cost_version="live",
                    provider_chain=["api_cost"],
                )
            except Exception as api_error:
                try:
                    fallback = await self.cost_table_provider.get_quote(request, timeout_ms=self.timeout_ms)
                    fallback.fallback_used = True
                    fallback.explain = {
                        **fallback.explain,
                        "fallback_reason": str(api_error),
                        "fallback_source": "cost_table",
                    }
                    return self._with_snapshot(
                        fallback,
                        cost_source="cost_table",
                        cost_version="local",
                        provider_chain=["api_cost", "cost_table"],
                        fallback_reason=str(api_error),
                    )
                except Exception as table_error:
                    fallback = await self.rule_provider.get_quote(request, timeout_ms=self.timeout_ms)
                    fallback.fallback_used = True
                    fallback.explain = {
                        **fallback.explain,
                        "fallback_reason": f"api={api_error}; table={table_error}",
                        "fallback_source": "rule",
                    }
                    return self._with_snapshot(
                        fallback,
                        cost_source="rule_table",
                        cost_version="builtin",
                        provider_chain=["api_cost", "cost_table", "rule_table"],
                        fallback_reason=f"api={api_error}; table={table_error}",
                    )

        api_task = asyncio.create_task(self.api_cost_provider.get_quote(request, timeout_ms=self.timeout_ms))
        table_task = asyncio.create_task(self.cost_table_provider.get_quote(request, timeout_ms=self.timeout_ms))

        try:
            done, _ = await asyncio.wait({api_task}, timeout=self.api_prefer_max_wait_seconds)
            if api_task in done:
                try:
                    api_result = api_task.result()
                    table_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await table_task
                    return self._with_snapshot(
                        api_result,
                        cost_source="api_cost",
                        cost_version="live",
                        provider_chain=["api_cost"],
                    )
                except Exception as api_error:
                    try:
                        fallback = await table_task
                    except Exception as table_error:
                        fallback = await self.rule_provider.get_quote(request, timeout_ms=self.timeout_ms)
                        fallback.fallback_used = True
                        fallback.explain = {
                            **fallback.explain,
                            "fallback_reason": f"api={api_error}; table={table_error}",
                            "fallback_source": "rule",
                        }
                        return self._with_snapshot(
                            fallback,
                            cost_source="rule_table",
                            cost_version="builtin",
                            provider_chain=["api_cost", "cost_table", "rule_table"],
                            fallback_reason=f"api={api_error}; table={table_error}",
                        )

                    fallback.fallback_used = True
                    fallback.explain = {
                        **fallback.explain,
                        "fallback_reason": str(api_error),
                        "fallback_source": "cost_table",
                    }
                    return self._with_snapshot(
                        fallback,
                        cost_source="cost_table",
                        cost_version="local",
                        provider_chain=["api_cost", "cost_table"],
                        fallback_reason=str(api_error),
                    )

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
                    return self._with_snapshot(
                        fallback,
                        cost_source="rule_table",
                        cost_version="builtin",
                        provider_chain=["api_cost", "cost_table", "rule_table"],
                        fallback_reason=f"api={api_error}; table={table_error}",
                    )

            if not api_task.done():
                api_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await api_task
                fallback.fallback_used = True
                fallback.explain = {
                    **fallback.explain,
                    "fallback_reason": "api_slow",
                    "fallback_source": "cost_table",
                }
                return self._with_snapshot(
                    fallback,
                    cost_source="cost_table",
                    cost_version="local",
                    provider_chain=["api_cost", "cost_table"],
                    fallback_reason="api_slow",
                )

            try:
                api_result = api_task.result()
                return self._with_snapshot(
                    api_result,
                    cost_source="api_cost",
                    cost_version="live",
                    provider_chain=["api_cost"],
                )
            except Exception:
                pass

            fallback.fallback_used = True
            fallback.explain = {
                **fallback.explain,
                "fallback_reason": "api_failed_after_wait",
                "fallback_source": "cost_table",
            }
            return self._with_snapshot(
                fallback,
                cost_source="cost_table",
                cost_version="local",
                provider_chain=["api_cost", "cost_table"],
                fallback_reason="api_failed_after_wait",
            )
        finally:
            if not api_task.done():
                api_task.cancel()
            if not table_task.done():
                table_task.cancel()

    def _is_circuit_open(self) -> bool:
        circuit = self._get_circuit_breaker("remote")
        return circuit.open_until > time.time() and not circuit.half_open

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
            latest = await self._quote_multi_source(request)
            latest.total_fee = round(latest.total_fee * (1 + self.safety_margin), 2)
            latest.cache_hit = False
            latest.stale = False
            self.cache.set(key, latest)
            self._set_hot_cache(key, latest)
        except Exception as exc:
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

    async def health_check(self) -> dict[str, Any]:
        circuit = self._get_circuit_breaker("remote")
        return {
            "rule_provider": await self.rule_provider.health_check(),
            "cost_table_provider": await self.cost_table_provider.health_check(),
            "api_cost_provider": await self.api_cost_provider.health_check(),
            "remote_provider": await self.remote_provider.health_check(),
            "circuit_breaker": {
                "failures": circuit.failures,
                "open": circuit.open_until > time.time(),
                "half_open": circuit.half_open,
            },
            "hot_cache_size": len(self._hot_cache),
            "engine_version": self._version,
        }

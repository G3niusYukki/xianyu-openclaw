"""报价缓存（TTL + stale-while-revalidate）。"""

import time
from dataclasses import dataclass

from src.modules.quote.models import QuoteResult


@dataclass(slots=True)
class QuoteCacheEntry:
    value: QuoteResult
    expires_at: float
    stale_until: float


class QuoteCache:
    def __init__(self, ttl_seconds: int = 60, max_stale_seconds: int = 300):
        self.ttl_seconds = max(1, ttl_seconds)
        self.max_stale_seconds = max(0, max_stale_seconds)
        self._entries: dict[str, QuoteCacheEntry] = {}

    def get(self, key: str) -> tuple[QuoteResult | None, bool, bool]:
        now = time.time()
        entry = self._entries.get(key)
        if not entry:
            return None, False, False

        if entry.expires_at >= now:
            result = entry.value
            result.cache_hit = True
            result.stale = False
            return result, True, False

        if entry.stale_until >= now:
            result = entry.value
            result.cache_hit = True
            result.stale = True
            return result, False, True

        self._entries.pop(key, None)
        return None, False, False

    def set(self, key: str, result: QuoteResult) -> None:
        now = time.time()
        self._entries[key] = QuoteCacheEntry(
            value=result,
            expires_at=now + self.ttl_seconds,
            stale_until=now + self.ttl_seconds + self.max_stale_seconds,
        )

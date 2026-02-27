"""
消息外发合规策略
Outbound message compliance policy
"""

from __future__ import annotations

import time
from typing import Any


DEFAULT_OUTBOUND_BLOCK_KEYWORDS = [
    "微信",
    "vx",
    "qq",
    "qq群",
    "站外",
    "私下交易",
    "加我",
]


class OutboundCompliancePolicy:
    """消息外发合规决策（禁词 + 频控）。"""

    def __init__(self, config: dict[str, Any] | None = None):
        cfg = config or {}
        self.enabled = bool(cfg.get("outbound_compliance_enabled", True))
        self.min_interval_seconds = self._safe_int(cfg.get("outbound_min_interval_seconds", 1), default=1, minimum=0)
        self.max_per_session_hour = self._safe_int(
            cfg.get("outbound_max_per_session_hour", 6),
            default=6,
            minimum=1,
        )
        self.max_per_session_day = self._safe_int(
            cfg.get("outbound_max_per_session_day", 20),
            default=20,
            minimum=1,
        )

        keywords = cfg.get("outbound_block_keywords")
        if isinstance(keywords, list):
            parsed = [str(item).strip().lower() for item in keywords if str(item).strip()]
        else:
            parsed = []
        self.block_keywords = parsed or list(DEFAULT_OUTBOUND_BLOCK_KEYWORDS)

    def evaluate(
        self,
        session_id: str,
        reply_text: str,
        state: dict[str, Any] | None,
        *,
        now_ts: float | None = None,
    ) -> tuple[bool, str]:
        """判断外发消息是否允许发送。"""
        if not self.enabled:
            return True, "disabled"

        sid = str(session_id or "").strip()
        if not sid:
            return False, "missing_session_id"

        text = str(reply_text or "").strip()
        if not text:
            return False, "empty_reply"

        lowered = text.lower()
        if any(keyword in lowered for keyword in self.block_keywords):
            return False, "blocked_keyword"

        now = now_ts if now_ts is not None else time.time()
        history = state or {}
        last_sent_at = self._safe_float(history.get("compliance_last_sent_at", history.get("last_outbound_at")))
        if last_sent_at > 0 and now - last_sent_at < self.min_interval_seconds:
            return False, "min_interval_not_met"

        timestamps = self._safe_float_list(history.get("compliance_outbound_timestamps"))
        cutoff_day = now - 86400
        recent_day = [ts for ts in timestamps if ts >= cutoff_day]
        recent_hour_count = sum(1 for ts in recent_day if ts >= now - 3600)

        if recent_hour_count >= self.max_per_session_hour:
            return False, "max_per_session_hour_reached"
        if len(recent_day) >= self.max_per_session_day:
            return False, "max_per_session_day_reached"

        return True, "allowed"

    def build_state_updates_on_sent(
        self,
        state: dict[str, Any] | None,
        *,
        now_ts: float | None = None,
    ) -> dict[str, Any]:
        """构造发送成功后的状态更新。"""
        now = now_ts if now_ts is not None else time.time()
        history = state or {}
        timestamps = self._safe_float_list(history.get("compliance_outbound_timestamps"))
        cutoff_day = now - 86400
        recent_day = [ts for ts in timestamps if ts >= cutoff_day]
        recent_day.append(now)
        if len(recent_day) > 200:
            recent_day = recent_day[-200:]
        return {
            "compliance_last_sent_at": now,
            "compliance_outbound_timestamps": recent_day,
            "compliance_last_decision": "allowed",
        }

    def build_state_updates_on_blocked(self, reason: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
        """构造阻断后的状态更新。"""
        history = state or {}
        blocked_count = self._safe_int(history.get("compliance_blocked_count", 0), default=0, minimum=0) + 1
        return {
            "compliance_last_decision": str(reason or "blocked"),
            "compliance_blocked_count": blocked_count,
            "compliance_last_blocked_at": time.time(),
        }

    @staticmethod
    def _safe_int(value: Any, *, default: int, minimum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed >= minimum else minimum

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _safe_float_list(cls, value: Any) -> list[float]:
        if not isinstance(value, list):
            return []
        result: list[float] = []
        for item in value:
            num = cls._safe_float(item)
            if num > 0:
                result.append(num)
        return result

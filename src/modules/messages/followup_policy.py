"""
已读未回合规跟进策略
Read-no-reply compliant follow-up policy
"""

from __future__ import annotations

import time
from typing import Any


DEFAULT_READ_NO_REPLY_TEMPLATES = [
    "看到你已读啦，我先把这个方案给你留着。需要我按你的重量和地区再精确算一次吗？",
    "如果你还在比较寄件方案，我可以按你的预算再给一个更省的选项，需要的话直接回我“继续报价”就行。",
]

DEFAULT_READ_NO_REPLY_STOP_KEYWORDS = [
    "不用",
    "不需要",
    "先不",
    "别发了",
    "勿扰",
    "拉黑",
    "举报",
]


class ReadNoReplyFollowupPolicy:
    """已读未回跟进决策策略。"""

    def __init__(self, config: dict[str, Any] | None = None):
        cfg = config or {}

        self.enabled = bool(cfg.get("read_no_reply_followup_enabled", False))
        self.min_elapsed_seconds = int(cfg.get("read_no_reply_min_elapsed_seconds", 300))
        self.min_interval_seconds = int(cfg.get("read_no_reply_min_interval_seconds", 1800))
        self.max_per_session = int(cfg.get("read_no_reply_max_per_session", 1))

        templates = cfg.get("read_no_reply_templates")
        if isinstance(templates, list):
            parsed = [str(item).strip() for item in templates if str(item).strip()]
        else:
            parsed = []
        self.templates = parsed or list(DEFAULT_READ_NO_REPLY_TEMPLATES)

        stop_keywords = cfg.get("read_no_reply_stop_keywords")
        if isinstance(stop_keywords, list):
            parsed_stop = [str(item).strip().lower() for item in stop_keywords if str(item).strip()]
        else:
            parsed_stop = []
        self.stop_keywords = parsed_stop or [kw.lower() for kw in DEFAULT_READ_NO_REPLY_STOP_KEYWORDS]

    def evaluate(
        self,
        session: dict[str, Any],
        state: dict[str, Any] | None,
        *,
        now_ts: float | None = None,
    ) -> tuple[bool, str]:
        """判断当前会话是否允许发送跟进。"""
        if not self.enabled:
            return False, "disabled"

        session_id = str(session.get("session_id", "")).strip()
        if not session_id:
            return False, "missing_session_id"

        history = state or {}
        if not history:
            return False, "no_history"

        if bool(history.get("opted_out", False)):
            return False, "opted_out"

        now = now_ts if now_ts is not None else time.time()

        first_reply_at = self._safe_float(history.get("first_reply_at"))
        if first_reply_at <= 0:
            return False, "no_first_reply"
        if now - first_reply_at < self.min_elapsed_seconds:
            return False, "too_soon_after_first_reply"

        followup_sent_count = int(history.get("followup_sent_count") or 0)
        if followup_sent_count >= self.max_per_session:
            return False, "max_followups_reached"

        last_followup_at = self._safe_float(history.get("last_followup_at"))
        if last_followup_at > 0 and now - last_followup_at < self.min_interval_seconds:
            return False, "min_interval_not_met"

        if self._hit_stop_keywords(session, history):
            return False, "stop_keyword_hit"

        return True, "eligible"

    def build_followup_message(self, session: dict[str, Any], state: dict[str, Any] | None) -> str:
        """生成跟进文案（默认轮询模板）。"""
        history = state or {}
        sent_count = int(history.get("followup_sent_count") or 0)
        template = self.templates[sent_count % len(self.templates)]

        peer_name = str(session.get("peer_name", "")).strip()
        item_title = str(session.get("item_title", "")).strip()
        message = template

        if "{peer_name}" in message:
            message = message.replace("{peer_name}", peer_name or "你")
        if "{item_title}" in message:
            message = message.replace("{item_title}", item_title or "这个商品")

        return message

    def _hit_stop_keywords(self, session: dict[str, Any], state: dict[str, Any]) -> bool:
        texts = [
            str(session.get("last_message", "")).lower(),
            str(state.get("last_inbound_message", "")).lower(),
        ]
        merged = " ".join(texts)
        return any(keyword in merged for keyword in self.stop_keywords)

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

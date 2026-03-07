"""Prohibited-item safety guard with LLM + rule double check."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

_LLMJudge = Callable[[str, str], dict[str, Any]]

PROHIBITED_KEYWORDS = (
    "手机",
    "电池",
    "充电宝",
    "电脑",
    "相机",
    "数码",
    "刀",
    "锋利",
    "剪刀",
    "油",
    "易燃",
    "酒精",
    "生鲜",
    "水果",
    "蔬菜",
    "肉",
    "冷链",
    "易碎",
    "玻璃",
    "灯",
    "贵重",
    "黄金",
    "首饰",
    "扫地机",
    "显示器",
    "机箱",
)

ALLOW_WHITELIST = ("蓝牙耳机",)


@dataclass
class SafetyDecision:
    prohibited: bool
    reason: str | None
    llm_flagged: bool
    matched_keyword: str | None


class SafetyGuard:
    """Use LLM as first pass and keyword verification as second pass."""

    def __init__(self, llm_judge: _LLMJudge) -> None:
        self.llm_judge = llm_judge

    def _match_keyword(self, message: str) -> str | None:
        msg = str(message or "")
        if any(allowed in msg for allowed in ALLOW_WHITELIST):
            return None
        for kw in PROHIBITED_KEYWORDS:
            if kw in msg:
                return kw
        return None

    def check(self, message: str, context: str = "") -> SafetyDecision:
        llm_result = self.llm_judge(message, context) or {}
        llm_flagged = bool(llm_result.get("is_prohibited"))
        reason = str(llm_result.get("prohibited_reason") or "").strip() or None

        if not llm_flagged:
            return SafetyDecision(prohibited=False, reason=None, llm_flagged=False, matched_keyword=None)

        matched = self._match_keyword(message)
        if matched:
            final_reason = reason or f"包含禁寄物品关键词: {matched}"
            return SafetyDecision(prohibited=True, reason=final_reason, llm_flagged=True, matched_keyword=matched)

        return SafetyDecision(
            prohibited=False,
            reason="LLM命中但当前消息未发现禁寄关键词，已按规则覆盖",
            llm_flagged=True,
            matched_keyword=None,
        )

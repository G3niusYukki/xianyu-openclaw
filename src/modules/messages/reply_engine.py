"""
消息回复策略引擎
Message Reply Strategy Engine

将自动回复逻辑从服务层剥离，支持意图规则、虚拟商品场景兜底和旧关键词兼容。
"""

import re
from dataclasses import dataclass, field
from typing import Any

DEFAULT_VIRTUAL_PRODUCT_KEYWORDS = [
    "虚拟",
    "卡密",
    "激活码",
    "兑换码",
    "cdk",
    "授权码",
    "序列号",
    "会员",
    "代下单",
    "代拍",
    "代充",
    "代购",
    "代订",
]


DEFAULT_INTENT_RULES: list[dict[str, Any]] = [
    {
        "name": "availability",
        "keywords": ["在吗", "还在", "有货吗", "有吗"],
        "reply": "在的，可以直接下单，拍下后我会尽快处理。",
    },
    {
        "name": "card_code_delivery",
        "keywords": ["卡密", "兑换码", "激活码", "cdk", "授权码", "序列号"],
        "reply": "这是虚拟商品，付款后会通过平台聊天发卡密/兑换信息，请按商品说明使用。",
    },
    {
        "name": "online_fulfillment",
        "keywords": ["代下单", "代拍", "代充", "代购", "代订"],
        "reply": "支持代下单服务，请把具体需求、数量和时效发我，我确认后马上安排。",
    },
    {
        "name": "delivery_eta",
        "keywords": ["多久发", "发货时间", "什么时候发", "多久到账", "多久到"],
        "patterns": [r"\d+\s*分钟", r"\d+\s*小时"],
        "reply": "虚拟商品通常付款后几分钟内处理，高峰期会稍有延迟，我会尽快给你。",
    },
    {
        "name": "price_bargain",
        "keywords": ["最低", "便宜", "优惠", "少点", "能便宜"],
        "reply": "价格已经尽量优惠，量大或长期合作可以再沟通方案。",
    },
    {
        "name": "usage_support",
        "keywords": ["怎么用", "不会用", "教程", "使用方法", "售后"],
        "reply": "下单后我会提供对应使用说明，遇到问题可随时留言，我会协助处理。",
    },
    {
        "name": "platform_safety",
        "keywords": ["靠谱吗", "安全", "担保", "骗子", "走平台"],
        "reply": "建议全程走闲鱼平台流程交易，按平台规则下单和确认，双方都更有保障。",
    },
]


@dataclass(slots=True)
class IntentRule:
    """单条回复规则。"""

    name: str
    reply: str
    keywords: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    priority: int = 100

    def matches(self, text: str) -> bool:
        for keyword in self.keywords:
            if keyword and keyword.lower() in text:
                return True
        for pattern in self.patterns:
            if pattern and re.search(pattern, text, flags=re.IGNORECASE):
                return True
        return False


class ReplyStrategyEngine:
    """通用自动回复策略引擎。"""

    def __init__(
        self,
        *,
        default_reply: str,
        virtual_default_reply: str,
        reply_prefix: str = "",
        keyword_replies: dict[str, str] | None = None,
        intent_rules: list[dict[str, Any]] | None = None,
        virtual_product_keywords: list[str] | None = None,
    ):
        self.default_reply = default_reply
        self.virtual_default_reply = virtual_default_reply or default_reply
        self.reply_prefix = reply_prefix
        self.virtual_product_keywords = [
            kw.lower() for kw in (virtual_product_keywords or DEFAULT_VIRTUAL_PRODUCT_KEYWORDS) if str(kw).strip()
        ]

        rules_data = intent_rules if isinstance(intent_rules, list) and intent_rules else DEFAULT_INTENT_RULES
        parsed_rules = [self._parse_rule(rule) for rule in rules_data]

        legacy_rules = self._build_legacy_keyword_rules(keyword_replies or {})
        self.rules = sorted([*parsed_rules, *legacy_rules], key=lambda rule: rule.priority)

    def generate_reply(self, message_text: str, item_title: str = "") -> str:
        """按规则生成回复。"""
        normalized = self._normalize_text(message_text)

        reply = ""
        for rule in self.rules:
            if rule.matches(normalized):
                reply = rule.reply
                break

        if not reply:
            if self._is_virtual_context(normalized, item_title):
                reply = self.virtual_default_reply
            else:
                reply = self.default_reply

        if item_title:
            reply = f"关于「{item_title}」，{reply}"

        if self.reply_prefix:
            reply = f"{self.reply_prefix}{reply}"

        return reply

    def _parse_rule(self, raw_rule: dict[str, Any]) -> IntentRule:
        name = str(raw_rule.get("name") or f"rule_{id(raw_rule)}")
        reply = str(raw_rule.get("reply") or "").strip()
        if not reply:
            reply = self.default_reply

        keywords = [str(k).strip().lower() for k in raw_rule.get("keywords", []) if str(k).strip()]
        patterns = [str(p).strip() for p in raw_rule.get("patterns", []) if str(p).strip()]
        priority = int(raw_rule.get("priority", 100))

        return IntentRule(name=name, reply=reply, keywords=keywords, patterns=patterns, priority=priority)

    def _build_legacy_keyword_rules(self, keyword_replies: dict[str, str]) -> list[IntentRule]:
        rules: list[IntentRule] = []
        for keyword, reply in keyword_replies.items():
            clean_keyword = str(keyword).strip()
            clean_reply = str(reply).strip()
            if not clean_keyword or not clean_reply:
                continue
            rules.append(
                IntentRule(
                    name=f"legacy_{clean_keyword}",
                    reply=clean_reply,
                    keywords=[clean_keyword.lower()],
                    priority=200,
                )
            )
        return rules

    def _is_virtual_context(self, message_text: str, item_title: str) -> bool:
        title_text = self._normalize_text(item_title)
        return any(keyword in message_text or keyword in title_text for keyword in self.virtual_product_keywords)

    @staticmethod
    def _normalize_text(text: str) -> str:
        return (text or "").strip().lower()

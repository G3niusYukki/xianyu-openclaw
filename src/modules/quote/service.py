"""
自动报价服务
Quote Service
"""

from __future__ import annotations

import math
import re
from typing import Any

import httpx

from src.core.config import get_config
from src.core.logger import get_logger
from src.modules.quote.models import QuoteParseResult, QuoteRequest, QuoteResult


class QuoteService:
    """快递询价解析与报价服务。"""

    QUOTE_KEYWORDS = (
        "报价",
        "报个价",
        "多少钱",
        "运费",
        "邮费",
        "快递费",
        "寄到",
        "发到",
        "寄件",
        "快递",
        "时效",
        "多久到",
    )

    URGENCY_KEYWORDS = ("加急", "急件", "当天", "立即", "马上", "最快", "尽快")

    def __init__(self, config: dict[str, Any] | None = None):
        app_config = get_config()
        self.config = config or app_config.get_section("quote", {})
        self.logger = get_logger()

    def detect_quote_intent(self, message_text: str, item_title: str = "") -> bool:
        merged = f"{message_text or ''} {item_title or ''}".lower()
        return any(keyword in merged for keyword in self.QUOTE_KEYWORDS)

    def parse_quote_request(self, message_text: str, item_title: str = "") -> QuoteParseResult:
        message_text = message_text or ""
        is_quote_intent = self.detect_quote_intent(message_text, item_title=item_title)

        destination = self._extract_destination_city(message_text)
        weight_kg = self._extract_weight_kg(message_text)
        pieces = self._extract_pieces(message_text)
        urgency = self._is_urgency_request(message_text)
        origin_city = str(self.config.get("origin_city", "杭州"))

        request = QuoteRequest(
            destination_city=destination,
            weight_kg=weight_kg,
            pieces=pieces,
            urgency=urgency,
            origin_city=origin_city,
            raw_message=message_text,
        )

        missing_fields: list[str] = []
        if is_quote_intent:
            if not request.destination_city:
                missing_fields.append("destination_city")
            if not request.weight_kg:
                missing_fields.append("weight_kg")

        return QuoteParseResult(
            is_quote_intent=is_quote_intent,
            request=request,
            missing_fields=missing_fields,
        )

    def build_first_reply(self, parsed: QuoteParseResult) -> str:
        if not parsed.is_quote_intent:
            return ""
        if parsed.missing_fields:
            missing_labels = {
                "destination_city": "收件城市",
                "weight_kg": "预估重量（kg）",
            }
            missing_hints = [missing_labels.get(field, field) for field in parsed.missing_fields]
            missing_text = "、".join(missing_hints)
            return (
                "收到，我先帮你准备报价。"
                f"请补充：{missing_text}。"
                "信息一齐我会马上回复具体价格。"
            )
        return "收到，正在为你计算具体报价，马上回复你。"

    def build_quote_message(self, quote: QuoteResult, request: QuoteRequest) -> str:
        destination = request.destination_city or "目的地"
        weight_text = f"{request.weight_kg:.2f}kg" if request.weight_kg else "未知重量"
        speed_text = "加急" if request.urgency else "标准"
        return (
            f"报价结果：寄往{destination}，{weight_text}，{speed_text}。"
            f"预计 {quote.total_fee:.2f} 元"
            f"（基础 {quote.base_fee:.2f} + 附加 {quote.additional_fee:.2f} + 服务费 {quote.service_fee:.2f}）。"
            f"预计时效约 {quote.eta_minutes} 分钟，报价 {quote.valid_minutes} 分钟内有效，以下单页为准。"
        )

    async def compute_quote(self, parsed: QuoteParseResult) -> tuple[QuoteResult | None, str]:
        if not parsed.is_quote_intent:
            return None, "not_quote_intent"
        if parsed.missing_fields:
            return None, "missing_fields"

        mode = str(self.config.get("mode", "rule_only")).strip()
        if mode == "remote_then_rule":
            remote = await self._compute_remote_quote(parsed.request)
            if remote is not None:
                return remote, "remote"
            local = self._compute_rule_quote(parsed.request)
            return local, "fallback_rule"

        local = self._compute_rule_quote(parsed.request)
        return local, "rule"

    def _extract_destination_city(self, text: str) -> str | None:
        text = text or ""
        patterns = (
            r"(?:寄到|发到|送到|到)\s*([一-龥]{2,12}(?:省|市|区|县)?)",
            r"收件(?:地|地址)?[:：\s]*([一-龥]{2,12}(?:省|市|区|县)?)",
            r"目的地[:：\s]*([一-龥]{2,12}(?:省|市|区|县)?)",
        )
        for pattern in patterns:
            matched = re.search(pattern, text)
            if matched:
                return matched.group(1).strip()
        return None

    def _extract_weight_kg(self, text: str) -> float | None:
        text = text or ""
        matched = re.search(r"(\d+(?:\.\d+)?)\s*(kg|公斤|斤|g|克)", text, flags=re.IGNORECASE)
        if matched:
            value = float(matched.group(1))
            unit = matched.group(2).lower()
            if unit in {"kg", "公斤"}:
                return max(value, 0.1)
            if unit == "斤":
                return max(value * 0.5, 0.1)
            if unit in {"g", "克"}:
                return max(value / 1000.0, 0.1)

        fallback = re.search(r"重量[:：\s]*(\d+(?:\.\d+)?)", text)
        if fallback:
            return max(float(fallback.group(1)), 0.1)
        return None

    def _extract_pieces(self, text: str) -> int:
        text = text or ""
        matched = re.search(r"(\d+)\s*(?:件|票|单)", text)
        if matched:
            return max(int(matched.group(1)), 1)
        return 1

    def _is_urgency_request(self, text: str) -> bool:
        text = (text or "").lower()
        return any(keyword in text for keyword in self.URGENCY_KEYWORDS)

    async def _compute_remote_quote(self, request: QuoteRequest) -> QuoteResult | None:
        url = str(self.config.get("remote_api_url", "")).strip()
        if not url:
            return None

        timeout_seconds = int(self.config.get("timeout_seconds", 3))
        payload = {
            "origin_city": request.origin_city,
            "destination_city": request.destination_city,
            "weight_kg": request.weight_kg,
            "pieces": request.pieces,
            "urgency": request.urgency,
        }
        headers = {"Content-Type": "application/json"}
        api_key = str(self.config.get("remote_api_key", "")).strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code != 200:
                    self.logger.warning(f"Remote quote failed with status {response.status_code}")
                    return None
                data = response.json()
        except Exception as exc:
            self.logger.warning(f"Remote quote request error: {exc}")
            return None

        try:
            total_fee = float(data.get("total_fee"))
            base_fee = float(data.get("base_fee", 0.0))
            additional_fee = float(data.get("additional_fee", max(total_fee - base_fee, 0.0)))
            service_fee = float(data.get("service_fee", 0.0))
            eta_minutes = int(data.get("eta_minutes", self.config.get("eta_inter_city_minutes", 360)))
            return QuoteResult(
                total_fee=round(total_fee, 2),
                base_fee=round(base_fee, 2),
                additional_fee=round(additional_fee, 2),
                service_fee=round(service_fee, 2),
                eta_minutes=max(eta_minutes, 1),
                currency=str(data.get("currency", self.config.get("currency", "CNY"))),
                provider=str(data.get("provider", "remote_provider")),
                confidence=float(data.get("confidence", 0.95)),
                valid_minutes=int(data.get("valid_minutes", self.config.get("valid_minutes", 15))),
                explain=str(data.get("explain", "remote_quote")),
            )
        except (TypeError, ValueError) as exc:
            self.logger.warning(f"Remote quote data parse error: {exc}")
            return None

    def _compute_rule_quote(self, request: QuoteRequest) -> QuoteResult:
        first_weight = float(self.config.get("first_weight_kg", 1.0))
        first_price = float(self.config.get("first_price", 8.0))
        extra_per_kg = float(self.config.get("extra_per_kg", 2.5))
        service_fee = float(self.config.get("service_fee", 1.0))
        urgency_fee = float(self.config.get("urgency_fee", 4.0))
        inter_city_extra = float(self.config.get("inter_city_extra", 2.0))
        remote_extra = float(self.config.get("remote_extra", 6.0))
        valid_minutes = int(self.config.get("valid_minutes", 15))
        currency = str(self.config.get("currency", "CNY"))

        weight_kg = max(float(request.weight_kg or first_weight), 0.1)
        extra_weight = max(weight_kg - first_weight, 0.0)
        weight_fee = math.ceil(extra_weight) * extra_per_kg if extra_weight > 0 else 0.0

        additional_fee = weight_fee
        explain_parts = [f"首重{first_weight:.1f}kg内{first_price:.2f}元", f"续重费用{weight_fee:.2f}元"]

        same_city = self._is_same_city(request.origin_city, request.destination_city)
        if not same_city:
            additional_fee += inter_city_extra
            explain_parts.append(f"跨城附加{inter_city_extra:.2f}元")

        if self._is_remote_destination(request.destination_city):
            additional_fee += remote_extra
            explain_parts.append(f"偏远附加{remote_extra:.2f}元")

        if request.urgency:
            additional_fee += urgency_fee
            explain_parts.append(f"加急附加{urgency_fee:.2f}元")

        total_fee = round(first_price + additional_fee + service_fee, 2)
        eta_minutes = int(self.config.get("eta_same_city_minutes", 90) if same_city else self.config.get("eta_inter_city_minutes", 360))
        if request.urgency:
            eta_minutes = max(20, int(eta_minutes * 0.6))

        return QuoteResult(
            total_fee=total_fee,
            base_fee=round(first_price, 2),
            additional_fee=round(additional_fee, 2),
            service_fee=round(service_fee, 2),
            eta_minutes=eta_minutes,
            currency=currency,
            provider="rule_engine",
            confidence=0.85,
            valid_minutes=valid_minutes,
            explain="; ".join(explain_parts),
        )

    def _is_same_city(self, origin_city: str | None, destination_city: str | None) -> bool:
        if not origin_city or not destination_city:
            return False
        origin = self._compact_city(origin_city)
        destination = self._compact_city(destination_city)
        if origin == destination:
            return True
        return origin[:2] == destination[:2]

    def _is_remote_destination(self, destination_city: str | None) -> bool:
        if not destination_city:
            return False
        remote_keywords = [str(k).strip() for k in self.config.get("remote_keywords", []) if str(k).strip()]
        return any(keyword in destination_city for keyword in remote_keywords)

    @staticmethod
    def _compact_city(city: str) -> str:
        return re.sub(r"(省|市|区|县|自治区|特别行政区)$", "", city.strip())

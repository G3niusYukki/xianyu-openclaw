"""
自动报价服务
Quote Service
"""

from __future__ import annotations

import asyncio
import math
import re
from typing import Any

import httpx

from src.core.config import get_config
from src.core.logger import get_logger
from src.modules.quote.cost_table import CostRecord, CostTableRepository, normalize_courier_name
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
    PROFILE_KEYWORDS = {"member": ("会员", "vip"), "normal": ("普通", "散客")}

    COURIER_KEYWORDS = {
        "圆通": "圆通",
        "韵达": "韵达",
        "中通": "中通",
        "申通": "申通",
        "菜鸟": "菜鸟裹裹",
        "菜鸟裹裹": "菜鸟裹裹",
        "极兔": "极兔",
        "德邦": "德邦",
        "顺丰": "顺丰",
        "京东": "京东",
        "邮政": "邮政",
        "ems": "邮政",
    }

    def __init__(self, config: dict[str, Any] | None = None):
        app_config = get_config()
        self.config = config or app_config.get_section("quote", {})
        self.logger = get_logger()

        table_dir = str(self.config.get("cost_table_dir", "data/quote_costs"))
        table_patterns = self.config.get("cost_table_patterns", ["*.xlsx", "*.csv"])
        if not isinstance(table_patterns, list):
            table_patterns = ["*.xlsx", "*.csv"]
        self.cost_table_repo = CostTableRepository(table_dir=table_dir, include_patterns=table_patterns)

        preferred = self.config.get("preferred_couriers", [])
        if isinstance(preferred, list):
            self.preferred_couriers = {normalize_courier_name(str(item)) for item in preferred if str(item).strip()}
        else:
            self.preferred_couriers = set()

        self.default_profile = self._normalize_profile(self.config.get("pricing_profile"))

    def detect_quote_intent(self, message_text: str, item_title: str = "") -> bool:
        merged = f"{message_text or ''} {item_title or ''}".lower()
        return any(keyword in merged for keyword in self.QUOTE_KEYWORDS)

    def parse_quote_request(self, message_text: str, item_title: str = "") -> QuoteParseResult:
        message_text = message_text or ""
        merged = f"{message_text} {item_title}".strip()
        is_quote_intent = self.detect_quote_intent(message_text, item_title=item_title)

        route_origin, route_destination = self._extract_route(message_text)
        destination = route_destination or self._extract_destination_city(message_text)
        weight_kg = self._extract_weight_kg(message_text)
        pieces = self._extract_pieces(message_text)
        urgency = self._is_urgency_request(message_text)
        origin_city = route_origin or self._extract_origin_city(message_text) or str(self.config.get("origin_city", "杭州"))
        courier = self._extract_courier(merged)
        profile = self._extract_profile(merged)

        request = QuoteRequest(
            destination_city=destination,
            weight_kg=weight_kg,
            pieces=pieces,
            urgency=urgency,
            origin_city=origin_city,
            courier=courier,
            profile=profile,
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
        pieces_text = f"，{request.pieces}件" if request.pieces and request.pieces > 1 else ""
        courier_text = f"，渠道{quote.courier}" if quote.courier else ""
        return (
            f"报价结果：寄往{destination}，{weight_text}{pieces_text}，{speed_text}{courier_text}。"
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

        if mode == "cost_table_plus_markup":
            table_quote = self._compute_cost_table_quote(parsed.request)
            if table_quote is not None:
                return table_quote, "cost_table"
            local = self._compute_rule_quote(parsed.request)
            return local, "fallback_rule"

        if mode == "api_cost_plus_markup":
            if self._is_api_parallel_fallback_enabled():
                quote, source = await self._compute_api_cost_quote_with_fast_fallback(parsed.request)
                if quote is not None:
                    return quote, source
            api_quote = await self._compute_api_cost_markup_quote(parsed.request)
            if api_quote is not None:
                return api_quote, "api_cost_markup"
            table_quote = self._compute_cost_table_quote(parsed.request)
            if table_quote is not None:
                return table_quote, "fallback_cost_table"
            local = self._compute_rule_quote(parsed.request)
            return local, "fallback_rule"

        local = self._compute_rule_quote(parsed.request)
        return local, "rule"

    async def _compute_api_cost_quote_with_fast_fallback(self, request: QuoteRequest) -> tuple[QuoteResult | None, str]:
        """API 成本价优先，超时快速回退本地成本表。"""
        wait_seconds = self._resolve_api_prefer_wait_seconds()
        table_quote = self._compute_cost_table_quote(request)
        api_task = asyncio.create_task(self._compute_api_cost_markup_quote(request))

        timed_out = False
        api_quote: QuoteResult | None = None
        try:
            api_quote = await asyncio.wait_for(asyncio.shield(api_task), timeout=wait_seconds)
        except asyncio.TimeoutError:
            timed_out = True
        except Exception as exc:
            self.logger.warning(f"API cost fast-path failed: {exc}")

        if api_quote is not None:
            return api_quote, "api_cost_markup"

        if table_quote is not None:
            if not api_task.done():
                api_task.cancel()
            return table_quote, "fallback_cost_table_fast" if timed_out else "fallback_cost_table"

        if not api_task.done():
            try:
                api_quote = await api_task
            except asyncio.CancelledError:
                api_quote = None
            except Exception as exc:
                self.logger.warning(f"API cost fallback failed: {exc}")
                api_quote = None
        else:
            try:
                api_quote = api_task.result()
            except Exception:
                api_quote = None

        if api_quote is not None:
            return api_quote, "api_cost_markup"
        return None, "api_cost_unavailable"

    def _extract_route(self, text: str) -> tuple[str | None, str | None]:
        text = text or ""
        pattern = (
            r"(?:从|由)\s*([一-龥]{2,20}?)\s*"
            r"(?:寄到|发到|送到|到)\s*([一-龥]{2,20}(?:省|市|区|县|自治区|特别行政区|自治州|地区)?)"
        )
        matched = re.search(pattern, text)
        if not matched:
            return None, None
        return matched.group(1).strip(), matched.group(2).strip()

    def _extract_origin_city(self, text: str) -> str | None:
        text = text or ""
        patterns = (
            r"(?:从|由|寄自|发自)\s*([一-龥]{2,20}(?:省|市|区|县|自治区|特别行政区|自治州|地区)?)",
            r"寄件(?:地|地址)?[:：\s]*([一-龥]{2,20}(?:省|市|区|县|自治区|特别行政区|自治州|地区)?)",
            r"始发地[:：\s]*([一-龥]{2,20}(?:省|市|区|县|自治区|特别行政区|自治州|地区)?)",
        )
        for pattern in patterns:
            matched = re.search(pattern, text)
            if matched:
                return matched.group(1).strip()
        return None

    def _extract_destination_city(self, text: str) -> str | None:
        text = text or ""
        patterns = (
            r"(?:寄到|发到|送到|到)\s*([一-龥]{2,20}(?:省|市|区|县|自治区|特别行政区|自治州|地区)?)",
            r"收件(?:地|地址)?[:：\s]*([一-龥]{2,20}(?:省|市|区|县|自治区|特别行政区|自治州|地区)?)",
            r"目的地[:：\s]*([一-龥]{2,20}(?:省|市|区|县|自治区|特别行政区|自治州|地区)?)",
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

    def _extract_courier(self, text: str) -> str | None:
        merged = (text or "").lower()
        for keyword, normalized in sorted(self.COURIER_KEYWORDS.items(), key=lambda item: len(item[0]), reverse=True):
            if keyword.lower() in merged:
                return normalize_courier_name(normalized)
        return None

    def _extract_profile(self, text: str) -> str:
        merged = (text or "").lower()
        for profile, keywords in self.PROFILE_KEYWORDS.items():
            if any(keyword in merged for keyword in keywords):
                return profile
        return self.default_profile

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
            "courier": request.courier,
            "profile": request.profile or self.default_profile,
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
                courier=normalize_courier_name(data.get("courier")),
                confidence=float(data.get("confidence", 0.95)),
                valid_minutes=int(data.get("valid_minutes", self.config.get("valid_minutes", 15))),
                explain=str(data.get("explain", "remote_quote")),
            )
        except (TypeError, ValueError) as exc:
            self.logger.warning(f"Remote quote data parse error: {exc}")
            return None

    def _compute_cost_table_quote(self, request: QuoteRequest) -> QuoteResult | None:
        if not request.origin_city or not request.destination_city:
            return None

        records = self.cost_table_repo.find_candidates(
            origin=request.origin_city,
            destination=request.destination_city,
            courier=request.courier,
            limit=64,
        )
        if not records:
            return None

        if self.preferred_couriers and not request.courier:
            preferred_records = [record for record in records if normalize_courier_name(record.courier) in self.preferred_couriers]
            if preferred_records:
                records = preferred_records

        quotes = [self._build_markup_quote_from_cost(request, record, provider="cost_table") for record in records]
        if not quotes:
            return None
        return min(quotes, key=lambda item: item.total_fee)

    async def _compute_api_cost_markup_quote(self, request: QuoteRequest) -> QuoteResult | None:
        records = await self._fetch_remote_cost_candidates(request)
        if not records:
            return None

        quotes = [self._build_markup_quote_from_cost(request, record, provider="api_cost") for record in records]
        if not quotes:
            return None
        return min(quotes, key=lambda item: item.total_fee)

    def _is_api_parallel_fallback_enabled(self) -> bool:
        return bool(self.config.get("api_fallback_to_table_parallel", True))

    def _resolve_api_prefer_wait_seconds(self) -> float:
        raw = self.config.get("api_prefer_max_wait_seconds", 1.2)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return 1.2
        return max(0.1, min(value, 10.0))

    async def _fetch_remote_cost_candidates(self, request: QuoteRequest) -> list[CostRecord]:
        url = str(self.config.get("cost_api_url", "")).strip()
        if not url:
            return []

        timeout_seconds = int(self.config.get("cost_api_timeout_seconds", self.config.get("timeout_seconds", 3)))
        payload = {
            "origin_city": request.origin_city,
            "destination_city": request.destination_city,
            "weight_kg": request.weight_kg,
            "pieces": request.pieces,
            "urgency": request.urgency,
            "courier": request.courier,
            "profile": request.profile or self.default_profile,
        }

        headers: dict[str, str] = {"Content-Type": "application/json"}
        api_key = str(self.config.get("cost_api_key", "") or self.config.get("remote_api_key", "")).strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        extra_headers = self.config.get("cost_api_headers", {})
        if isinstance(extra_headers, dict):
            for key, value in extra_headers.items():
                headers[str(key)] = str(value)

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code != 200:
                    self.logger.warning(f"Cost API quote failed with status {response.status_code}")
                    return []
                data = response.json()
        except Exception as exc:
            self.logger.warning(f"Cost API request error: {exc}")
            return []

        records = self._parse_remote_cost_candidates(data, request)
        if request.courier:
            requested = normalize_courier_name(request.courier)
            matched = [record for record in records if normalize_courier_name(record.courier) == requested]
            if matched:
                return matched
        return records

    def _parse_remote_cost_candidates(self, data: Any, request: QuoteRequest) -> list[CostRecord]:
        candidates_data: list[dict[str, Any]] = []
        if isinstance(data, list):
            candidates_data = [item for item in data if isinstance(item, dict)]
        elif isinstance(data, dict):
            payload = data.get("candidates")
            if not isinstance(payload, list):
                payload = data.get("costs")
            if not isinstance(payload, list):
                payload = data.get("data")
            if isinstance(payload, list):
                candidates_data = [item for item in payload if isinstance(item, dict)]
            else:
                candidates_data = [data]

        records: list[CostRecord] = []
        for raw in candidates_data:
            record = self._parse_remote_cost_record(raw, request)
            if record is not None:
                records.append(record)

        records.sort(key=lambda item: (item.first_cost + item.extra_cost, item.first_cost))
        return records

    def _parse_remote_cost_record(self, payload: dict[str, Any], request: QuoteRequest) -> CostRecord | None:
        courier = self._pick_text(payload, "courier", "company", "carrier", "express")
        origin = self._pick_text(payload, "origin_city", "origin", "from_city", "from") or request.origin_city
        destination = (
            self._pick_text(payload, "destination_city", "destination", "to_city", "to")
            or request.destination_city
        )
        first_cost = self._pick_number(payload, "first_cost", "cost_first", "first_weight_cost", "base_cost", "first")
        extra_cost = self._pick_number(payload, "extra_cost", "cost_extra", "extra_weight_cost", "second_cost", "extra")
        throw_ratio = self._pick_number(payload, "throw_ratio", "volume_ratio", "volumetric_ratio")

        if not origin or not destination or first_cost is None or extra_cost is None:
            return None

        return CostRecord(
            courier=normalize_courier_name(courier or request.courier or "快递"),
            origin=str(origin).strip(),
            destination=str(destination).strip(),
            first_cost=float(first_cost),
            extra_cost=float(extra_cost),
            throw_ratio=throw_ratio,
            source_file="api",
            source_sheet="cost",
        )

    def _build_markup_quote_from_cost(self, request: QuoteRequest, cost: CostRecord, provider: str) -> QuoteResult:
        first_weight = max(float(self.config.get("first_weight_kg", 1.0)), 0.1)
        weight_kg = max(float(request.weight_kg or first_weight), 0.1)
        pieces = max(int(request.pieces or 1), 1)
        profile = self._normalize_profile(request.profile)

        first_add, extra_add = self._resolve_markup(cost.courier, profile)
        extra_steps = math.ceil(max(weight_kg - first_weight, 0.0))

        base_fee = pieces * (float(cost.first_cost) + first_add)
        additional_fee = pieces * extra_steps * (float(cost.extra_cost) + extra_add)

        service_fee = float(self.config.get("service_fee", 1.0))
        if request.urgency:
            service_fee += float(self.config.get("urgency_fee", 4.0))

        total_fee = round(base_fee + additional_fee + service_fee, 2)
        same_city = self._is_same_city(request.origin_city, request.destination_city)
        eta_minutes = int(self.config.get("eta_same_city_minutes", 90) if same_city else self.config.get("eta_inter_city_minutes", 360))
        if request.urgency:
            eta_minutes = max(20, int(eta_minutes * 0.6))

        explain = (
            f"来源{provider}; 成本首重{cost.first_cost:.2f}元/续重{cost.extra_cost:.2f}元; "
            f"加价策略({profile}) 首重+{first_add:.2f}/续重+{extra_add:.2f}; "
            f"件数{pieces}; 续重计费段{extra_steps}"
        )
        return QuoteResult(
            total_fee=total_fee,
            base_fee=round(base_fee, 2),
            additional_fee=round(additional_fee, 2),
            service_fee=round(service_fee, 2),
            eta_minutes=eta_minutes,
            currency=str(self.config.get("currency", "CNY")),
            provider=provider,
            courier=normalize_courier_name(cost.courier),
            confidence=0.94 if provider == "api_cost" else 0.91,
            valid_minutes=int(self.config.get("valid_minutes", 15)),
            explain=explain,
        )

    def _resolve_markup(self, courier: str, profile: str) -> tuple[float, float]:
        rules = self._get_markup_rules()
        default_rule = rules.get("default", {})

        courier_rule: dict[str, Any] = {}
        normalized = normalize_courier_name(courier)
        for key, value in rules.items():
            if key == "default" or not isinstance(value, dict):
                continue
            if normalize_courier_name(key) == normalized:
                courier_rule = value
                break

        if profile == "member":
            first_keys = ("member_first_add", "vip_first_add", "first_add_member", "first_add")
            extra_keys = ("member_extra_add", "vip_extra_add", "extra_add_member", "extra_add")
        else:
            first_keys = ("normal_first_add", "first_add_normal", "first_add")
            extra_keys = ("normal_extra_add", "extra_add_normal", "extra_add")

        first_add = self._pick_float_from_rule(courier_rule, first_keys, default=self._pick_float_from_rule(default_rule, first_keys, 0.0))
        extra_add = self._pick_float_from_rule(courier_rule, extra_keys, default=self._pick_float_from_rule(default_rule, extra_keys, 0.0))
        return first_add, extra_add

    def _get_markup_rules(self) -> dict[str, dict[str, Any]]:
        rules = self.config.get("markup_rules", {})
        if not isinstance(rules, dict):
            rules = {}

        legacy = self.config.get("courier_markup", {})
        if isinstance(legacy, dict):
            merged: dict[str, dict[str, Any]] = {}
            for key, value in rules.items():
                if isinstance(value, dict):
                    merged[str(key)] = value
            for key, value in legacy.items():
                if isinstance(value, dict):
                    merged[str(key)] = value
            return merged

        return {str(key): value for key, value in rules.items() if isinstance(value, dict)}

    @staticmethod
    def _pick_float_from_rule(rule: dict[str, Any], keys: tuple[str, ...], default: float) -> float:
        for key in keys:
            value = rule.get(key)
            try:
                if value is not None:
                    return float(value)
            except (TypeError, ValueError):
                continue
        return float(default)

    @staticmethod
    def _pick_text(payload: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = payload.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return ""

    @staticmethod
    def _pick_number(payload: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            value = payload.get(key)
            if value is None:
                continue
            if isinstance(value, (int, float)):
                return float(value)
            text = str(value).strip()
            if not text:
                continue
            match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
            if not match:
                continue
            try:
                return float(match.group(0))
            except ValueError:
                continue
        return None

    def _normalize_profile(self, profile: Any) -> str:
        profile_text = str(profile or "").strip().lower()
        if profile_text in {"member", "vip", "会员"}:
            return "member"
        if profile_text in {"normal", "普通"}:
            return "normal"
        return "normal"

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

        pieces = max(int(request.pieces or 1), 1)
        weight_kg = max(float(request.weight_kg or first_weight), 0.1)
        extra_weight = max(weight_kg - first_weight, 0.0)
        weight_fee = math.ceil(extra_weight) * extra_per_kg if extra_weight > 0 else 0.0

        single_base_fee = first_price
        single_additional_fee = weight_fee
        explain_parts = [f"首重{first_weight:.1f}kg内{first_price:.2f}元", f"续重费用{weight_fee:.2f}元"]

        same_city = self._is_same_city(request.origin_city, request.destination_city)
        if not same_city:
            single_additional_fee += inter_city_extra
            explain_parts.append(f"跨城附加{inter_city_extra:.2f}元")

        if self._is_remote_destination(request.destination_city):
            single_additional_fee += remote_extra
            explain_parts.append(f"偏远附加{remote_extra:.2f}元")

        if request.urgency:
            single_additional_fee += urgency_fee
            explain_parts.append(f"加急附加{urgency_fee:.2f}元")

        base_fee = pieces * single_base_fee
        additional_fee = pieces * single_additional_fee
        total_fee = round(base_fee + additional_fee + service_fee, 2)

        eta_minutes = int(self.config.get("eta_same_city_minutes", 90) if same_city else self.config.get("eta_inter_city_minutes", 360))
        if request.urgency:
            eta_minutes = max(20, int(eta_minutes * 0.6))

        return QuoteResult(
            total_fee=total_fee,
            base_fee=round(base_fee, 2),
            additional_fee=round(additional_fee, 2),
            service_fee=round(service_fee, 2),
            eta_minutes=eta_minutes,
            currency=currency,
            provider="rule_engine",
            courier=normalize_courier_name(request.courier),
            confidence=0.85,
            valid_minutes=valid_minutes,
            explain="; ".join(explain_parts) + f"; 件数{pieces}",
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
        remote_keywords = [str(item).strip() for item in self.config.get("remote_keywords", []) if str(item).strip()]
        return any(keyword in destination_city for keyword in remote_keywords)

    @staticmethod
    def _compact_city(city: str) -> str:
        return re.sub(r"(省|市|区|县|自治区|特别行政区)$", "", city.strip())

"""
闲鱼消息服务
Messages Service

提供站内会话读取、自动回复与自动报价能力。
"""

import asyncio
import json
import os
import random
import re
import time
from pathlib import Path
from time import perf_counter
from typing import Any

from src.core.compliance import get_compliance_guard
from src.core.config import get_config
from src.core.error_handler import BrowserError
from src.core.logger import get_logger
from src.modules.compliance.center import ComplianceCenter
from src.modules.messages.reply_engine import ReplyStrategyEngine
from src.modules.quote.engine import AutoQuoteEngine
from src.modules.quote.models import QuoteRequest, QuoteResult
from src.modules.quote.providers import QuoteProviderError


class MessageSelectors:
    """消息页选择器。"""

    MESSAGE_PAGE = "https://www.goofish.com/im"

    SESSION_LIST = "[class*='session'], [class*='conversation'], [data-session-id]"
    MESSAGE_INPUT = "textarea, [contenteditable='true'], input[placeholder*='消息']"
    SEND_BUTTON = "button:has-text('发送'), button:has-text('Send'), [class*='send']"


DEFAULT_WEIGHT_REPLY_TEMPLATE = (
    "{origin_province}到{dest_province} {billing_weight}kg 首单价格\n"
    "{courier}: {price} 元\n"
    "预计时效：{eta_days}\n"
    "重要提示：\n"
    "体积重大于实际重量时按体积计费！"
)

DEFAULT_VOLUME_REPLY_TEMPLATE = (
    "{origin_province}到{dest_province} {billing_weight}kg 首单价格\n"
    "体积重规则：{volume_formula}\n"
    "{courier}: {price} 元\n"
    "预计时效：{eta_days}\n"
    "重要提示：\n"
    "体积重大于实际重量时按体积计费！"
)


class MessagesService:
    """闲鱼会话自动回复服务。"""

    def __init__(self, controller=None, config: dict[str, Any] | None = None):
        self.controller = controller
        self.logger = get_logger()

        app_config = get_config()
        self.config = config or app_config.get_section("messages", {})
        self.quote_config = {
            **app_config.get_section("quote", {}),
            **self.config.get("quote", {}),
        }
        self.transport_mode = self._normalized_transport_mode(self.config.get("transport", "dom"))
        self.ws_config = self.config.get("ws", {}) if isinstance(self.config.get("ws"), dict) else {}
        self._ws_transport: Any | None = None
        self._ws_unavailable_reason = ""
        self._reply_templates_path = self._resolve_reply_templates_path()
        self._reply_templates_cache: dict[str, str] = {
            "weight_template": DEFAULT_WEIGHT_REPLY_TEMPLATE,
            "volume_template": DEFAULT_VOLUME_REPLY_TEMPLATE,
        }
        self._reply_templates_mtime: float = -1.0

        browser_config = app_config.browser
        self.delay_range = (
            browser_config.get("delay", {}).get("min", 1),
            browser_config.get("delay", {}).get("max", 3),
        )

        self.fast_reply_enabled = bool(self.config.get("fast_reply_enabled", False))
        self.reply_target_seconds = float(self.config.get("reply_target_seconds", 3.0))
        self.reuse_message_page = bool(self.config.get("reuse_message_page", True))
        self.first_reply_delay_seconds = tuple(self.config.get("first_reply_delay_seconds", [0.25, 0.9]))
        self.inter_reply_delay_seconds = tuple(self.config.get("inter_reply_delay_seconds", [0.4, 1.2]))
        self.send_confirm_delay_seconds = tuple(self.config.get("send_confirm_delay_seconds", [0.15, 0.35]))

        self.reply_prefix = self.config.get("reply_prefix", "")
        self.default_reply = self.config.get("default_reply", "您好，宝贝在的，感兴趣可以直接拍下。")
        self.virtual_default_reply = self.config.get(
            "virtual_default_reply",
            "在的，这是虚拟商品，拍下后会尽快在聊天内给你处理结果。",
        )
        self.max_replies_per_run = int(self.config.get("max_replies_per_run", 10))

        self.keyword_replies: dict[str, str] = {
            "还在": "在的，商品还在，直接拍就可以。",
            "在吗": "在的，有需要可以直接下单。",
            "最低": "价格已经尽量实在了，诚心要的话可以小刀。",
            "便宜": "价格是参考同款成色定的，诚心要可以聊。",
            "包邮": "默认不包邮，具体看地区可以商量。",
            "瑕疵": "有正常使用痕迹，主要细节我都拍在图里了。",
            "发票": "如需发票或购买凭证，我可以帮你再确认一下。",
            "验货": "支持走闲鱼平台流程，验货后确认收货更安心。",
            "自提": "可以自提，时间地点可以私聊约。",
        }

        custom_keywords = self.config.get("keyword_replies", {})
        if isinstance(custom_keywords, dict):
            self.keyword_replies.update({str(k): str(v) for k, v in custom_keywords.items()})

        self.reply_engine = ReplyStrategyEngine(
            default_reply=self.default_reply,
            virtual_default_reply=self.virtual_default_reply,
            reply_prefix=self.reply_prefix,
            keyword_replies=self.keyword_replies,
            intent_rules=self.config.get("intent_rules", []),
            virtual_product_keywords=self.config.get("virtual_product_keywords", []),
        )

        self.quote_engine = AutoQuoteEngine(self.quote_config)
        default_quote_keywords = ["报价", "多少钱", "价格", "运费", "邮费", "快递费", "寄到", "发到", "送到", "怎么寄"]
        default_standard_format_triggers = ["你好", "您好", "在吗", "在不", "hi", "hello", "哈喽", "有人吗"]
        raw_quote_keywords = self.config.get("quote_intent_keywords")
        if isinstance(raw_quote_keywords, list):
            cleaned_quote_keywords = [
                str(s).strip().lower()
                for s in raw_quote_keywords
                if str(s).strip() and len(str(s).strip()) >= 2
            ]
        else:
            cleaned_quote_keywords = []
        self.quote_intent_keywords = cleaned_quote_keywords or [str(s).lower() for s in default_quote_keywords]
        raw_standard_triggers = self.config.get("standard_format_trigger_keywords")
        if isinstance(raw_standard_triggers, list):
            cleaned_standard_triggers = [
                str(s).strip().lower()
                for s in raw_standard_triggers
                if str(s).strip() and len(str(s).strip()) >= 2
            ]
        else:
            cleaned_standard_triggers = []
        self.standard_format_trigger_keywords = cleaned_standard_triggers or [
            str(s).lower() for s in default_standard_format_triggers
        ]
        self.quote_missing_prompts = {
            "origin": "寄件城市",
            "destination": "收件城市",
            "weight": "包裹重量（kg）",
        }
        self.quote_missing_template = self.config.get(
            "quote_missing_template",
            "询价格式：xx省 - xx省 - 重量（kg）\n长宽高（单位cm）",
        )
        self.strict_format_reply_enabled = bool(self.config.get("strict_format_reply_enabled", False))
        self.quote_reply_all_couriers = bool(self.config.get("quote_reply_all_couriers", True))
        self.quote_reply_max_couriers = max(1, int(self.config.get("quote_reply_max_couriers", 10)))
        self.quote_failed_template = self.config.get(
            "quote_failed_template",
            "报价服务暂时繁忙，我先帮您转人工确认，确保价格准确。",
        )

        self.compliance_guard = get_compliance_guard()
        self.compliance_center = ComplianceCenter()
        self.high_risk_keywords = [
            "加微信",
            "vx",
            "v信",
            "qq",
            "私下交易",
            "站外",
            "转账",
            "逼单",
        ]
        self.safe_fallback_reply = "建议您全程在闲鱼站内交易沟通，我这边可继续为您提供合规报价与服务说明。"

        self.selectors = MessageSelectors()

    @staticmethod
    def _normalized_transport_mode(raw_mode: Any) -> str:
        mode = str(raw_mode or "ws").strip().lower()
        if mode not in {"dom", "ws", "auto"}:
            return "ws"
        return mode

    def _resolve_ws_cookie(self) -> str:
        raw_cookie = str(self.config.get("cookie", "") or "").strip()
        if raw_cookie:
            return raw_cookie

        env_cookie = str(os.getenv("XIANYU_COOKIE_1", "") or "").strip()
        if env_cookie:
            return env_cookie

        app_config = get_config()
        for account in app_config.accounts:
            if bool(account.get("enabled", True)):
                cookie = str(account.get("cookie", "") or "").strip()
                if cookie:
                    return cookie
        return ""

    def _resolve_reply_templates_path(self) -> Path:
        app_config = get_config()
        content_cfg = app_config.get_section("content", {})
        templates_cfg = content_cfg.get("templates", {}) if isinstance(content_cfg, dict) else {}
        if not isinstance(templates_cfg, dict):
            templates_cfg = {}
        raw_template_dir = str(templates_cfg.get("path") or "config/templates")
        root = Path(__file__).resolve().parents[3]
        template_dir = Path(raw_template_dir)
        if not template_dir.is_absolute():
            template_dir = root / template_dir
        return template_dir / "reply_templates.json"

    def _load_reply_templates(self) -> dict[str, str]:
        path = self._reply_templates_path
        if not path.exists():
            return self._reply_templates_cache

        try:
            mtime = float(path.stat().st_mtime)
        except OSError:
            return self._reply_templates_cache

        if abs(mtime - self._reply_templates_mtime) < 1e-6:
            return self._reply_templates_cache

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            weight = str(raw.get("weight_template") or DEFAULT_WEIGHT_REPLY_TEMPLATE).strip()
            volume = str(raw.get("volume_template") or DEFAULT_VOLUME_REPLY_TEMPLATE).strip()
            self._reply_templates_cache = {
                "weight_template": weight or DEFAULT_WEIGHT_REPLY_TEMPLATE,
                "volume_template": volume or DEFAULT_VOLUME_REPLY_TEMPLATE,
            }
            self._reply_templates_mtime = mtime
        except Exception as exc:
            self.logger.warning("Load reply templates failed: %s", exc)
        return self._reply_templates_cache

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _select_quote_reply_template(self, explain: dict[str, Any]) -> str:
        templates = self._load_reply_templates()
        actual_weight = self._safe_float(explain.get("actual_weight_kg"))
        billing_weight = self._safe_float(explain.get("billing_weight_kg"))
        use_volume_template = billing_weight > (actual_weight + 1e-6)
        return templates["volume_template"] if use_volume_template else templates["weight_template"]

    @staticmethod
    def _format_eta_days(minutes: int | float | None) -> str:
        try:
            raw = float(minutes or 0)
        except (TypeError, ValueError):
            raw = 0.0
        if raw <= 0:
            return "1天"
        days = max(1.0, raw / 1440.0)
        rounded = round(days, 1)
        if abs(rounded - round(rounded)) < 1e-9:
            return f"{int(round(rounded))}天"
        return f"{rounded:.1f}天"

    def _resolve_quote_candidate_couriers(self, request: QuoteRequest) -> list[str]:
        couriers: list[str] = []
        seen: set[str] = set()

        preferred = self.quote_config.get("preferred_couriers", [])
        if isinstance(preferred, list):
            for item in preferred:
                name = str(item or "").strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                couriers.append(name)

        provider = getattr(self.quote_engine, "cost_table_provider", None)
        repo = getattr(provider, "repo", None)
        if repo is not None:
            try:
                rows = repo.find_candidates(
                    origin=request.origin,
                    destination=request.destination,
                    courier=None,
                    limit=max(24, self.quote_reply_max_couriers * 8),
                )
                for row in rows:
                    name = str(getattr(row, "courier", "") or "").strip()
                    if not name or name in seen:
                        continue
                    seen.add(name)
                    couriers.append(name)
            except Exception as exc:
                self.logger.warning("Resolve candidate couriers failed: %s", exc)

        return couriers[: self.quote_reply_max_couriers]

    async def _quote_all_couriers(self, request: QuoteRequest) -> list[tuple[str, QuoteResult]]:
        couriers = self._resolve_quote_candidate_couriers(request)
        if not couriers:
            return []

        async def _one(courier_name: str) -> tuple[str, QuoteResult | None]:
            sub_request = QuoteRequest(
                origin=request.origin,
                destination=request.destination,
                weight=request.weight,
                volume=request.volume,
                volume_weight=request.volume_weight,
                service_level=request.service_level,
                courier=courier_name,
                item_type=request.item_type,
                time_window=request.time_window,
            )
            try:
                result = await self.quote_engine.get_quote(sub_request)
                return courier_name, result
            except Exception:
                return courier_name, None

        pairs = await asyncio.gather(*[_one(name) for name in couriers])
        ok_pairs: list[tuple[str, QuoteResult]] = []
        for courier_name, result in pairs:
            if result is None:
                continue
            ok_pairs.append((courier_name, result))
        ok_pairs.sort(key=lambda item: (float(item[1].total_fee), str(item[0])))
        return ok_pairs

    def _compose_multi_courier_quote_reply(self, quote_rows: list[tuple[str, QuoteResult]]) -> str:
        if not quote_rows:
            return ""

        first_explain = quote_rows[0][1].explain if isinstance(quote_rows[0][1].explain, dict) else {}
        origin = str(first_explain.get("matched_origin") or first_explain.get("normalized_origin") or "寄件地")
        destination = str(first_explain.get("matched_destination") or first_explain.get("normalized_destination") or "收件地")

        lines = [f"{origin} -> {destination} 可选快递报价（可自行挑选）："]
        for index, (courier_name, result) in enumerate(quote_rows, start=1):
            eta = self._format_eta_days(result.eta_minutes)
            lines.append(f"{index}. {courier_name}：{float(result.total_fee):.2f}元（预计{eta}）")
        lines.append("回复“选XX快递”即可按对应渠道安排。")
        return "\n".join(lines)

    def _should_use_ws_transport(self) -> bool:
        if self.transport_mode == "ws":
            return True
        if self.transport_mode == "auto":
            return bool(self._resolve_ws_cookie())
        return False

    async def _ensure_ws_transport(self) -> Any | None:
        if not self._should_use_ws_transport():
            return None
        if self._ws_transport is not None:
            return self._ws_transport
        if self._ws_unavailable_reason:
            if self.transport_mode == "ws":
                raise BrowserError(self._ws_unavailable_reason)
            return None

        cookie_text = self._resolve_ws_cookie()
        if not cookie_text:
            msg = "WebSocket transport requires XIANYU_COOKIE_1 (or messages.cookie)."
            if self.transport_mode == "ws":
                raise BrowserError(msg)
            self._ws_unavailable_reason = msg
            return None

        try:
            from src.modules.messages.ws_live import GoofishWsTransport

            self._ws_transport = GoofishWsTransport(
                cookie_text=cookie_text,
                config=self.ws_config,
                cookie_supplier=self._resolve_ws_cookie,
            )
            await self._ws_transport.start()
            self.logger.info("MessagesService WebSocket transport enabled")
            return self._ws_transport
        except Exception as exc:
            self._ws_unavailable_reason = str(exc)
            if self.transport_mode == "ws":
                raise BrowserError(f"Failed to initialize WebSocket transport: {exc}") from exc
            self.logger.warning(f"WebSocket transport unavailable, fallback to DOM transport: {exc}")
            return None

    async def close(self) -> None:
        if self._ws_transport is not None:
            try:
                await self._ws_transport.stop()
            except Exception:
                pass
            self._ws_transport = None

    def _random_delay(self, min_factor: float = 1.0, max_factor: float = 1.0) -> float:
        min_delay = self.delay_range[0] * min_factor
        max_delay = self.delay_range[1] * max_factor
        return random.uniform(min_delay, max_delay)

    @staticmethod
    def _random_range(delay_range: tuple[float, float], fallback: tuple[float, float]) -> float:
        low, high = fallback
        if len(delay_range) == 2:
            low = float(delay_range[0])
            high = float(delay_range[1])
        return random.uniform(min(low, high), max(low, high))

    async def _ensure_message_page(self, page_id: str) -> None:
        await self.controller.navigate(page_id, self.selectors.MESSAGE_PAGE)

    async def _get_unread_sessions_dom(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.controller:
            raise BrowserError("Browser controller is not initialized. Cannot fetch unread sessions.")

        page_id = await self.controller.new_page()
        try:
            await self._ensure_message_page(page_id)
            await asyncio.sleep(self._random_delay(0.6, 1.1))

            script = f"""
(() => {{
  const nodes = Array.from(
    document.querySelectorAll("[data-session-id], [class*='session'], [class*='conversation'], li")
  );
  const result = [];

  for (const node of nodes) {{
    const text = (node.innerText || "").trim();
    if (!text) continue;

    const unreadEl = node.querySelector("[class*='unread'], [class*='badge'], [class*='count']");
    const unreadText = (unreadEl?.innerText || "").trim();
    const unreadCount = Number((unreadText.match(/\\d+/) || ["0"])[0]);

    if (unreadCount <= 0) continue;

    const lines = text.split("\\n").map(s => s.trim()).filter(Boolean);
    const sessionId = node.getAttribute("data-session-id")
      || node.dataset?.sessionId
      || node.getAttribute("data-id")
      || `session_${{result.length + 1}}`;

    result.push({{
      session_id: sessionId,
      peer_name: lines[0] || "买家",
      item_title: lines.length > 2 ? lines[1] : "",
      last_message: lines[lines.length - 1] || "",
      unread_count: unreadCount,
    }});

    if (result.length >= {max(limit, 1)}) break;
  }}

  return result;
}})();
"""
            data = await self.controller.execute_script(page_id, script)
            if isinstance(data, list):
                return data
            return []
        finally:
            await self.controller.close_page(page_id)

    async def get_unread_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        """读取未读会话。"""
        ws_transport = await self._ensure_ws_transport()
        if ws_transport is not None:
            ws_result = await ws_transport.get_unread_sessions(limit=limit)
            if ws_result or not self.controller:
                return ws_result
            ws_ready = True
            try:
                ready_fn = getattr(ws_transport, "is_ready", None)
                if callable(ready_fn):
                    ws_ready = bool(ready_fn())
            except Exception:
                ws_ready = True
            if not ws_ready:
                if self.transport_mode == "auto":
                    self.logger.warning("WebSocket unread pull unavailable, fallback to DOM session scan")
                    return await self._get_unread_sessions_dom(limit=limit)
                return ws_result
            if self.transport_mode == "auto":
                return await self._get_unread_sessions_dom(limit=limit)
            return ws_result

        return await self._get_unread_sessions_dom(limit=limit)

    def _is_quote_request(self, message_text: str) -> bool:
        text = (message_text or "").strip().lower()
        if not text:
            return False

        if any(keyword in text for keyword in self.quote_intent_keywords):
            return True

        has_weight = bool(re.search(r"\d+(?:\.\d+)?\s*(kg|公斤|斤|g|克)\b", text, flags=re.IGNORECASE))
        if not has_weight:
            return False

        if any(p in text for p in ["到货", "多久到", "什么时候到", "到没", "到了吗", "到哪了"]):
            if not any(marker in text for marker in ["寄", "发", "收", "从", "由", "~", "～", "-", "—"]):
                return False

        route_patterns = (
            r"[\u4e00-\u9fa5]{2,20}\s*(?:到|寄到|发到|送到)\s*[\u4e00-\u9fa5]{2,20}",
            r"(?:寄件|发件|收件|寄自|发自|从|由)",
            r"[\u4e00-\u9fa5]{2,20}\s*[~～\-—]\s*[\u4e00-\u9fa5]{2,20}",
        )
        return any(re.search(pattern, text) for pattern in route_patterns)

    def _is_standard_format_trigger(self, message_text: str) -> bool:
        text = (message_text or "").strip().lower()
        if not text:
            return False
        compact_text = re.sub(r"\s+", "", text)
        return any(keyword in compact_text for keyword in self.standard_format_trigger_keywords)

    @staticmethod
    def _extract_weight_kg(message_text: str) -> float | None:
        text = message_text or ""
        m = re.search(r"(\d+(?:\.\d+)?)\s*(kg|公斤|斤|g|克)", text, flags=re.IGNORECASE)
        if not m:
            return None
        value = float(m.group(1))
        unit = m.group(2).lower()
        if unit in {"斤"}:
            return round(value * 0.5, 3)
        if unit in {"g", "克"}:
            return round(value / 1000, 3)
        return round(value, 3)

    @staticmethod
    def _extract_volume_cm3(message_text: str) -> float | None:
        text = message_text or ""
        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:cm|厘米)?\s*[x×*＊]\s*"
            r"(\d+(?:\.\d+)?)\s*(?:cm|厘米)?\s*[x×*＊]\s*"
            r"(\d+(?:\.\d+)?)\s*(?:cm|厘米)?",
            text,
            flags=re.IGNORECASE,
        )
        if not m:
            return None
        a, b, c = float(m.group(1)), float(m.group(2)), float(m.group(3))
        volume = a * b * c
        if volume <= 0:
            return None
        return round(volume, 3)

    @staticmethod
    def _extract_volume_weight_kg(message_text: str) -> float | None:
        text = message_text or ""
        m = re.search(r"(?:体积重|材积重)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*(kg|公斤|斤|g|克)", text, flags=re.IGNORECASE)
        if not m:
            return None
        value = float(m.group(1))
        unit = m.group(2).lower()
        if unit in {"斤"}:
            return round(value * 0.5, 3)
        if unit in {"g", "克"}:
            return round(value / 1000, 3)
        return round(value, 3)

    @staticmethod
    def _extract_service_level(message_text: str) -> str:
        text = (message_text or "").lower()
        if any(k in text for k in ["加急", "急件", "当天", "最快"]):
            return "urgent"
        if any(k in text for k in ["次日", "特快", "次晨", "快速", "快递"]):
            return "express"
        return "standard"

    @staticmethod
    def _extract_locations(message_text: str) -> tuple[str | None, str | None]:
        text = message_text or ""

        labeled_origin = re.search(r"(?:寄件(?:城市)?|发件(?:城市)?|始发地)\s*[:：]?\s*([\u4e00-\u9fa5]{2,20})", text)
        labeled_dest = re.search(r"(?:收件(?:城市)?|目的地|寄到|送到)\s*[:：]?\s*([\u4e00-\u9fa5]{2,20})", text)
        if labeled_origin and labeled_dest:
            return labeled_origin.group(1), labeled_dest.group(1)

        compact = re.search(r"([\u4e00-\u9fa5]{2,20})\s*[~～\-—]\s*([\u4e00-\u9fa5]{2,20})", text)
        if compact:
            return compact.group(1), compact.group(2)

        patterns = [
            (
                r"(?:从|由)\s*([\u4e00-\u9fa5]{2,20}?)\s*"
                r"(?:寄到|发到|送到|到)\s*"
                r"([\u4e00-\u9fa5]{2,20}(?:省|市|区|县|自治区|特别行政区|自治州|地区)?)"
            ),
            r"([\u4e00-\u9fa5]{2,20}?)\s*(?:寄到|发到|送到|到)\s*([\u4e00-\u9fa5]{2,20})",
        ]
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                return m.group(1), m.group(2)

        dest = None
        dm = re.search(
            r"(?:寄到|发到|送到|到)\s*([\u4e00-\u9fa5]{2,20}(?:省|市|区|县|自治区|特别行政区|自治州|地区)?)",
            text,
        )
        if dm:
            dest = dm.group(1)

        origin = None
        om = re.search(
            r"(?:从|由|寄自|发自)\s*([\u4e00-\u9fa5]{2,20}(?:省|市|区|县|自治区|特别行政区|自治州|地区)?)",
            text,
        )
        if om:
            origin = om.group(1)

        return origin, dest

    def _build_quote_request(self, message_text: str) -> tuple[QuoteRequest | None, list[str]]:
        origin, destination = self._extract_locations(message_text)
        weight = self._extract_weight_kg(message_text)
        volume = self._extract_volume_cm3(message_text)
        volume_weight = self._extract_volume_weight_kg(message_text)
        service_level = self._extract_service_level(message_text)

        missing: list[str] = []
        if not origin:
            missing.append("origin")
        if not destination:
            missing.append("destination")
        if weight is None:
            missing.append("weight")

        if missing:
            return None, missing

        return (
            QuoteRequest(
                origin=origin or "",
                destination=destination or "",
                weight=float(weight or 0),
                volume=float(volume or 0.0),
                volume_weight=float(volume_weight or 0.0),
                service_level=service_level,
            ),
            [],
        )

    def _sanitize_reply(self, reply_text: str) -> str:
        text = reply_text or ""
        lowered = text.lower()
        if any(keyword in lowered for keyword in self.high_risk_keywords):
            return self.safe_fallback_reply

        result = self.compliance_guard.evaluate_content(text)
        if result.get("blocked"):
            return self.safe_fallback_reply
        return text

    async def _generate_reply_with_quote(self, message_text: str, item_title: str = "") -> tuple[str, dict[str, Any]]:
        is_quote_intent = self._is_quote_request(message_text)
        force_standard_format = self._is_standard_format_trigger(message_text)
        request, missing = self._build_quote_request(message_text)
        if missing and (is_quote_intent or self.strict_format_reply_enabled or force_standard_format):
            fields = "、".join([self.quote_missing_prompts[field] for field in missing])
            prompt = self.quote_missing_template.format(fields=fields)
            strict_enforced = bool(self.strict_format_reply_enabled and not is_quote_intent)
            return self._sanitize_reply(prompt), {
                "is_quote": True,
                "quote_need_info": True,
                "format_enforced": bool(strict_enforced or force_standard_format),
                "format_enforced_reason": "greeting" if force_standard_format else ("strict_mode" if strict_enforced else ""),
                "quote_missing_fields": missing,
                "quote_success": False,
                "quote_fallback": False,
            }

        if not is_quote_intent:
            reply = self.reply_engine.generate_reply(message_text=message_text, item_title=item_title)
            return self._sanitize_reply(reply), {"is_quote": False}

        if request is None:
            # 保底分支：理论上 missing 已覆盖，这里兜底防止格式解析异常时漏回复
            prompt = self.quote_missing_template.format(fields="寄件城市、收件城市、包裹重量（kg）")
            return self._sanitize_reply(prompt), {
                "is_quote": True,
                "quote_need_info": True,
                "quote_missing_fields": ["origin", "destination", "weight"],
                "quote_success": False,
                "quote_fallback": False,
            }

        start = perf_counter()
        try:
            multi_quote_rows: list[tuple[str, QuoteResult]] = []
            if self.quote_reply_all_couriers:
                multi_quote_rows = await self._quote_all_couriers(request)

            if multi_quote_rows:
                best_courier, best_result = multi_quote_rows[0]
                reply = self._compose_multi_courier_quote_reply(multi_quote_rows)
                latency_ms = int((perf_counter() - start) * 1000)
                return self._sanitize_reply(reply), {
                    "is_quote": True,
                    "quote_need_info": False,
                    "quote_success": True,
                    "quote_fallback": any(bool(r.fallback_used) for _, r in multi_quote_rows),
                    "quote_cache_hit": all(bool(r.cache_hit) for _, r in multi_quote_rows),
                    "quote_stale": any(bool(r.stale) for _, r in multi_quote_rows),
                    "quote_latency_ms": latency_ms,
                    "quote_all_couriers": [
                        {
                            "courier": courier_name,
                            "total_fee": round(float(result.total_fee), 2),
                            "eta_minutes": int(result.eta_minutes),
                            "eta_days": self._format_eta_days(result.eta_minutes),
                            "fallback_used": bool(result.fallback_used),
                            "cache_hit": bool(result.cache_hit),
                        }
                        for courier_name, result in multi_quote_rows
                    ],
                    "quote_result": {
                        **best_result.to_dict(),
                        "selected_courier": best_courier,
                    },
                }

            result = await self.quote_engine.get_quote(request)
            latency_ms = int((perf_counter() - start) * 1000)
            explain = result.explain if isinstance(result.explain, dict) else {}
            selected_template = self._select_quote_reply_template(explain)
            reply = result.compose_reply(
                validity_minutes=int(self.quote_config.get("validity_minutes", 30)),
                template=selected_template,
            )
            return self._sanitize_reply(reply), {
                "is_quote": True,
                "quote_need_info": False,
                "quote_success": True,
                "quote_fallback": bool(result.fallback_used),
                "quote_cache_hit": bool(result.cache_hit),
                "quote_stale": bool(result.stale),
                "quote_latency_ms": latency_ms,
                "quote_result": result.to_dict(),
            }
        except QuoteProviderError:
            return self._sanitize_reply(self.quote_failed_template), {
                "is_quote": True,
                "quote_need_info": False,
                "quote_success": False,
                "quote_fallback": True,
            }

    def generate_reply(self, message_text: str, item_title: str = "") -> str:
        """按策略引擎生成回复（兼容旧调用）。"""
        reply = self.reply_engine.generate_reply(message_text=message_text, item_title=item_title)
        return self._sanitize_reply(reply)

    async def _send_reply_on_page(self, page_id: str, session_id: str, reply_text: str) -> bool:
        escaped = reply_text.replace("\\", "\\\\").replace("`", "\\`")
        script = f"""
(() => {{
  const target = document.querySelector(`[data-session-id="{session_id}"]`)
    || document.querySelector(`[data-id="{session_id}"]`);
  if (target) target.click();

  const input = document.querySelector("textarea")
    || document.querySelector("[contenteditable='true']")
    || document.querySelector("input[placeholder*='消息']");
  if (!input) return false;

  if (input.tagName.toLowerCase() === "textarea" || input.tagName.toLowerCase() === "input") {{
    input.value = `{escaped}`;
    input.dispatchEvent(new Event("input", {{ bubbles: true }}));
  }} else {{
    input.innerText = `{escaped}`;
    input.dispatchEvent(new InputEvent("input", {{ bubbles: true, data: `{escaped}` }}));
  }}

  const sendBtn = Array.from(document.querySelectorAll("button,span,a")).find(el =>
    (el.innerText || "").includes("发送") || (el.innerText || "").toLowerCase().includes("send")
  );

  if (sendBtn) {{
    sendBtn.click();
    return true;
  }}

  const keyboardEvent = new KeyboardEvent("keydown", {{ key: "Enter", code: "Enter", bubbles: true }});
  input.dispatchEvent(keyboardEvent);
  return true;
}})();
"""
        result = await self.controller.execute_script(page_id, script)
        await asyncio.sleep(self._random_range(self.send_confirm_delay_seconds, (0.15, 0.35)))
        return bool(result)

    async def reply_to_session(self, session_id: str, reply_text: str, page_id: str | None = None) -> bool:
        """向指定会话发送消息。"""
        ws_transport = await self._ensure_ws_transport()
        if ws_transport is not None:
            ws_sent = await ws_transport.send_text(session_id=session_id, text=reply_text)
            if ws_sent or not self.controller:
                return ws_sent
            if self.transport_mode != "auto":
                return False
            self.logger.warning(f"WebSocket send failed for session `{session_id}`, fallback to DOM send")

        if not self.controller:
            raise BrowserError("Browser controller is not initialized. Cannot send reply.")

        owned_page = False
        current_page = page_id
        if not current_page:
            current_page = await self.controller.new_page()
            owned_page = True

        try:
            if owned_page or not self.reuse_message_page:
                await self._ensure_message_page(current_page)
                await asyncio.sleep(self._random_delay(0.3, 0.8))
            return await self._send_reply_on_page(current_page, session_id, reply_text)
        finally:
            if owned_page:
                await self.controller.close_page(current_page)

    async def auto_reply_unread(self, limit: int = 20, dry_run: bool = False) -> dict[str, Any]:
        """自动回复未读消息。"""
        unread = await self.get_unread_sessions(limit=limit)
        unread = unread[: self.max_replies_per_run]

        details = []
        success = 0
        within_target_count = 0

        quote_requests = 0
        quote_need_info_count = 0
        quote_success_count = 0
        quote_fallback_count = 0
        quote_latency_samples: list[int] = []

        shared_page_id: str | None = None
        if self.fast_reply_enabled and self.reuse_message_page and not dry_run and self.controller:
            shared_page_id = await self.controller.new_page()
            await self._ensure_message_page(shared_page_id)

        try:
            for index, session in enumerate(unread):
                detail = await self.process_session(session=session, dry_run=dry_run, page_id=shared_page_id)
                details.append(detail)
                within_target = bool(detail.get("within_target", False))

                if within_target:
                    within_target_count += 1

                if detail.get("is_quote"):
                    if detail.get("quote_need_info"):
                        quote_need_info_count += 1
                    else:
                        quote_requests += 1
                        if detail.get("quote_success"):
                            quote_success_count += 1
                        if detail.get("quote_fallback"):
                            quote_fallback_count += 1
                        if isinstance(detail.get("quote_latency_ms"), int):
                            quote_latency_samples.append(int(detail["quote_latency_ms"]))

                if detail.get("sent"):
                    success += 1

                if not dry_run:
                    if index == 0 and self.fast_reply_enabled:
                        await asyncio.sleep(self._random_range(self.first_reply_delay_seconds, (0.25, 0.9)))
                    else:
                        delay = self.inter_reply_delay_seconds if self.fast_reply_enabled else (0.8, 1.6)
                        await asyncio.sleep(self._random_range(delay, (0.8, 1.6)))
        finally:
            if shared_page_id:
                await self.controller.close_page(shared_page_id)

        quote_success_rate = (quote_success_count / quote_requests) if quote_requests else 0.0
        quote_fallback_rate = (quote_fallback_count / quote_requests) if quote_requests else 0.0
        quote_latency_ms = int(sum(quote_latency_samples) / len(quote_latency_samples)) if quote_latency_samples else 0
        within_target_rate = (within_target_count / len(unread)) if unread else 0.0

        return {
            "action": "auto_reply_unread",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total": len(unread),
            "success": success,
            "failed": len(unread) - success,
            "dry_run": dry_run,
            "target_reply_seconds": self.reply_target_seconds,
            "within_target_count": within_target_count,
            "within_target_rate": round(within_target_rate, 4),
            "quote_latency_ms": quote_latency_ms,
            "quote_need_info_count": quote_need_info_count,
            "quote_success_rate": round(quote_success_rate, 4),
            "quote_fallback_rate": round(quote_fallback_rate, 4),
            "details": details,
        }

    async def process_session(
        self,
        session: dict[str, Any],
        dry_run: bool = False,
        page_id: str | None = None,
        account_id: str | None = None,
        actor: str = "messages_service",
    ) -> dict[str, Any]:
        """处理单个会话（供批处理与 worker 复用）。"""
        session_start = perf_counter()
        session_id = str(session.get("session_id", ""))
        msg = str(session.get("last_message", ""))
        item_title = str(session.get("item_title", ""))

        reply_text, quote_meta = await self._generate_reply_with_quote(msg, item_title=item_title)
        decision = self.compliance_center.evaluate_before_send(
            reply_text,
            actor=actor,
            account_id=account_id,
            session_id=session_id,
            action="message_send",
        )

        sent = False
        blocked_by_policy = bool(decision.blocked)
        if blocked_by_policy:
            sent = False
            reply_text = self.safe_fallback_reply
            if quote_meta.get("is_quote"):
                quote_meta["quote_success"] = False
                quote_meta["quote_blocked_by_policy"] = True
        elif dry_run:
            sent = True
        elif session_id:
            sent = await self.reply_to_session(session_id, reply_text, page_id=page_id)

        latency_seconds = perf_counter() - session_start
        within_target = latency_seconds <= self.reply_target_seconds

        return {
            "session_id": session_id,
            "peer_name": session.get("peer_name", ""),
            "last_message": msg,
            "reply": reply_text,
            "sent": sent,
            "blocked_by_policy": blocked_by_policy,
            "policy_reason": decision.reason,
            "policy_scope": decision.policy_scope,
            "latency_seconds": round(latency_seconds, 3),
            "within_target": within_target,
            **quote_meta,
        }

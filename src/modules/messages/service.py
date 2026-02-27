"""
闲鱼消息服务
Messages Service

提供站内会话读取与自动回复能力。
"""

import asyncio
import json
import random
import time
from typing import Any

from src.core.config import get_config
from src.core.error_handler import BrowserError
from src.core.logger import get_logger
from src.modules.messages.followup_policy import ReadNoReplyFollowupPolicy
from src.modules.messages.followup_store import FollowupStateStore
from src.modules.messages.fulfillment import FulfillmentHelper
from src.modules.messages.reply_engine import ReplyStrategyEngine
from src.modules.messages.workflow_state import WorkflowStage, WorkflowStateStore
from src.modules.quote.service import QuoteService


class MessageSelectors:
    """消息页选择器。"""

    MESSAGE_PAGE = "https://www.goofish.com/im"

    SESSION_LIST = "[class*='session'], [class*='conversation'], [data-session-id]"
    MESSAGE_INPUT = "textarea, [contenteditable='true'], input[placeholder*='消息']"
    SEND_BUTTON = "button:has-text('发送'), button:has-text('Send'), [class*='send']"


class MessagesService:
    """闲鱼会话自动回复服务。"""

    def __init__(self, controller=None, config: dict[str, Any] | None = None):
        self.controller = controller
        self.logger = get_logger()

        app_config = get_config()
        self.config = config or app_config.get_section("messages", {})

        browser_config = app_config.browser
        self.delay_range = (
            browser_config.get("delay", {}).get("min", 1),
            browser_config.get("delay", {}).get("max", 3),
        )

        self.fast_first_reply_enabled = bool(self.config.get("fast_first_reply_enabled", True))
        self.first_reply_target_seconds = float(self.config.get("first_reply_target_seconds", 3.0))
        self.reuse_message_page = bool(self.config.get("reuse_message_page", True))
        self.followup_quote_enabled = bool(self.config.get("followup_quote_enabled", True))

        self.first_reply_delay_range = self._resolve_delay_range(
            "first_reply_delay_seconds",
            (0.25, 0.8) if self.fast_first_reply_enabled else (1.0, 2.0),
        )
        self.inter_reply_delay_range = self._resolve_delay_range(
            "inter_reply_delay_seconds",
            (0.4, 1.2) if self.fast_first_reply_enabled else (1.0, 2.0),
        )
        self.send_confirm_delay_range = self._resolve_delay_range(
            "send_confirm_delay_seconds",
            (0.15, 0.35) if self.fast_first_reply_enabled else (0.6, 1.2),
        )
        self.followup_quote_delay_range = self._resolve_delay_range(
            "followup_quote_delay_seconds",
            (0.6, 1.5),
        )

        self.reply_prefix = self.config.get("reply_prefix", "")
        self.default_reply = self.config.get("default_reply", "您好，宝贝在的，感兴趣可以直接拍下。")
        self.virtual_default_reply = self.config.get(
            "virtual_default_reply",
            "在的，这是虚拟商品，拍下后会尽快在聊天内给你处理结果。",
        )
        self.max_replies_per_run = int(self.config.get("max_replies_per_run", 10))
        self.read_no_reply_followup_enabled = bool(self.config.get("read_no_reply_followup_enabled", False))
        self.read_no_reply_limit_per_run = self._resolve_positive_int(
            "read_no_reply_limit_per_run",
            default=20,
            max_value=200,
        )
        self.followup_state_path = str(self.config.get("followup_state_path", "data/messages_followup_state.json"))
        self.followup_state_max_sessions = self._resolve_positive_int(
            "followup_state_max_sessions",
            default=5000,
            max_value=200000,
        )
        self.workflow_state_enabled = bool(self.config.get("workflow_state_enabled", True))
        self.workflow_state_path = str(self.config.get("workflow_state_path", "data/message_workflow_state.json"))
        self.workflow_state_max_sessions = self._resolve_positive_int(
            "workflow_state_max_sessions",
            default=5000,
            max_value=200000,
        )

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

        self.quote_service = QuoteService()
        self.fulfillment_helper = FulfillmentHelper(self.config)
        self.followup_policy = ReadNoReplyFollowupPolicy(self.config)
        self.followup_store = FollowupStateStore(
            path=self.followup_state_path,
            max_sessions=self.followup_state_max_sessions,
        )
        self.workflow_state_store = (
            WorkflowStateStore(
                path=self.workflow_state_path,
                max_sessions=self.workflow_state_max_sessions,
            )
            if self.workflow_state_enabled
            else None
        )
        self.selectors = MessageSelectors()
        self._message_page_id: str | None = None

    def _resolve_delay_range(self, key: str, default: tuple[float, float]) -> tuple[float, float]:
        raw = self.config.get(key)
        if isinstance(raw, (list, tuple)) and len(raw) == 2:
            try:
                low = float(raw[0])
                high = float(raw[1])
                if low >= 0 and high >= 0:
                    return (min(low, high), max(low, high))
            except (TypeError, ValueError):
                pass
        return default

    def _resolve_positive_int(self, key: str, default: int, max_value: int) -> int:
        raw = self.config.get(key, default)
        try:
            parsed = int(raw)
            if parsed <= 0:
                return default
            return min(parsed, max_value)
        except (TypeError, ValueError):
            return default

    def _random_between(self, delay_range: tuple[float, float]) -> float:
        return random.uniform(delay_range[0], delay_range[1])

    def _random_delay(self, min_factor: float = 1.0, max_factor: float = 1.0) -> float:
        min_delay = self.delay_range[0] * min_factor
        max_delay = self.delay_range[1] * max_factor
        return random.uniform(min_delay, max_delay)

    async def _ensure_message_page(self) -> str:
        """确保消息页面可复用。"""
        if not self.controller:
            raise BrowserError("Browser controller is not initialized. Cannot open message page.")

        if self._message_page_id:
            current_url = await self.controller.execute_script(self._message_page_id, "window.location.href")
            if isinstance(current_url, str) and self.selectors.MESSAGE_PAGE in current_url:
                return self._message_page_id
            if isinstance(current_url, str) and current_url:
                await self.controller.navigate(
                    self._message_page_id,
                    self.selectors.MESSAGE_PAGE,
                    wait_load=not self.fast_first_reply_enabled,
                )
                await asyncio.sleep(self._random_between(self.first_reply_delay_range))
                return self._message_page_id
            self._message_page_id = None

        page_id = await self.controller.new_page()
        await self.controller.navigate(page_id, self.selectors.MESSAGE_PAGE, wait_load=not self.fast_first_reply_enabled)
        await asyncio.sleep(self._random_between(self.first_reply_delay_range))
        self._message_page_id = page_id
        return page_id

    async def close_message_page(self) -> None:
        """关闭复用中的消息页。"""
        if self._message_page_id and self.controller:
            await self.controller.close_page(self._message_page_id)
        self._message_page_id = None

    async def get_unread_sessions(self, limit: int = 20, *, reuse_page: bool | None = None) -> list[dict[str, Any]]:
        """读取未读会话。"""
        if not self.controller:
            raise BrowserError("Browser controller is not initialized. Cannot fetch unread sessions.")

        should_reuse = self.reuse_message_page if reuse_page is None else bool(reuse_page)

        page_id: str | None = None
        own_page = False
        try:
            if should_reuse:
                page_id = await self._ensure_message_page()
            else:
                own_page = True
                page_id = await self.controller.new_page()
                await self.controller.navigate(page_id, self.selectors.MESSAGE_PAGE)
                await asyncio.sleep(self._random_delay(1.5, 2.5))

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
            if own_page and page_id:
                await self.controller.close_page(page_id)

    async def get_read_no_reply_sessions(
        self,
        limit: int = 20,
        *,
        reuse_page: bool | None = None,
    ) -> list[dict[str, Any]]:
        """读取“已读未回”会话（用于二次合规跟进）。"""
        if not self.controller:
            raise BrowserError("Browser controller is not initialized. Cannot fetch sessions.")

        should_reuse = self.reuse_message_page if reuse_page is None else bool(reuse_page)

        page_id: str | None = None
        own_page = False
        try:
            if should_reuse:
                page_id = await self._ensure_message_page()
            else:
                own_page = True
                page_id = await self.controller.new_page()
                await self.controller.navigate(page_id, self.selectors.MESSAGE_PAGE)
                await asyncio.sleep(self._random_delay(1.5, 2.5))

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
    if (unreadCount > 0) continue;

    const lines = text.split("\\n").map(s => s.trim()).filter(Boolean);
    if (!lines.length) continue;

    const hasReadMarker = lines.some(line => /已读/.test(line));
    if (!hasReadMarker) continue;

    const tail = lines[lines.length - 1] || "";
    const lastMessage = /已读/.test(tail) && lines.length >= 2
      ? lines[lines.length - 2]
      : tail;

    const sessionId = node.getAttribute("data-session-id")
      || node.dataset?.sessionId
      || node.getAttribute("data-id")
      || `session_${{result.length + 1}}`;

    result.push({{
      session_id: sessionId,
      peer_name: lines[0] || "买家",
      item_title: lines.length > 2 ? lines[1] : "",
      last_message: lastMessage || "",
      unread_count: 0,
      has_read_marker: true,
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
            if own_page and page_id:
                await self.controller.close_page(page_id)

    def generate_reply(self, message_text: str, item_title: str = "") -> str:
        """按策略引擎生成回复。"""
        return self.reply_engine.generate_reply(message_text=message_text, item_title=item_title)

    async def _send_message(self, page_id: str, session_id: str, reply_text: str) -> bool:
        safe_session_id = json.dumps(session_id, ensure_ascii=False)
        safe_reply_text = json.dumps(reply_text, ensure_ascii=False)
        script = f"""
(() => {{
  const sessionId = {safe_session_id};
  const replyText = {safe_reply_text};
  const cssEscape = (typeof CSS !== "undefined" && typeof CSS.escape === "function")
    ? CSS.escape
    : (v) => String(v).replace(/\\"/g, '\\\\"');
  const escaped = cssEscape(sessionId);
  const target = document.querySelector(`[data-session-id="${{escaped}}"]`)
    || document.querySelector(`[data-id="${{escaped}}"]`);
  if (target) target.click();

  const input = document.querySelector("textarea")
    || document.querySelector("[contenteditable='true']")
    || document.querySelector("input[placeholder*='消息']");
  if (!input) return false;

  if (input.tagName.toLowerCase() === "textarea" || input.tagName.toLowerCase() === "input") {{
    input.value = replyText;
    input.dispatchEvent(new Event("input", {{ bubbles: true }}));
  }} else {{
    input.innerText = replyText;
    input.dispatchEvent(new InputEvent("input", {{ bubbles: true, data: replyText }}));
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
        await asyncio.sleep(self._random_between(self.send_confirm_delay_range))
        return bool(result)

    async def reply_to_session(
        self,
        session_id: str,
        reply_text: str,
        page_id: str | None = None,
        *,
        close_page: bool = True,
    ) -> bool:
        """向指定会话发送消息。"""
        if not self.controller:
            raise BrowserError("Browser controller is not initialized. Cannot send reply.")

        own_page = page_id is None
        try:
            if own_page:
                page_id = await self.controller.new_page()
                await self.controller.navigate(page_id, self.selectors.MESSAGE_PAGE)
                await asyncio.sleep(self._random_delay())
            return await self._send_message(page_id, session_id, reply_text)
        finally:
            if own_page and close_page and page_id:
                await self.controller.close_page(page_id)

    async def auto_reply_unread(self, limit: int = 20, dry_run: bool = False) -> dict[str, Any]:
        """自动回复未读消息。"""
        page_id: str | None = None

        if self.reuse_message_page and not dry_run:
            page_id = await self._ensure_message_page()

        try:
            unread = await self.get_unread_sessions(limit=limit, reuse_page=bool(page_id))
            unread = unread[: self.max_replies_per_run]

            details = []
            success = 0
            first_reply_within_target = 0
            quote_followup_total = 0
            quote_followup_success = 0

            for idx, session in enumerate(unread):
                session_id = str(session.get("session_id", ""))
                msg = str(session.get("last_message", ""))
                item_title = str(session.get("item_title", ""))
                is_order_intent = self.fulfillment_helper.is_order_intent(msg)

                if not dry_run and session_id:
                    self.followup_store.record_inbound(session_id, msg)
                    if self.workflow_state_store is not None:
                        stage = WorkflowStage.ORDERED if is_order_intent else WorkflowStage.NEW
                        self.workflow_state_store.transition(
                            session_id,
                            stage,
                            metadata={"event": "inbound_message", "last_message": msg, "is_order_intent": is_order_intent},
                            force=bool(is_order_intent),
                        )

                parsed_quote = self.quote_service.parse_quote_request(msg, item_title=item_title)
                is_quote_intent = bool(self.followup_quote_enabled and parsed_quote.is_quote_intent and not is_order_intent)

                if is_order_intent:
                    first_reply_text = self.fulfillment_helper.build_ack_reply(item_title=item_title)
                elif is_quote_intent:
                    first_reply_text = self.quote_service.build_first_reply(parsed_quote)
                else:
                    first_reply_text = self.generate_reply(msg, item_title=item_title)

                first_reply_sent = False
                first_reply_latency: float | None = None

                if dry_run:
                    first_reply_sent = True
                    first_reply_latency = 0.0
                elif session_id:
                    start = time.monotonic()
                    first_reply_sent = await self.reply_to_session(
                        session_id,
                        first_reply_text,
                        page_id=page_id,
                        close_page=False,
                    )
                    first_reply_latency = round(time.monotonic() - start, 3)

                if first_reply_sent:
                    success += 1
                    if first_reply_latency is not None and first_reply_latency <= self.first_reply_target_seconds:
                        first_reply_within_target += 1
                    if not dry_run and session_id:
                        self.followup_store.record_first_reply(session_id, first_reply_text, item_title=item_title)
                        if self.workflow_state_store is not None:
                            target_stage = WorkflowStage.ORDERED if is_order_intent else WorkflowStage.REPLIED
                            self.workflow_state_store.transition(
                                session_id,
                                target_stage,
                                metadata={"event": "first_reply_sent", "is_order_intent": is_order_intent},
                                force=bool(is_order_intent),
                            )

                quote_reply = ""
                quote_source = ""
                quote_sent = False

                if is_quote_intent:
                    quote_followup_total += 1
                    if parsed_quote.missing_fields:
                        quote_source = "pending_fields"
                    else:
                        if dry_run:
                            quote_result, quote_source = await self.quote_service.compute_quote(parsed_quote)
                            if quote_result is not None:
                                quote_reply = self.quote_service.build_quote_message(quote_result, parsed_quote.request)
                                quote_sent = True
                        else:
                            await asyncio.sleep(self._random_between(self.followup_quote_delay_range))
                            quote_result, quote_source = await self.quote_service.compute_quote(parsed_quote)
                            if quote_result is not None and session_id:
                                quote_reply = self.quote_service.build_quote_message(quote_result, parsed_quote.request)
                                quote_sent = await self.reply_to_session(
                                    session_id,
                                    quote_reply,
                                    page_id=page_id,
                                    close_page=False,
                                )

                    if quote_sent:
                        quote_followup_success += 1
                        if not dry_run and session_id:
                            self.followup_store.record_outbound(session_id, quote_reply, item_title=item_title)
                            if self.workflow_state_store is not None:
                                self.workflow_state_store.transition(
                                    session_id,
                                    WorkflowStage.QUOTED,
                                    metadata={"event": "quote_sent", "quote_source": quote_source},
                                )

                details.append(
                    {
                        "session_id": session_id,
                        "peer_name": session.get("peer_name", ""),
                        "last_message": msg,
                        "first_reply": first_reply_text,
                        "first_reply_sent": first_reply_sent,
                        "first_reply_latency_seconds": first_reply_latency,
                        "first_reply_within_target": bool(
                            first_reply_latency is not None and first_reply_latency <= self.first_reply_target_seconds
                        ),
                        "is_quote_intent": is_quote_intent,
                        "is_order_intent": is_order_intent,
                        "quote_reply": quote_reply,
                        "quote_source": quote_source,
                        "quote_sent": quote_sent,
                    }
                )

                if not dry_run and idx < len(unread) - 1:
                    await asyncio.sleep(self._random_between(self.inter_reply_delay_range))

            return {
                "action": "auto_reply_unread",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total": len(unread),
                "success": success,
                "failed": len(unread) - success,
                "dry_run": dry_run,
                "first_reply_target_seconds": self.first_reply_target_seconds,
                "first_reply_within_target": first_reply_within_target,
                "quote_followup_total": quote_followup_total,
                "quote_followup_success": quote_followup_success,
                "details": details,
            }
        finally:
            if page_id:
                await self.close_message_page()

    async def auto_followup_read_no_reply(self, limit: int = 20, dry_run: bool = False) -> dict[str, Any]:
        """合规处理“已读未回”会话。"""
        if not self.read_no_reply_followup_enabled:
            return {
                "action": "auto_followup_read_no_reply",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "enabled": False,
                "dry_run": dry_run,
                "total": 0,
                "eligible": 0,
                "success": 0,
                "failed": 0,
                "skipped_reason": "read_no_reply_followup_disabled",
                "details": [],
            }

        page_id: str | None = None
        if self.reuse_message_page and not dry_run:
            page_id = await self._ensure_message_page()

        try:
            effective_limit = min(max(limit, 1), self.read_no_reply_limit_per_run)
            sessions = await self.get_read_no_reply_sessions(limit=effective_limit, reuse_page=bool(page_id))

            details: list[dict[str, Any]] = []
            eligible = 0
            success = 0

            for idx, session in enumerate(sessions):
                session_id = str(session.get("session_id", ""))
                item_title = str(session.get("item_title", ""))

                state = self.followup_store.get(session_id) if session_id else {}
                allow_send, decision = self.followup_policy.evaluate(session, state)
                if decision == "stop_keyword_hit" and not dry_run and session_id:
                    state = self.followup_store.mark_opt_out(session_id)
                    if self.workflow_state_store is not None:
                        self.workflow_state_store.transition(
                            session_id,
                            WorkflowStage.CLOSED,
                            metadata={"event": "followup_stopped_by_keyword"},
                            force=True,
                        )

                followup_text = ""
                followup_sent = False

                if allow_send:
                    eligible += 1
                    followup_text = self.followup_policy.build_followup_message(session, state)

                    if dry_run:
                        followup_sent = True
                    elif session_id:
                        followup_sent = await self.reply_to_session(
                            session_id,
                            followup_text,
                            page_id=page_id,
                            close_page=False,
                        )

                    if followup_sent:
                        success += 1
                        if not dry_run and session_id:
                            state = self.followup_store.record_followup_sent(
                                session_id,
                                followup_text,
                                item_title=item_title,
                            )
                            if self.workflow_state_store is not None:
                                self.workflow_state_store.transition(
                                    session_id,
                                    WorkflowStage.FOLLOWED,
                                    metadata={"event": "followup_sent"},
                                )

                details.append(
                    {
                        "session_id": session_id,
                        "peer_name": session.get("peer_name", ""),
                        "item_title": item_title,
                        "last_message": session.get("last_message", ""),
                        "has_read_marker": bool(session.get("has_read_marker", True)),
                        "decision": decision,
                        "eligible": allow_send,
                        "followup_text": followup_text,
                        "followup_sent": followup_sent,
                        "followup_sent_count": int((state or {}).get("followup_sent_count") or 0),
                    }
                )

                if not dry_run and idx < len(sessions) - 1:
                    await asyncio.sleep(self._random_between(self.inter_reply_delay_range))

            return {
                "action": "auto_followup_read_no_reply",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "enabled": True,
                "dry_run": dry_run,
                "total": len(sessions),
                "eligible": eligible,
                "success": success,
                "failed": eligible - success,
                "details": details,
            }
        finally:
            if page_id:
                await self.close_message_page()

    async def auto_workflow(self, limit: int = 20, dry_run: bool = False) -> dict[str, Any]:
        """全流程：未读首响 + 询价补充 + 已读未回跟进。"""
        first_stage = await self.auto_reply_unread(limit=limit, dry_run=dry_run)
        second_stage = await self.auto_followup_read_no_reply(limit=limit, dry_run=dry_run)

        return {
            "action": "auto_workflow",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "dry_run": dry_run,
            "stages": {
                "auto_reply_unread": first_stage,
                "auto_followup_read_no_reply": second_stage,
            },
            "summary": {
                "replied_sessions": int(first_stage.get("success", 0)),
                "quote_followup_success": int(first_stage.get("quote_followup_success", 0)),
                "read_no_reply_followup_success": int(second_stage.get("success", 0)),
            },
        }

    def transition_workflow_stage(
        self,
        session_id: str,
        stage: str,
        *,
        force: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """手动推进/修正会话工作流状态。"""
        sid = str(session_id or "").strip()
        if not sid:
            return {"success": False, "reason": "missing_session_id", "record": {}}
        if self.workflow_state_store is None:
            return {"success": False, "reason": "workflow_state_disabled", "record": {}}

        ok, reason, record = self.workflow_state_store.transition(
            sid,
            stage,
            metadata=metadata or {"event": "manual_transition"},
            force=force,
        )
        return {"success": bool(ok), "reason": reason, "record": record}

"""
闲鱼消息服务
Messages Service

提供站内会话读取与自动回复能力。
"""

import asyncio
import random
import time
from typing import Any

from src.core.config import get_config
from src.core.error_handler import BrowserError
from src.core.logger import get_logger


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
        self.reply_prefix = self.config.get("reply_prefix", "")
        self.default_reply = self.config.get("default_reply", "您好，宝贝在的，感兴趣可以直接拍下。")
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

        self.selectors = MessageSelectors()

    def _random_delay(self, min_factor: float = 1.0, max_factor: float = 1.0) -> float:
        min_delay = self.delay_range[0] * min_factor
        max_delay = self.delay_range[1] * max_factor
        return random.uniform(min_delay, max_delay)

    async def get_unread_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        """读取未读会话。"""
        if not self.controller:
            raise BrowserError("Browser controller is not initialized. Cannot fetch unread sessions.")

        page_id = await self.controller.new_page()
        try:
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
            await self.controller.close_page(page_id)

    def generate_reply(self, message_text: str, item_title: str = "") -> str:
        """根据关键词生成回复。"""
        text = (message_text or "").strip().lower()

        reply = ""
        for keyword, template in self.keyword_replies.items():
            if keyword.lower() in text:
                reply = template
                break

        if not reply:
            reply = self.default_reply

        if item_title:
            reply = f"关于「{item_title}」，{reply}"

        if self.reply_prefix:
            reply = f"{self.reply_prefix}{reply}"

        return reply

    async def reply_to_session(self, session_id: str, reply_text: str) -> bool:
        """向指定会话发送消息。"""
        if not self.controller:
            raise BrowserError("Browser controller is not initialized. Cannot send reply.")

        page_id = await self.controller.new_page()
        try:
            await self.controller.navigate(page_id, self.selectors.MESSAGE_PAGE)
            await asyncio.sleep(self._random_delay())

            escaped = reply_text.replace("\\", "\\\\").replace("`", "\\`")
            script = f"""
(() => {{
  const target = document.querySelector(`[data-session-id=\"{session_id}\"]`)
    || document.querySelector(`[data-id=\"{session_id}\"]`);
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
            await asyncio.sleep(self._random_delay(0.5, 1.2))
            return bool(result)
        finally:
            await self.controller.close_page(page_id)

    async def auto_reply_unread(self, limit: int = 20, dry_run: bool = False) -> dict[str, Any]:
        """自动回复未读消息。"""
        unread = await self.get_unread_sessions(limit=limit)
        unread = unread[: self.max_replies_per_run]

        details = []
        success = 0

        for session in unread:
            session_id = str(session.get("session_id", ""))
            msg = str(session.get("last_message", ""))
            item_title = str(session.get("item_title", ""))
            reply_text = self.generate_reply(msg, item_title=item_title)

            sent = False
            if dry_run:
                sent = True
            elif session_id:
                sent = await self.reply_to_session(session_id, reply_text)

            details.append(
                {
                    "session_id": session_id,
                    "peer_name": session.get("peer_name", ""),
                    "last_message": msg,
                    "reply": reply_text,
                    "sent": sent,
                }
            )

            if sent:
                success += 1

            await asyncio.sleep(self._random_delay(0.8, 1.6))

        return {
            "action": "auto_reply_unread",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total": len(unread),
            "success": success,
            "failed": len(unread) - success,
            "dry_run": dry_run,
            "details": details,
        }

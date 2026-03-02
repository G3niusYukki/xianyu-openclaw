"""Lite Mode entrypoint: python -m src.lite."""

from __future__ import annotations

import asyncio
import re

from src.core.compliance import get_compliance_guard
from src.core.logger import get_logger
from src.modules.messages.reply_engine import ReplyStrategyEngine
from src.modules.quote.engine import AutoQuoteEngine
from src.modules.quote.models import QuoteRequest

from .config import load_lite_config
from .dedup import DualLayerDedup
from .ws_client import LiteWsClient
from .xianyu_api import XianyuApiClient


def _try_parse_quote_request(text: str) -> QuoteRequest | None:
    """Best-effort parsing for basic route+weight messages."""

    raw = str(text or "")
    city_match = re.search(r"([\u4e00-\u9fa5]{2,})\s*(?:到|->|至)\s*([\u4e00-\u9fa5]{2,})", raw)
    weight_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:kg|公斤|斤)", raw, flags=re.IGNORECASE)
    if not city_match or not weight_match:
        return None

    origin = city_match.group(1)
    destination = city_match.group(2)
    weight = float(weight_match.group(1))
    if "斤" in weight_match.group(0):
        weight = weight / 2.0

    return QuoteRequest(origin=origin, destination=destination, weight=max(0.1, weight))


async def _process_loop(
    ws_client: LiteWsClient,
    dedup: DualLayerDedup,
    reply_engine: ReplyStrategyEngine,
    quote_engine: AutoQuoteEngine,
) -> None:
    logger = get_logger()
    compliance = get_compliance_guard()

    while True:
        event = await ws_client.next_event()
        chat_id = str(event.get("chat_id", "") or "")
        sender_user_id = str(event.get("sender_user_id", "") or "")
        message_text = str(event.get("text", "") or "").strip()
        item_id = str(event.get("item_id", "") or "")
        create_time = int(event.get("create_time", 0) or 0)

        if not chat_id or not sender_user_id or not message_text:
            continue

        await dedup.cleanup()
        if await dedup.seen_exact(chat_id, create_time, message_text):
            continue
        if await dedup.seen_content(chat_id, message_text):
            continue

        quote_req = _try_parse_quote_request(message_text)
        if quote_req is not None:
            try:
                quote_result = await quote_engine.get_quote(quote_req)
                reply = quote_result.compose_reply()
            except Exception as exc:
                logger.warning(f"Lite quote failed, fallback to reply engine: {exc}")
                reply = reply_engine.generate_reply(message_text=message_text, item_title=item_id)
        else:
            reply = reply_engine.generate_reply(message_text=message_text, item_title=item_id)

        allowed, hits = compliance.check_content(message_text, reply)
        if not allowed:
            logger.warning(f"Lite compliance blocked reply, hits={hits}")
            continue

        ok = await ws_client.send_text(chat_id, sender_user_id, reply)
        if ok:
            logger.info(f"Lite replied -> chat={chat_id}, buyer={sender_user_id[:8]}..., text={reply[:80]}")


async def _amain() -> None:
    logger = get_logger()
    cfg = load_lite_config()

    api_client = XianyuApiClient(cfg.cookie)
    await api_client.has_login()
    await api_client.get_token(force_refresh=True)

    dedup = DualLayerDedup(
        cfg.dedup_db_path,
        exact_days=cfg.dedup_exact_days,
        content_hours=cfg.dedup_content_hours,
    )
    await dedup.init()

    reply_engine = ReplyStrategyEngine(
        default_reply=cfg.default_reply,
        virtual_default_reply=cfg.virtual_default_reply,
    )
    quote_engine = AutoQuoteEngine()

    ws_client = LiteWsClient(
        ws_url=cfg.ws_url,
        cookie=cfg.cookie,
        device_id=api_client.device_id,
        my_user_id=api_client.user_id,
        token_provider=api_client.get_token,
        heartbeat_interval=cfg.heartbeat_interval,
        heartbeat_timeout=cfg.heartbeat_timeout,
        reconnect_base_delay=cfg.reconnect_base_delay,
        reconnect_backoff=cfg.reconnect_backoff,
        reconnect_max_delay=cfg.reconnect_max_delay,
        message_expire_ms=cfg.message_expire_ms,
    )

    logger.info("🐟 xianyu-openclaw Lite Mode starting...")
    runner = asyncio.create_task(ws_client.run_forever())
    processor = asyncio.create_task(_process_loop(ws_client, dedup, reply_engine, quote_engine))

    try:
        await asyncio.gather(runner, processor)
    finally:
        await ws_client.stop()


def main() -> None:
    """Program entrypoint."""

    asyncio.run(_amain())


if __name__ == "__main__":
    main()

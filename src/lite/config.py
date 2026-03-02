"""Lite mode configuration loaded from environment and .env file."""

from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass(slots=True)
class LiteConfig:
    """Configuration for Lite mode runtime."""

    cookie: str
    ai_key: str
    ws_url: str = "wss://wss-goofish.dingtalk.com/"
    heartbeat_interval: int = 15
    heartbeat_timeout: int = 8
    reconnect_base_delay: float = 2.0
    reconnect_backoff: float = 1.8
    reconnect_max_delay: float = 45.0
    message_expire_ms: int = 300000
    dedup_db_path: str = "data/lite_dedup.db"
    dedup_exact_days: int = 7
    dedup_content_hours: int = 24
    default_reply: str = "在的，可以直接下单，拍下后我会尽快处理。"
    virtual_default_reply: str = "在的，这是虚拟商品，付款后会尽快给你处理。"


def load_lite_config() -> LiteConfig:
    """Load Lite mode configuration from .env and process environment."""

    load_dotenv(override=False)
    cookie = (os.getenv("LITE_COOKIE") or os.getenv("XIANYU_COOKIE_1") or os.getenv("COOKIES_STR") or "").strip()
    ai_key = (os.getenv("AI_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    if not cookie:
        raise ValueError("Missing cookie. Set LITE_COOKIE or XIANYU_COOKIE_1 in .env")

    return LiteConfig(
        cookie=cookie,
        ai_key=ai_key,
        ws_url=(os.getenv("LITE_WS_URL") or "wss://wss-goofish.dingtalk.com/").strip(),
        heartbeat_interval=int(os.getenv("LITE_HEARTBEAT_INTERVAL", "15")),
        heartbeat_timeout=int(os.getenv("LITE_HEARTBEAT_TIMEOUT", "8")),
        reconnect_base_delay=float(os.getenv("LITE_RECONNECT_BASE_DELAY", "2")),
        reconnect_backoff=float(os.getenv("LITE_RECONNECT_BACKOFF", "1.8")),
        reconnect_max_delay=float(os.getenv("LITE_RECONNECT_MAX_DELAY", "45")),
        message_expire_ms=int(os.getenv("LITE_MESSAGE_EXPIRE_MS", "300000")),
        dedup_db_path=(os.getenv("LITE_DEDUP_DB", "data/lite_dedup.db")).strip(),
        dedup_exact_days=int(os.getenv("LITE_DEDUP_EXACT_DAYS", "7")),
        dedup_content_hours=int(os.getenv("LITE_DEDUP_CONTENT_HOURS", "24")),
        default_reply=(os.getenv("LITE_DEFAULT_REPLY") or "在的，可以直接下单，拍下后我会尽快处理。").strip(),
        virtual_default_reply=(
            os.getenv("LITE_VIRTUAL_DEFAULT_REPLY") or "在的，这是虚拟商品，付款后会尽快给你处理。"
        ).strip(),
    )

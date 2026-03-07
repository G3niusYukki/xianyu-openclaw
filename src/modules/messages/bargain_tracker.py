"""
议价计数模块 — 追踪每个会话的议价轮次

借鉴 XianyuAutoAgent context_manager.py 的 chat_bargain_counts 表，
在 AI 上下文中注入议价次数，让模型根据轮次调整回复策略。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from src.core.logger import get_logger

logger = get_logger()

BARGAIN_KEYWORDS = [
    "便宜", "优惠", "少一点", "能少", "能便宜",
    "打折", "折扣", "最低", "底价",
    "减", "降", "让", "砍",
    "多少能卖", "什么价", "最低多少",
]


class BargainTracker:
    """按 chat_id 追踪议价次数。"""

    def __init__(self, db_path: str | Path = "data/bargain_tracker.db") -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=3000")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bargain_counts (
                    chat_id      TEXT PRIMARY KEY,
                    count        INTEGER DEFAULT 0,
                    last_updated TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def is_bargain_message(content: str) -> bool:
        """判断消息是否包含议价意图。"""
        text = content.strip().lower()
        return any(kw in text for kw in BARGAIN_KEYWORDS)

    def get_count(self, chat_id: str) -> int:
        """获取某会话的议价次数。"""
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT count FROM bargain_counts WHERE chat_id = ?", (chat_id,)
            ).fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    def increment(self, chat_id: str) -> int:
        """议价次数 +1，返回新计数。"""
        now = datetime.utcnow().isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute("SELECT count FROM bargain_counts WHERE chat_id = ?", (chat_id,)).fetchone()
            if row:
                new_count = row[0] + 1
                conn.execute(
                    "UPDATE bargain_counts SET count = ?, last_updated = ? WHERE chat_id = ?",
                    (new_count, now, chat_id),
                )
            else:
                new_count = 1
                conn.execute(
                    "INSERT INTO bargain_counts (chat_id, count, last_updated) VALUES (?, ?, ?)",
                    (chat_id, 1, now),
                )
            conn.commit()
            return new_count
        except Exception as exc:
            logger.warning(f"[bargain] increment error: {exc}")
            conn.rollback()
            return 0
        finally:
            conn.close()

    def record_if_bargain(self, chat_id: str, content: str) -> int:
        """如果消息是议价，自动 +1 并返回新计数；否则返回当前计数。"""
        if self.is_bargain_message(content):
            count = self.increment(chat_id)
            logger.debug(f"[bargain] chat={chat_id} bargain #{count}")
            return count
        return self.get_count(chat_id)

    def get_context_hint(self, chat_id: str) -> str | None:
        """生成注入 AI 上下文的提示文本。"""
        count = self.get_count(chat_id)
        if count == 0:
            return None
        if count == 1:
            return "买家第1次议价，可以礼貌回应但坚持价格。"
        if count == 2:
            return "买家第2次议价，语气可以稍微松动，但强调性价比。"
        if count <= 4:
            return f"买家已议价{count}次，可以考虑小幅度让步或赠品策略。"
        return f"买家已议价{count}次（高频议价），请坚守底价，引导下单。"

    def reset(self, chat_id: str) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DELETE FROM bargain_counts WHERE chat_id = ?", (chat_id,))
            conn.commit()
        finally:
            conn.close()

    def cleanup(self, days: int = 30) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            c = conn.execute(
                "DELETE FROM bargain_counts WHERE last_updated < datetime('now', ?)", (f"-{days} days",)
            ).rowcount
            conn.commit()
            if c:
                logger.info(f"[bargain] cleanup: removed {c} records older than {days} days")
            return c
        finally:
            conn.close()

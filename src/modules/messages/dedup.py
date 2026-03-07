"""
消息去重模块 — 防止对同一条消息重复回复

双层策略（借鉴 XianyuAutoAgent context_manager.py）：
  Layer 1: 精确去重 — 基于 (chat_id, create_time, content) 的 MD5 hash
  Layer 2: 内容去重 — 基于 (chat_id, normalized_content) 的 MD5 hash
           确保相同询问在同一会话中只回复一次
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path

from src.core.logger import get_logger

logger = get_logger()


class MessageDedup:
    """消息去重器，使用 SQLite 持久化。"""

    def __init__(self, db_path: str | Path = "data/message_dedup.db") -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=3000")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS message_replies (
                    message_hash TEXT PRIMARY KEY,
                    chat_id      TEXT NOT NULL,
                    content      TEXT NOT NULL,
                    create_time  INTEGER NOT NULL,
                    reply        TEXT,
                    replied_at   TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS content_replies (
                    content_hash TEXT PRIMARY KEY,
                    chat_id      TEXT NOT NULL,
                    content      TEXT NOT NULL,
                    reply        TEXT,
                    first_at     TEXT DEFAULT (datetime('now')),
                    last_at      TEXT DEFAULT (datetime('now')),
                    count        INTEGER DEFAULT 1
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mr_chat ON message_replies (chat_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cr_chat ON content_replies (chat_id)")
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.strip().split())

    @staticmethod
    def _hash(raw: str) -> str:
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def _msg_hash(self, chat_id: str, create_time: int, content: str) -> str:
        return self._hash(f"{chat_id}:{create_time}:{self._normalize(content)}")

    def _content_hash(self, chat_id: str, content: str) -> str:
        return self._hash(f"{chat_id}:{self._normalize(content)}")

    def is_duplicate(self, chat_id: str, create_time: int, content: str) -> bool:
        """Layer 1: 完全相同的消息是否已回复过。"""
        h = self._msg_hash(chat_id, create_time, content)
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute("SELECT 1 FROM message_replies WHERE message_hash = ?", (h,)).fetchone()
            return row is not None
        finally:
            conn.close()

    def is_content_duplicate(self, chat_id: str, content: str) -> bool:
        """Layer 2: 同一会话中相同内容的询问是否已回复过。"""
        h = self._content_hash(chat_id, content)
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute("SELECT 1 FROM content_replies WHERE content_hash = ?", (h,)).fetchone()
            return row is not None
        finally:
            conn.close()

    def is_replied(self, chat_id: str, create_time: int, content: str) -> bool:
        """综合判断：任一层命中即视为已回复。"""
        return self.is_duplicate(chat_id, create_time, content) or self.is_content_duplicate(chat_id, content)

    def mark_replied(
        self,
        chat_id: str,
        create_time: int,
        content: str,
        reply: str = "",
    ) -> None:
        """标记消息已回复（同时写入两张表）。"""
        now = datetime.utcnow().isoformat()
        msg_h = self._msg_hash(chat_id, create_time, content)
        cnt_h = self._content_hash(chat_id, content)
        norm = self._normalize(content)

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO message_replies (message_hash, chat_id, content, create_time, reply, replied_at) VALUES (?,?,?,?,?,?)",
                (msg_h, chat_id, norm, create_time, reply, now),
            )
            row = conn.execute("SELECT count FROM content_replies WHERE content_hash = ?", (cnt_h,)).fetchone()
            if row:
                conn.execute(
                    "UPDATE content_replies SET last_at = ?, count = count + 1, reply = ? WHERE content_hash = ?",
                    (now, reply, cnt_h),
                )
            else:
                conn.execute(
                    "INSERT INTO content_replies (content_hash, chat_id, content, reply, first_at, last_at, count) VALUES (?,?,?,?,?,?,1)",
                    (cnt_h, chat_id, norm, reply, now, now),
                )
            conn.commit()
        except Exception as exc:
            logger.warning(f"[dedup] mark_replied error: {exc}")
            conn.rollback()
        finally:
            conn.close()

    def cleanup(self, days: int = 30) -> int:
        """清理超过指定天数的去重记录。"""
        conn = sqlite3.connect(self.db_path)
        try:
            c1 = conn.execute(
                "DELETE FROM message_replies WHERE replied_at < datetime('now', ?)", (f"-{days} days",)
            ).rowcount
            c2 = conn.execute(
                "DELETE FROM content_replies WHERE last_at < datetime('now', ?)", (f"-{days} days",)
            ).rowcount
            conn.commit()
            total = c1 + c2
            if total:
                logger.info(f"[dedup] cleanup: removed {total} records older than {days} days")
            return total
        finally:
            conn.close()

"""Dual-layer dedup store for Lite mode."""

from __future__ import annotations

import hashlib
import time

import aiosqlite


class DualLayerDedup:
    """Track exact-message and content-message dedup records in SQLite."""

    def __init__(self, db_path: str, *, exact_days: int = 7, content_hours: int = 24):
        self.db_path = db_path
        self.exact_ttl = exact_days * 24 * 3600
        self.content_ttl = content_hours * 3600

    async def init(self) -> None:
        """Create tables if absent."""

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS exact_dedup (
                    digest TEXT PRIMARY KEY,
                    created_at INTEGER NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS content_dedup (
                    digest TEXT PRIMARY KEY,
                    created_at INTEGER NOT NULL
                )
                """
            )
            await db.commit()

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    async def seen_exact(self, chat_id: str, create_time: int, content: str) -> bool:
        """Return True if exact message was seen before."""

        digest = self._hash(f"{chat_id}:{create_time}:{content}")
        return await self._seen_and_mark("exact_dedup", digest)

    async def seen_content(self, chat_id: str, content: str) -> bool:
        """Return True if normalized content was seen recently."""

        normalized = " ".join(str(content or "").split())
        digest = self._hash(f"{chat_id}:{normalized}")
        return await self._seen_and_mark("content_dedup", digest)

    async def _seen_and_mark(self, table: str, digest: str) -> bool:
        """Atomically mark digest and report whether it was seen before.

        Uses SQLite ``INSERT OR IGNORE`` to avoid read-then-write races under
        concurrent inserts for the same digest.
        """

        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                f"INSERT OR IGNORE INTO {table}(digest, created_at) VALUES (?, ?)",
                (digest, int(time.time())),
            )
            await db.commit()
            # rowcount == 1: inserted now (not seen before)
            # rowcount == 0: ignored by PK conflict (already seen)
            return cur.rowcount == 0

    async def cleanup(self) -> None:
        """Cleanup expired rows for both dedup layers."""

        now = int(time.time())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM exact_dedup WHERE created_at < ?", (now - self.exact_ttl,))
            await db.execute("DELETE FROM content_dedup WHERE created_at < ?", (now - self.content_ttl,))
            await db.commit()

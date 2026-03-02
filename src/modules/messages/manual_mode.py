"""Manual takeover mode management for message sessions."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ManualModeState:
    session_id: str
    enabled: bool
    updated_at: float
    expires_at: float | None


@dataclass(slots=True)
class ManualModeResult:
    state: ManualModeState
    toggled: bool = False
    timeout_recovered: bool = False


class ManualModeStore:
    """Session-scoped manual takeover state persisted in SQLite."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        toggle_keyword: str = "。",
        timeout_seconds: int = 3600,
    ) -> None:
        self.db_path = Path(db_path)
        self.toggle_keyword = toggle_keyword
        self.timeout_seconds = max(1, int(timeout_seconds))
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS message_manual_mode (
                    session_id TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL,
                    updated_at REAL NOT NULL,
                    expires_at REAL
                )
                """
            )
            conn.commit()

    def _now(self, now: float | None = None) -> float:
        return float(now if now is not None else time.time())

    def _upsert(self, session_id: str, enabled: bool, now_ts: float) -> ManualModeState:
        expires_at = now_ts + self.timeout_seconds if enabled else None
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO message_manual_mode(session_id, enabled, updated_at, expires_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    enabled=excluded.enabled,
                    updated_at=excluded.updated_at,
                    expires_at=excluded.expires_at
                """,
                (session_id, 1 if enabled else 0, now_ts, expires_at),
            )
            conn.commit()
        return ManualModeState(session_id=session_id, enabled=enabled, updated_at=now_ts, expires_at=expires_at)

    def _get_raw(self, session_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT session_id, enabled, updated_at, expires_at FROM message_manual_mode WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return row

    def get_state(self, session_id: str, *, now: float | None = None) -> ManualModeResult:
        now_ts = self._now(now)
        row = self._get_raw(session_id)
        if row is None:
            state = ManualModeState(session_id=session_id, enabled=False, updated_at=now_ts, expires_at=None)
            return ManualModeResult(state=state)

        enabled = bool(row["enabled"])
        expires_at = row["expires_at"]

        if enabled and expires_at is not None and float(expires_at) <= now_ts:
            state = self._upsert(session_id, False, now_ts)
            return ManualModeResult(state=state, timeout_recovered=True)

        state = ManualModeState(
            session_id=row["session_id"],
            enabled=enabled,
            updated_at=float(row["updated_at"]),
            expires_at=float(expires_at) if expires_at is not None else None,
        )
        return ManualModeResult(state=state)

    def set_state(self, session_id: str, enabled: bool, *, now: float | None = None) -> ManualModeState:
        now_ts = self._now(now)
        return self._upsert(session_id, enabled, now_ts)

    def toggle(self, session_id: str, *, now: float | None = None) -> ManualModeState:
        current = self.get_state(session_id, now=now).state
        return self.set_state(session_id, not current.enabled, now=now)

    def process_message(self, session_id: str, message: str, *, now: float | None = None) -> ManualModeResult:
        now_ts = self._now(now)
        baseline = self.get_state(session_id, now=now_ts)
        if str(message or "").strip() == self.toggle_keyword:
            state = self.toggle(session_id, now=now_ts)
            return ManualModeResult(state=state, toggled=True, timeout_recovered=baseline.timeout_recovered)
        return baseline

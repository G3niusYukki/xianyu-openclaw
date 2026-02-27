"""跟进引擎：已读未回场景的合规跟进。"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.core.logger import get_logger


@dataclass(slots=True)
class FollowUpPolicy:
    max_touches_per_day: int = 2
    min_interval_hours: float = 4.0
    silent_hours_start: int = 22
    silent_hours_end: int = 8
    max_attempts: int = 3
    backoff_multiplier: float = 2.0
    allowed_keywords: tuple[str, ...] = ("提醒", "确认", "需要", "帮助", "服务")
    forbidden_keywords: tuple[str, ...] = ("微信", "vx", "v信", "私聊", "转账", "加我")


@dataclass(slots=True)
class FollowUpAudit:
    id: int
    session_id: str
    account_id: str | None
    action: str
    policy_version: str
    template_id: str
    triggered_at: int
    sent_at: int | None
    status: str
    metadata: dict[str, Any]


class FollowUpEngine:
    """合规跟进引擎。"""

    DEFAULT_TEMPLATES = [
        {"id": "gentle_reminder", "text": "您好，关于您咨询的商品，还需要了解更多信息吗？随时可以继续沟通。"},
        {"id": "service_check", "text": "您好，请问还有什么可以帮您的吗？如有需要可以随时留言。"},
        {"id": "final_check", "text": "最后确认一下，如果您暂时不需要了也可以直接忽略此消息，祝您生活愉快！"},
    ]

    def __init__(
        self,
        policy: FollowUpPolicy | None = None,
        db_path: str = "data/followup.db",
        templates: list[dict[str, str]] | None = None,
    ):
        self.policy = policy or FollowUpPolicy()
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.templates = templates or self.DEFAULT_TEMPLATES
        self.logger = get_logger()
        self._policy_version = "v1"
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS followup_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    account_id TEXT,
                    action TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    template_id TEXT,
                    triggered_at INTEGER NOT NULL,
                    sent_at INTEGER,
                    status TEXT NOT NULL,
                    metadata TEXT,
                    created_at INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_followup_session
                ON followup_audit(session_id, triggered_at DESC);

                CREATE INDEX IF NOT EXISTS idx_followup_account
                ON followup_audit(account_id, triggered_at DESC);

                CREATE TABLE IF NOT EXISTS do_not_disturb (
                    session_id TEXT PRIMARY KEY,
                    reason TEXT,
                    blocked_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS followup_state (
                    session_id TEXT PRIMARY KEY,
                    last_read_at INTEGER,
                    last_reply_at INTEGER,
                    touch_count INTEGER NOT NULL DEFAULT 0,
                    last_touch_at INTEGER,
                    next_eligible_at INTEGER,
                    status TEXT NOT NULL DEFAULT 'pending'
                );
                """
            )

    def _is_silent_hours(self) -> bool:
        now = datetime.now(UTC)
        hour = now.hour
        start = self.policy.silent_hours_start
        end = self.policy.silent_hours_end
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end

    def _get_touch_stats(self, session_id: str) -> tuple[int, int]:
        now = int(time.time())
        day_start = now - (now % 86400)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS c FROM followup_audit
                WHERE session_id=? AND triggered_at>=? AND status='sent'
                """,
                (session_id, day_start),
            ).fetchone()
            daily_count = int(row["c"]) if row else 0

            last_row = conn.execute(
                """
                SELECT triggered_at FROM followup_audit
                WHERE session_id=? AND status='sent'
                ORDER BY triggered_at DESC LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            last_touch_ts = int(last_row["triggered_at"]) if last_row else 0
        return daily_count, last_touch_ts

    def _is_on_dnd_list(self, session_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM do_not_disturb WHERE session_id=?", (session_id,)).fetchone()
            return row is not None

    def _add_to_dnd(self, session_id: str, reason: str) -> None:
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO do_not_disturb(session_id, reason, blocked_at)
                VALUES (?, ?, ?)
                """,
                (session_id, reason, now),
            )

    def check_eligibility(
        self,
        session_id: str,
        account_id: str | None = None,
        last_read_at: int | None = None,
        last_reply_at: int | None = None,
    ) -> tuple[bool, str]:
        if self._is_on_dnd_list(session_id):
            return False, "do_not_disturb"

        if self._is_silent_hours():
            return False, "silent_hours"

        daily_count, last_touch_ts = self._get_touch_stats(session_id)
        if daily_count >= self.policy.max_touches_per_day:
            return False, f"daily_limit:{daily_count}/{self.policy.max_touches_per_day}"

        if last_touch_ts > 0:
            elapsed_hours = (time.time() - last_touch_ts) / 3600
            if elapsed_hours < self.policy.min_interval_hours:
                remaining = self.policy.min_interval_hours - elapsed_hours
                return False, f"cooldown:{remaining:.1f}h_remaining"

        if last_read_at and last_reply_at:
            if last_reply_at > last_read_at:
                return False, "already_replied"

        return True, "eligible"

    def select_template(self, touch_count: int) -> dict[str, str] | None:
        if touch_count < 0:
            return None
        idx = min(touch_count, len(self.templates) - 1)
        return self.templates[idx]

    def validate_template(self, template_text: str) -> tuple[bool, str]:
        text = (template_text or "").lower()
        for kw in self.policy.forbidden_keywords:
            if kw.lower() in text:
                return False, f"forbidden_keyword:{kw}"

        has_allowed = any(kw.lower() in text for kw in self.policy.allowed_keywords)
        if not has_allowed:
            return False, "missing_service_keyword"
        return True, "valid"

    def record_trigger(
        self,
        session_id: str,
        account_id: str | None,
        action: str,
        template_id: str,
        status: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        now = int(time.time())
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO followup_audit(
                    session_id, account_id, action, policy_version, template_id,
                    triggered_at, sent_at, status, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    account_id,
                    action,
                    self._policy_version,
                    template_id,
                    now,
                    now if status == "sent" else None,
                    status,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                ),
            )
            return int(cur.lastrowcount)

    def process_session(
        self,
        session_id: str,
        account_id: str | None = None,
        last_read_at: int | None = None,
        last_reply_at: int | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        eligible, reason = self.check_eligibility(
            session_id=session_id,
            account_id=account_id,
            last_read_at=last_read_at,
            last_reply_at=last_reply_at,
        )

        if not eligible:
            return {
                "session_id": session_id,
                "eligible": False,
                "reason": reason,
                "dry_run": dry_run,
            }

        daily_count, _ = self._get_touch_stats(session_id)
        template = self.select_template(daily_count)
        if not template:
            return {
                "session_id": session_id,
                "eligible": False,
                "reason": "no_template",
                "dry_run": dry_run,
            }

        valid, validation_reason = self.validate_template(template["text"])
        if not valid:
            self.logger.warning(f"Template validation failed: {validation_reason}")
            return {
                "session_id": session_id,
                "eligible": False,
                "reason": f"template_invalid:{validation_reason}",
                "dry_run": dry_run,
            }

        audit_id = self.record_trigger(
            session_id=session_id,
            account_id=account_id,
            action="followup",
            template_id=template["id"],
            status="sent" if not dry_run else "dry_run",
            metadata={"touch_count": daily_count + 1},
        )

        return {
            "session_id": session_id,
            "eligible": True,
            "template_id": template["id"],
            "template_text": template["text"],
            "touch_count": daily_count + 1,
            "audit_id": audit_id,
            "dry_run": dry_run,
        }

    def add_dnd(self, session_id: str, reason: str = "user_reject") -> bool:
        self._add_to_dnd(session_id, reason)
        return True

    def remove_dnd(self, session_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM do_not_disturb WHERE session_id=?", (session_id,))
            return cur.rowcount > 0

    def get_audit_log(
        self,
        session_id: str | None = None,
        account_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM followup_audit WHERE 1=1"
        params: list[Any] = []

        if session_id:
            sql += " AND session_id=?"
            params.append(session_id)
        if account_id:
            sql += " AND account_id=?"
            params.append(account_id)

        sql += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, limit))

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            data["metadata"] = json.loads(data.get("metadata") or "{}")
            result.append(data)
        return result

    def get_dnd_list(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM do_not_disturb ORDER BY blocked_at DESC").fetchall()
            return [dict(r) for r in rows]

    def get_stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS c FROM followup_audit").fetchone()["c"]
            sent = conn.execute("SELECT COUNT(*) AS c FROM followup_audit WHERE status='sent'").fetchone()["c"]
            dnd_count = conn.execute("SELECT COUNT(*) AS c FROM do_not_disturb").fetchone()["c"]
        return {
            "total_triggers": total,
            "sent_count": sent,
            "dnd_count": dnd_count,
            "policy_version": self._policy_version,
        }

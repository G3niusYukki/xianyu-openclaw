"""分级合规策略中心与审计回放。"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class ComplianceDecision:
    allowed: bool
    blocked: bool
    reason: str
    hits: list[str]
    policy_scope: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "blocked": self.blocked,
            "reason": self.reason,
            "hits": self.hits,
            "policy_scope": self.policy_scope,
        }


class ComplianceCenter:
    """支持 global/account/session 三级覆盖的策略中心。"""

    def __init__(
        self,
        policy_path: str = "config/compliance_policies.yaml",
        db_path: str = "data/compliance.db",
    ) -> None:
        self.policy_path = Path(policy_path)
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._policy_mtime: float | None = None
        self._policies: dict[str, Any] = {}
        self._init_db()
        self.reload()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS compliance_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor TEXT,
                    account_id TEXT,
                    session_id TEXT,
                    action TEXT NOT NULL,
                    content TEXT,
                    decision TEXT NOT NULL,
                    blocked INTEGER NOT NULL,
                    hits_json TEXT,
                    policy_scope TEXT,
                    policy_version TEXT,
                    created_at INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_compliance_audit_time ON compliance_audit(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_compliance_audit_session
                ON compliance_audit(session_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_compliance_audit_account
                ON compliance_audit(account_id, created_at DESC);
                """
            )

    def reload(self) -> None:
        defaults = {
            "version": "v1",
            "reload": {"auto_reload": True, "check_interval_seconds": 10},
            "global": {
                "whitelist": [],
                "blacklist": [],
                "stop_words": ["微信", "vx", "v信", "站外", "转账"],
                "rate_limit": {
                    "account": {"window_seconds": 60, "max_messages": 20},
                    "session": {"window_seconds": 60, "max_messages": 8},
                },
            },
            "accounts": {},
            "sessions": {},
        }

        loaded: dict[str, Any] = {}
        if self.policy_path.exists():
            with open(self.policy_path, encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
            self._policy_mtime = self.policy_path.stat().st_mtime

        self._policies = defaults
        self._merge_dict(self._policies, loaded)

    def _merge_dict(self, base: dict[str, Any], override: dict[str, Any]) -> None:
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                self._merge_dict(base[key], value)
            else:
                base[key] = value

    def _auto_reload(self) -> None:
        reload_cfg = self._policies.get("reload", {})
        if not reload_cfg.get("auto_reload", True):
            return
        if not self.policy_path.exists():
            return
        current = self.policy_path.stat().st_mtime
        if self._policy_mtime is None or current > self._policy_mtime:
            self.reload()

    def _scope_policy(self, account_id: str | None, session_id: str | None) -> tuple[dict[str, Any], str]:
        policy: dict[str, Any] = {}
        self._merge_dict(policy, self._policies.get("global", {}))
        scope = "global"

        if account_id and account_id in self._policies.get("accounts", {}):
            self._merge_dict(policy, self._policies["accounts"][account_id])
            scope = f"account:{account_id}"

        if session_id and session_id in self._policies.get("sessions", {}):
            self._merge_dict(policy, self._policies["sessions"][session_id])
            scope = f"session:{session_id}"

        return policy, scope

    def _rate_limit_block(
        self,
        action: str,
        account_id: str | None,
        session_id: str | None,
        policy: dict[str, Any],
    ) -> tuple[bool, str]:
        now = int(time.time())
        with self._connect() as conn:
            account_rule = policy.get("rate_limit", {}).get("account", {})
            if account_id and account_rule:
                window = int(account_rule.get("window_seconds", 60))
                max_messages = int(account_rule.get("max_messages", 20))
                cnt = conn.execute(
                    "SELECT COUNT(*) AS c FROM compliance_audit WHERE account_id=? AND action=? AND created_at>=?",
                    (account_id, action, now - window),
                ).fetchone()["c"]
                if int(cnt) >= max_messages:
                    return True, f"account_rate_limit:{cnt}/{max_messages}"

            session_rule = policy.get("rate_limit", {}).get("session", {})
            if session_id and session_rule:
                window = int(session_rule.get("window_seconds", 60))
                max_messages = int(session_rule.get("max_messages", 8))
                cnt = conn.execute(
                    "SELECT COUNT(*) AS c FROM compliance_audit WHERE session_id=? AND action=? AND created_at>=?",
                    (session_id, action, now - window),
                ).fetchone()["c"]
                if int(cnt) >= max_messages:
                    return True, f"session_rate_limit:{cnt}/{max_messages}"

        return False, ""

    def evaluate_before_send(
        self,
        content: str,
        *,
        actor: str = "system",
        account_id: str | None = None,
        session_id: str | None = None,
        action: str = "message_send",
    ) -> ComplianceDecision:
        self._auto_reload()
        policy, scope = self._scope_policy(account_id, session_id)

        text = (content or "").strip()
        lowered = text.lower()

        whitelist = [str(x).lower() for x in policy.get("whitelist", [])]
        blacklist = [str(x).lower() for x in policy.get("blacklist", [])]
        stop_words = [str(x).lower() for x in policy.get("stop_words", [])]

        if any(w and w in lowered for w in whitelist):
            decision = ComplianceDecision(True, False, "whitelist_pass", [], scope)
            self.audit(actor, account_id, session_id, action, text, decision)
            return decision

        hits = [w for w in stop_words if w and w in lowered]
        if hits:
            decision = ComplianceDecision(False, True, "high_risk_stop_word", hits, scope)
            self.audit(actor, account_id, session_id, action, text, decision)
            return decision

        blocked_hits = [w for w in blacklist if w and w in lowered]
        if blocked_hits:
            decision = ComplianceDecision(False, True, "blacklist_hit", blocked_hits, scope)
            self.audit(actor, account_id, session_id, action, text, decision)
            return decision

        blocked, reason = self._rate_limit_block(action, account_id, session_id, policy)
        if blocked:
            decision = ComplianceDecision(False, True, reason, [], scope)
            self.audit(actor, account_id, session_id, action, text, decision)
            return decision

        decision = ComplianceDecision(True, False, "pass", [], scope)
        self.audit(actor, account_id, session_id, action, text, decision)
        return decision

    def audit(
        self,
        actor: str,
        account_id: str | None,
        session_id: str | None,
        action: str,
        content: str,
        decision: ComplianceDecision,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO compliance_audit(
                    actor, account_id, session_id, action, content, decision,
                    blocked, hits_json, policy_scope, policy_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    actor,
                    account_id,
                    session_id,
                    action,
                    content,
                    decision.reason,
                    1 if decision.blocked else 0,
                    json.dumps(decision.hits, ensure_ascii=False),
                    decision.policy_scope,
                    str(self._policies.get("version", "v1")),
                    int(time.time()),
                ),
            )

    def replay(
        self,
        *,
        account_id: str | None = None,
        session_id: str | None = None,
        blocked_only: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM compliance_audit WHERE 1=1"
        params: list[Any] = []

        if account_id:
            sql += " AND account_id=?"
            params.append(account_id)
        if session_id:
            sql += " AND session_id=?"
            params.append(session_id)
        if blocked_only:
            sql += " AND blocked=1"

        sql += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, limit))

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            data["blocked"] = bool(data.get("blocked", 0))
            data["hits"] = json.loads(data.get("hits_json") or "[]")
            result.append(data)
        return result

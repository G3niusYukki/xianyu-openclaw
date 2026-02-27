"""
会话跟进状态持久化
Session follow-up state store
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Lock
from typing import Any


class FollowupStateStore:
    """基于 JSON 文件的轻量会话状态存储。"""

    def __init__(self, path: str = "data/messages_followup_state.json", max_sessions: int = 5000):
        self.path = Path(path)
        self.max_sessions = int(max_sessions) if int(max_sessions) > 0 else 5000
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def get(self, session_id: str) -> dict[str, Any]:
        sid = str(session_id).strip()
        if not sid:
            return {}
        with self._lock:
            data = self._load_all()
            record = data.get(sid, {})
            return dict(record) if isinstance(record, dict) else {}

    def upsert(self, session_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        sid = str(session_id).strip()
        if not sid:
            return {}
        with self._lock:
            data = self._load_all()
            now = time.time()
            record = data.get(sid, {})
            if not isinstance(record, dict):
                record = {}
            record.update(updates)
            record["updated_at"] = now
            record.setdefault("created_at", now)
            data[sid] = record
            data = self._prune_if_needed(data)
            self._save_all(data)
            return dict(record)

    def record_inbound(self, session_id: str, message: str) -> dict[str, Any]:
        """记录买家新消息，并重置跟进计数。"""
        return self.upsert(
            session_id,
            {
                "last_inbound_message": str(message or "").strip(),
                "last_inbound_at": time.time(),
                "followup_sent_count": 0,
                "opted_out": False,
            },
        )

    def record_first_reply(self, session_id: str, message: str, item_title: str = "") -> dict[str, Any]:
        """记录首响发送时间，用于后续已读未回跟进判断。"""
        now = time.time()
        return self.upsert(
            session_id,
            {
                "first_reply_at": now,
                "last_outbound_at": now,
                "last_outbound_message": str(message or "").strip(),
                "last_item_title": str(item_title or "").strip(),
                "followup_sent_count": 0,
            },
        )

    def record_outbound(self, session_id: str, message: str, item_title: str = "") -> dict[str, Any]:
        """记录普通外发消息（不计入已读未回跟进次数）。"""
        return self.upsert(
            session_id,
            {
                "last_outbound_at": time.time(),
                "last_outbound_message": str(message or "").strip(),
                "last_item_title": str(item_title or "").strip(),
            },
        )

    def record_followup_sent(self, session_id: str, message: str, item_title: str = "") -> dict[str, Any]:
        """记录已读未回跟进发送。"""
        current = self.get(session_id)
        count = int(current.get("followup_sent_count") or 0) + 1
        return self.upsert(
            session_id,
            {
                "last_followup_at": time.time(),
                "last_outbound_at": time.time(),
                "last_outbound_message": str(message or "").strip(),
                "last_item_title": str(item_title or "").strip(),
                "followup_sent_count": count,
            },
        )

    def mark_opt_out(self, session_id: str) -> dict[str, Any]:
        """标记买家明确拒绝跟进。"""
        return self.upsert(
            session_id,
            {
                "opted_out": True,
                "opted_out_at": time.time(),
            },
        )

    def _load_all(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            raw = self.path.read_text(encoding="utf-8").strip()
            if not raw:
                return {}
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_all(self, data: dict[str, Any]) -> None:
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.path)

    def _prune_if_needed(self, data: dict[str, Any]) -> dict[str, Any]:
        if len(data) <= self.max_sessions:
            return data
        ordered = sorted(
            data.items(),
            key=lambda item: self._safe_float(item[1].get("updated_at")) if isinstance(item[1], dict) else 0.0,
            reverse=True,
        )
        keep = ordered[: self.max_sessions]
        return {session_id: record for session_id, record in keep}

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

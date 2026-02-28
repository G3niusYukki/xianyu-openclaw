"""自动化推进配置助手。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


class AutomationSetupService:
    """为消息自动化与飞书通知生成低门槛配置。"""

    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = Path(config_path)

    def apply(
        self,
        *,
        poll_interval_seconds: float = 1.0,
        scan_limit: int = 20,
        claim_limit: int = 10,
        reply_target_seconds: float = 3.0,
        feishu_enabled: bool = False,
        feishu_webhook: str = "",
        notify_on_start: bool = True,
        notify_on_alert: bool = True,
        notify_recovery: bool = True,
        heartbeat_minutes: int = 30,
    ) -> dict[str, Any]:
        data, existed = self._load_yaml()

        messages_cfg = data.get("messages")
        if not isinstance(messages_cfg, dict):
            messages_cfg = {}
            data["messages"] = messages_cfg

        messages_cfg["enabled"] = True
        messages_cfg["transport"] = "ws"
        messages_cfg["fast_reply_enabled"] = True
        messages_cfg["reply_target_seconds"] = max(0.5, float(reply_target_seconds))

        workflow_cfg = messages_cfg.get("workflow")
        if not isinstance(workflow_cfg, dict):
            workflow_cfg = {}
            messages_cfg["workflow"] = workflow_cfg

        workflow_cfg["db_path"] = str(workflow_cfg.get("db_path") or "data/workflow.db")
        workflow_cfg["poll_interval_seconds"] = max(0.2, float(poll_interval_seconds))
        workflow_cfg["scan_limit"] = max(1, int(scan_limit))
        workflow_cfg["claim_limit"] = max(1, int(claim_limit))
        workflow_cfg["lease_seconds"] = int(workflow_cfg.get("lease_seconds", 60))
        workflow_cfg["max_attempts"] = int(workflow_cfg.get("max_attempts", 3))
        workflow_cfg["backoff_seconds"] = int(workflow_cfg.get("backoff_seconds", 2))

        notifications = workflow_cfg.get("notifications")
        if not isinstance(notifications, dict):
            notifications = {}
            workflow_cfg["notifications"] = notifications

        feishu_cfg = notifications.get("feishu")
        if not isinstance(feishu_cfg, dict):
            feishu_cfg = {}
            notifications["feishu"] = feishu_cfg

        feishu_cfg["enabled"] = bool(feishu_enabled)
        if feishu_webhook:
            feishu_cfg["webhook"] = str(feishu_webhook).strip()
        feishu_cfg["notify_on_start"] = bool(notify_on_start)
        feishu_cfg["notify_on_alert"] = bool(notify_on_alert)
        feishu_cfg["notify_recovery"] = bool(notify_recovery)
        feishu_cfg["heartbeat_minutes"] = max(0, int(heartbeat_minutes))
        feishu_cfg["bot_name"] = str(feishu_cfg.get("bot_name") or "闲鱼自动化助手")

        backup_path = self._backup_existing_file() if existed else None
        self._write_yaml(data)

        status = self.status()
        return {
            "success": True,
            "config_path": str(self.config_path),
            "backup_path": str(backup_path) if backup_path else "",
            "status": status,
        }

    def status(self) -> dict[str, Any]:
        data, _ = self._load_yaml()
        messages_cfg = data.get("messages") if isinstance(data.get("messages"), dict) else {}
        workflow_cfg = messages_cfg.get("workflow") if isinstance(messages_cfg.get("workflow"), dict) else {}
        feishu_cfg = (
            workflow_cfg.get("notifications", {}).get("feishu", {})
            if isinstance(workflow_cfg.get("notifications"), dict)
            else {}
        )
        webhook = str(feishu_cfg.get("webhook", "")).strip()

        return {
            "messages_enabled": bool(messages_cfg.get("enabled", False)),
            "transport": str(messages_cfg.get("transport", "dom")),
            "fast_reply_enabled": bool(messages_cfg.get("fast_reply_enabled", False)),
            "reply_target_seconds": float(messages_cfg.get("reply_target_seconds", 3.0)),
            "workflow": {
                "db_path": str(workflow_cfg.get("db_path", "")),
                "poll_interval_seconds": float(workflow_cfg.get("poll_interval_seconds", 1.0)),
                "scan_limit": int(workflow_cfg.get("scan_limit", 20)),
                "claim_limit": int(workflow_cfg.get("claim_limit", 10)),
            },
            "feishu": {
                "enabled": bool(feishu_cfg.get("enabled", False)),
                "webhook_configured": bool(webhook),
                "notify_on_start": bool(feishu_cfg.get("notify_on_start", False)),
                "notify_on_alert": bool(feishu_cfg.get("notify_on_alert", True)),
                "notify_recovery": bool(feishu_cfg.get("notify_recovery", True)),
                "heartbeat_minutes": int(feishu_cfg.get("heartbeat_minutes", 30)),
            },
        }

    def get_feishu_webhook(self) -> str:
        data, _ = self._load_yaml()
        messages_cfg = data.get("messages") if isinstance(data.get("messages"), dict) else {}
        workflow_cfg = messages_cfg.get("workflow") if isinstance(messages_cfg.get("workflow"), dict) else {}
        notifications = workflow_cfg.get("notifications") if isinstance(workflow_cfg.get("notifications"), dict) else {}
        feishu_cfg = notifications.get("feishu") if isinstance(notifications.get("feishu"), dict) else {}
        return str(feishu_cfg.get("webhook", "")).strip()

    def _load_yaml(self) -> tuple[dict[str, Any], bool]:
        if self.config_path.exists():
            raw = self.config_path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw) or {}
            if not isinstance(data, dict):
                data = {}
            return data, True

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        example_path = self.config_path.parent / "config.example.yaml"
        if example_path.exists():
            raw = example_path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw) or {}
            if not isinstance(data, dict):
                data = {}
            return data, False
        return {}, False

    def _backup_existing_file(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup_path = self.config_path.with_name(f"{self.config_path.name}.bak.{stamp}")
        backup_path.write_text(self.config_path.read_text(encoding="utf-8"), encoding="utf-8")
        return backup_path

    def _write_yaml(self, data: dict[str, Any]) -> None:
        payload = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
        self.config_path.write_text(payload, encoding="utf-8")

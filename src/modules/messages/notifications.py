"""消息自动化通知（飞书 webhook）。"""

from __future__ import annotations

from typing import Any

import httpx


class FeishuNotifier:
    """飞书机器人 webhook 通知。"""

    def __init__(self, webhook_url: str, *, bot_name: str = "闲鱼自动化助手", timeout_seconds: float = 5.0):
        self.webhook_url = str(webhook_url or "").strip()
        self.bot_name = str(bot_name or "闲鱼自动化助手").strip()
        self.timeout_seconds = max(1.0, float(timeout_seconds))

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)

    async def send_text(self, text: str) -> bool:
        if not self.enabled:
            return False

        payload = {
            "msg_type": "text",
            "content": {"text": str(text or "").strip()},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(self.webhook_url, json=payload)
            return 200 <= resp.status_code < 300
        except Exception:
            return False


def format_alert_message(alerts: list[dict[str, Any]], sla: dict[str, Any], workflow: dict[str, Any]) -> str:
    lines = [f"【闲鱼自动化】SLA 告警 x{len(alerts)}"]
    for item in alerts:
        title = str(item.get("title", "")).strip()
        message = str(item.get("message", "")).strip()
        lines.append(f"- {title}: {message}" if title else f"- {message}")

    lines.append(
        "首响P95={p95}ms, 报价成功率={rate}, 回退率={fallback}".format(
            p95=sla.get("first_reply_p95_ms", 0),
            rate=sla.get("quote_success_rate", 0),
            fallback=sla.get("quote_fallback_rate", 0),
        )
    )
    lines.append(
        "jobs={jobs}, states={states}".format(
            jobs=workflow.get("jobs", {}),
            states=workflow.get("states", {}),
        )
    )
    return "\n".join(lines)


def format_recovery_message(sla: dict[str, Any], workflow: dict[str, Any]) -> str:
    return "\n".join(
        [
            "【闲鱼自动化】告警恢复",
            "当前首响P95={p95}ms, 报价成功率={rate}, 回退率={fallback}".format(
                p95=sla.get("first_reply_p95_ms", 0),
                rate=sla.get("quote_success_rate", 0),
                fallback=sla.get("quote_fallback_rate", 0),
            ),
            f"jobs={workflow.get('jobs', {})}, states={workflow.get('states', {})}",
        ]
    )


def format_start_message(interval_seconds: float, dry_run: bool = False) -> str:
    return "\n".join(
        [
            "【闲鱼自动化】Workflow Worker 已启动",
            f"poll_interval={interval_seconds}s",
            f"dry_run={bool(dry_run)}",
        ]
    )


def format_heartbeat_message(last: dict[str, Any], loops: int) -> str:
    sla = last.get("sla", {}) if isinstance(last, dict) else {}
    workflow = last.get("workflow", {}) if isinstance(last, dict) else {}
    return "\n".join(
        [
            f"【闲鱼自动化】心跳 loops={loops}",
            "unread={unread}, enqueued={enqueued}, claimed={claimed}, success={success}, failed={failed}".format(
                unread=last.get("unread_sessions", 0),
                enqueued=last.get("enqueued", 0),
                claimed=last.get("claimed", 0),
                success=last.get("success", 0),
                failed=last.get("failed", 0),
            ),
            "首响P95={p95}ms, 报价成功率={rate}".format(
                p95=sla.get("first_reply_p95_ms", 0),
                rate=sla.get("quote_success_rate", 0),
            ),
            f"states={workflow.get('states', {})}",
        ]
    )


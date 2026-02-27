"""
消息工作流 SLA 监控与告警
Workflow SLA monitor and alerts
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Lock
from typing import Any


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    q = max(0.0, min(1.0, q))
    sorted_vals = sorted(float(v) for v in values)
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    weight = pos - lo
    return float(sorted_vals[lo] * (1 - weight) + sorted_vals[hi] * weight)


class WorkflowSlaMonitor:
    """记录 worker 周期指标并评估告警。"""

    def __init__(self, config: dict[str, Any] | None = None):
        cfg = config or {}
        self.enabled = bool(cfg.get("worker_sla_enabled", True))
        self.path = Path(str(cfg.get("worker_sla_path", "data/workflow_sla_metrics.json")))
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self.window_size = self._safe_int(cfg.get("worker_sla_window_size"), default=500, minimum=10)
        self.alert_min_samples = self._safe_int(cfg.get("worker_alert_min_samples"), default=10, minimum=1)
        self.alert_failure_rate_threshold = self._safe_float(
            cfg.get("worker_alert_failure_rate_threshold"),
            default=0.2,
            minimum=0.0,
        )
        self.alert_first_reply_ratio_threshold = self._safe_float(
            cfg.get("worker_alert_first_reply_within_target_ratio_threshold"),
            default=0.7,
            minimum=0.0,
        )
        self.alert_cycle_p95_seconds = self._safe_float(
            cfg.get("worker_alert_cycle_p95_seconds"),
            default=20.0,
            minimum=0.1,
        )
        self._lock = Lock()

    @staticmethod
    def _safe_int(raw: Any, default: int, minimum: int) -> int:
        try:
            value = int(raw)
            if value < minimum:
                return default
            return value
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_float(raw: Any, default: float, minimum: float) -> float:
        try:
            value = float(raw)
            if value < minimum:
                return default
            return value
        except (TypeError, ValueError):
            return default

    def record_cycle(
        self,
        *,
        cycle_status: str,
        duration_seconds: float,
        cycle_result: dict[str, Any] | None = None,
        error: str = "",
    ) -> dict[str, Any]:
        """
        记录单轮 worker 指标并返回最新 summary/alerts。
        """
        if not self.enabled:
            return {"enabled": False, "summary": {}, "alerts": []}

        sample = self._build_sample(
            cycle_status=cycle_status,
            duration_seconds=duration_seconds,
            cycle_result=cycle_result,
            error=error,
        )

        with self._lock:
            data = self._read_all()
            cycles = data.get("cycles", [])
            if not isinstance(cycles, list):
                cycles = []
            cycles.append(sample)
            cycles = cycles[-self.window_size :]

            summary = self._compute_summary(cycles)
            alerts = self._evaluate_alerts(summary)

            payload = {
                "enabled": True,
                "window_size": self.window_size,
                "updated_at": time.time(),
                "cycles": cycles,
                "summary": summary,
                "alerts": alerts,
            }
            self._write_all(payload)

            return {"enabled": True, "summary": summary, "alerts": alerts}

    def get_snapshot(self) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "summary": {}, "alerts": [], "cycles": []}
        with self._lock:
            data = self._read_all()
            if not data:
                return {"enabled": True, "summary": {}, "alerts": [], "cycles": []}
            return data

    def _build_sample(
        self,
        *,
        cycle_status: str,
        duration_seconds: float,
        cycle_result: dict[str, Any] | None,
        error: str,
    ) -> dict[str, Any]:
        sample: dict[str, Any] = {
            "ts": time.time(),
            "status": str(cycle_status or "unknown"),
            "duration_seconds": round(float(duration_seconds), 3),
            "error": str(error or ""),
            "processed_sessions": 0,
            "first_reply_total": 0,
            "first_reply_within_target": 0,
            "quote_followup_total": 0,
            "quote_followup_success": 0,
            "read_no_reply_followup_total": 0,
            "read_no_reply_followup_success": 0,
            "first_reply_target_seconds": 0.0,
        }

        if not isinstance(cycle_result, dict):
            return sample

        stages = cycle_result.get("stages", {})
        if not isinstance(stages, dict):
            return sample

        stage1 = stages.get("auto_reply_unread", {})
        stage2 = stages.get("auto_followup_read_no_reply", {})
        if isinstance(stage1, dict):
            sample["processed_sessions"] = int(stage1.get("total", 0) or 0)
            sample["first_reply_total"] = int(stage1.get("total", 0) or 0)
            sample["first_reply_within_target"] = int(stage1.get("first_reply_within_target", 0) or 0)
            sample["quote_followup_total"] = int(stage1.get("quote_followup_total", 0) or 0)
            sample["quote_followup_success"] = int(stage1.get("quote_followup_success", 0) or 0)
            sample["first_reply_target_seconds"] = float(stage1.get("first_reply_target_seconds", 0.0) or 0.0)
        if isinstance(stage2, dict):
            sample["read_no_reply_followup_total"] = int(stage2.get("eligible", 0) or 0)
            sample["read_no_reply_followup_success"] = int(stage2.get("success", 0) or 0)

        return sample

    def _compute_summary(self, cycles: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(cycles)
        success = sum(1 for item in cycles if str(item.get("status")) == "success")
        failed = total - success
        durations = [float(item.get("duration_seconds") or 0.0) for item in cycles]

        first_reply_total = sum(int(item.get("first_reply_total") or 0) for item in cycles)
        first_reply_within = sum(int(item.get("first_reply_within_target") or 0) for item in cycles)
        quote_total = sum(int(item.get("quote_followup_total") or 0) for item in cycles)
        quote_success = sum(int(item.get("quote_followup_success") or 0) for item in cycles)
        rn_total = sum(int(item.get("read_no_reply_followup_total") or 0) for item in cycles)
        rn_success = sum(int(item.get("read_no_reply_followup_success") or 0) for item in cycles)

        failure_rate = (failed / total) if total > 0 else 0.0
        first_reply_ratio = (first_reply_within / first_reply_total) if first_reply_total > 0 else 1.0
        quote_ratio = (quote_success / quote_total) if quote_total > 0 else 1.0
        rn_ratio = (rn_success / rn_total) if rn_total > 0 else 1.0

        return {
            "total_cycles": total,
            "success_cycles": success,
            "failed_cycles": failed,
            "failure_rate": round(failure_rate, 4),
            "cycle_duration_p50_seconds": round(_percentile(durations, 0.5), 3),
            "cycle_duration_p95_seconds": round(_percentile(durations, 0.95), 3),
            "first_reply_total": first_reply_total,
            "first_reply_within_target": first_reply_within,
            "first_reply_within_target_ratio": round(first_reply_ratio, 4),
            "quote_followup_total": quote_total,
            "quote_followup_success": quote_success,
            "quote_followup_success_ratio": round(quote_ratio, 4),
            "read_no_reply_followup_total": rn_total,
            "read_no_reply_followup_success": rn_success,
            "read_no_reply_followup_success_ratio": round(rn_ratio, 4),
            "last_cycle_at": float(cycles[-1].get("ts")) if cycles else 0.0,
        }

    def _evaluate_alerts(self, summary: dict[str, Any]) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        total_cycles = int(summary.get("total_cycles", 0) or 0)
        if total_cycles < self.alert_min_samples:
            return alerts

        failure_rate = float(summary.get("failure_rate", 0.0) or 0.0)
        if failure_rate >= self.alert_failure_rate_threshold:
            alerts.append(
                {
                    "code": "HIGH_FAILURE_RATE",
                    "severity": "high",
                    "message": f"failure_rate={failure_rate:.2%} >= threshold={self.alert_failure_rate_threshold:.2%}",
                }
            )

        first_reply_total = int(summary.get("first_reply_total", 0) or 0)
        first_reply_ratio = float(summary.get("first_reply_within_target_ratio", 1.0) or 1.0)
        if first_reply_total >= self.alert_min_samples and first_reply_ratio < self.alert_first_reply_ratio_threshold:
            alerts.append(
                {
                    "code": "FIRST_REPLY_SLA_DEGRADED",
                    "severity": "medium",
                    "message": (
                        f"first_reply_within_target_ratio={first_reply_ratio:.2%} "
                        f"< threshold={self.alert_first_reply_ratio_threshold:.2%}"
                    ),
                }
            )

        p95 = float(summary.get("cycle_duration_p95_seconds", 0.0) or 0.0)
        if p95 > self.alert_cycle_p95_seconds:
            alerts.append(
                {
                    "code": "WORKFLOW_CYCLE_SLOW",
                    "severity": "medium",
                    "message": f"cycle_duration_p95={p95:.2f}s > threshold={self.alert_cycle_p95_seconds:.2f}s",
                }
            )

        return alerts

    def _read_all(self) -> dict[str, Any]:
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

    def _write_all(self, data: dict[str, Any]) -> None:
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.path)

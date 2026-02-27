"""workflow SLA 监控测试。"""

from pathlib import Path

from src.modules.messages.sla_monitor import WorkflowSlaMonitor


def test_sla_monitor_generates_failure_rate_alert(tmp_path: Path) -> None:
    monitor = WorkflowSlaMonitor(
        {
            "worker_sla_enabled": True,
            "worker_sla_path": str(tmp_path / "sla.json"),
            "worker_sla_window_size": 20,
            "worker_alert_min_samples": 3,
            "worker_alert_failure_rate_threshold": 0.5,
            "worker_alert_first_reply_within_target_ratio_threshold": 0.7,
            "worker_alert_cycle_p95_seconds": 20,
        }
    )

    monitor.record_cycle(cycle_status="failed", duration_seconds=1.0, cycle_result=None, error="e1")
    monitor.record_cycle(cycle_status="failed", duration_seconds=1.2, cycle_result=None, error="e2")
    snapshot = monitor.record_cycle(cycle_status="success", duration_seconds=1.1, cycle_result=None, error="")

    codes = {item["code"] for item in snapshot["alerts"]}
    assert "HIGH_FAILURE_RATE" in codes


def test_sla_monitor_generates_first_reply_alert(tmp_path: Path) -> None:
    monitor = WorkflowSlaMonitor(
        {
            "worker_sla_enabled": True,
            "worker_sla_path": str(tmp_path / "sla_first_reply.json"),
            "worker_sla_window_size": 20,
            "worker_alert_min_samples": 2,
            "worker_alert_failure_rate_threshold": 0.9,
            "worker_alert_first_reply_within_target_ratio_threshold": 0.8,
            "worker_alert_cycle_p95_seconds": 50,
        }
    )

    cycle_result = {
        "stages": {
            "auto_reply_unread": {
                "total": 5,
                "first_reply_within_target": 2,
                "quote_followup_total": 2,
                "quote_followup_success": 1,
                "first_reply_target_seconds": 3.0,
            },
            "auto_followup_read_no_reply": {
                "eligible": 2,
                "success": 1,
            },
        }
    }

    monitor.record_cycle(cycle_status="success", duration_seconds=2.0, cycle_result=cycle_result, error="")
    snapshot = monitor.record_cycle(cycle_status="success", duration_seconds=2.2, cycle_result=cycle_result, error="")

    codes = {item["code"] for item in snapshot["alerts"]}
    assert "FIRST_REPLY_SLA_DEGRADED" in codes

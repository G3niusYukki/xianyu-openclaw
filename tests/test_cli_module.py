"""CLI module command helper tests."""

from src.cli import _module_check_summary, _required_checks_for_module


def test_required_checks_cover_three_modules() -> None:
    presales = _required_checks_for_module("presales")
    operations = _required_checks_for_module("operations")
    aftersales = _required_checks_for_module("aftersales")

    assert "消息首响SLA" in presales
    assert "消息首响SLA" not in operations
    assert "消息首响SLA" not in aftersales
    assert "OpenClaw Gateway" in presales
    assert "OpenClaw Gateway" in operations
    assert "OpenClaw Gateway" in aftersales


def test_module_check_summary_blocks_when_required_check_fails() -> None:
    doctor_report = {
        "summary": {"total": 4, "failed": 1},
        "next_steps": ["fix"],
        "checks": [
            {"name": "Python版本", "passed": True},
            {"name": "数据库", "passed": True},
            {"name": "配置文件", "passed": False},
            {"name": "OpenClaw Gateway", "passed": True},
        ],
    }
    summary = _module_check_summary(target="aftersales", doctor_report=doctor_report)

    assert summary["ready"] is False
    assert len(summary["blockers"]) == 1
    assert summary["blockers"][0]["name"] == "配置文件"

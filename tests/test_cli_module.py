"""CLI module helper tests."""

from src.cli import _module_check_summary


def test_module_check_summary_blocks_when_base_required_check_fails(monkeypatch) -> None:
    monkeypatch.setattr("src.core.startup_checks.resolve_runtime_mode", lambda: "lite")
    doctor_report = {
        "summary": {"total": 5, "failed": 1},
        "next_steps": ["fix"],
        "checks": [
            {"name": "Python版本", "passed": True},
            {"name": "数据库", "passed": True},
            {"name": "配置文件", "passed": False},
            {"name": "闲鱼Cookie", "passed": True},
            {"name": "Lite 浏览器驱动", "passed": True},
        ],
    }

    summary = _module_check_summary(target="aftersales", doctor_report=doctor_report)

    assert summary["runtime"] == "lite"
    assert summary["ready"] is False
    assert any(item["name"] == "配置文件" for item in summary["blockers"])


def test_module_check_summary_auto_mode_accepts_gateway_or_lite(monkeypatch) -> None:
    monkeypatch.setattr("src.core.startup_checks.resolve_runtime_mode", lambda: "auto")
    doctor_report = {
        "summary": {"total": 6, "failed": 1},
        "next_steps": [],
        "checks": [
            {"name": "Python版本", "passed": True},
            {"name": "数据库", "passed": True},
            {"name": "配置文件", "passed": True},
            {"name": "闲鱼Cookie", "passed": True},
            {"name": "OpenClaw Gateway", "passed": False},
            {"name": "Lite 浏览器驱动", "passed": True},
            {"name": "消息首响SLA", "passed": True},
        ],
    }

    summary = _module_check_summary(target="presales", doctor_report=doctor_report)

    assert summary["ready"] is True
    assert not any(item["name"] == "浏览器运行时" for item in summary["blockers"])


def test_module_check_summary_auto_mode_blocks_when_gateway_and_lite_both_fail(monkeypatch) -> None:
    monkeypatch.setattr("src.core.startup_checks.resolve_runtime_mode", lambda: "auto")
    doctor_report = {
        "summary": {"total": 6, "failed": 2},
        "next_steps": [],
        "checks": [
            {"name": "Python版本", "passed": True},
            {"name": "数据库", "passed": True},
            {"name": "配置文件", "passed": True},
            {"name": "闲鱼Cookie", "passed": True},
            {"name": "OpenClaw Gateway", "passed": False},
            {"name": "Lite 浏览器驱动", "passed": False},
            {"name": "消息首响SLA", "passed": True},
        ],
    }

    summary = _module_check_summary(target="presales", doctor_report=doctor_report)

    assert summary["ready"] is False
    assert any(item["name"] == "浏览器运行时" for item in summary["blockers"])

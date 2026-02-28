"""CLI module helper tests."""

import argparse

import pytest

from src.cli import _module_check_summary, cmd_messages, cmd_module


def test_module_check_summary_blocks_when_base_required_check_fails(monkeypatch) -> None:
    monkeypatch.setattr("src.core.startup_checks.resolve_runtime_mode", lambda: "lite")
    monkeypatch.setattr("src.cli._messages_transport_mode", lambda: "dom")
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
    monkeypatch.setattr("src.cli._messages_transport_mode", lambda: "dom")
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
    monkeypatch.setattr("src.cli._messages_transport_mode", lambda: "dom")
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


def test_module_check_summary_ws_transport_skips_browser_runtime(monkeypatch) -> None:
    monkeypatch.setattr("src.core.startup_checks.resolve_runtime_mode", lambda: "auto")
    monkeypatch.setattr("src.cli._messages_transport_mode", lambda: "ws")
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

    assert summary["messages_transport"] == "ws"
    assert summary["ready"] is True
    assert not any(item["name"] == "浏览器运行时" for item in summary["blockers"])
@pytest.mark.asyncio
async def test_cmd_module_check_all_aggregates_results(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.core.doctor.run_doctor",
        lambda **_: {"summary": {"total": 1, "failed": 0}, "checks": [], "next_steps": ["step-a"]},
    )

    def fake_summary(target: str, doctor_report: dict) -> dict:
        return {
            "target": target,
            "runtime": "lite",
            "ready": target != "operations",
            "required_checks": [],
            "blockers": [] if target != "operations" else [{"name": "配置文件", "passed": False}],
            "next_steps": doctor_report.get("next_steps", []),
            "doctor_summary": doctor_report.get("summary", {}),
        }

    outputs: list[dict] = []
    monkeypatch.setattr("src.cli._module_check_summary", fake_summary)
    monkeypatch.setattr("src.cli._json_out", lambda data: outputs.append(data))

    args = argparse.Namespace(action="check", target="all", skip_gateway=False, strict=False)
    await cmd_module(args)

    assert len(outputs) == 1
    payload = outputs[0]
    assert payload["target"] == "all"
    assert payload["ready"] is False
    assert set(payload["modules"].keys()) == {"presales", "operations", "aftersales"}
    assert any(item["target"] == "operations" for item in payload["blockers"])


@pytest.mark.asyncio
async def test_cmd_module_check_all_strict_exits_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.core.doctor.run_doctor",
        lambda **_: {"summary": {}, "checks": [], "next_steps": []},
    )

    monkeypatch.setattr(
        "src.cli._module_check_summary",
        lambda target, doctor_report: {
            "target": target,
            "runtime": "auto",
            "ready": False,
            "required_checks": [],
            "blockers": [{"name": "x"}],
            "next_steps": [],
            "doctor_summary": {},
        },
    )
    monkeypatch.setattr("src.cli._json_out", lambda data: None)

    args = argparse.Namespace(action="check", target="all", skip_gateway=False, strict=True)
    with pytest.raises(SystemExit) as exc_info:
        await cmd_module(args)

    assert exc_info.value.code == 2


@pytest.mark.asyncio
async def test_cmd_module_start_all_requires_background(monkeypatch) -> None:
    outputs: list[dict] = []
    monkeypatch.setattr("src.cli._json_out", lambda data: outputs.append(data))

    args = argparse.Namespace(action="start", target="all", background=False, mode="daemon")
    with pytest.raises(SystemExit) as exc_info:
        await cmd_module(args)

    assert exc_info.value.code == 2
    assert outputs
    assert "requires --background" in str(outputs[-1].get("error", ""))


@pytest.mark.asyncio
async def test_cmd_module_start_all_dispatches_each_target(monkeypatch) -> None:
    called: list[str] = []
    outputs: list[dict] = []

    def fake_start(target: str, args: argparse.Namespace) -> dict:
        called.append(target)
        return {"target": target, "started": True}

    monkeypatch.setattr("src.cli._start_background_module", fake_start)
    monkeypatch.setattr("src.cli._json_out", lambda data: outputs.append(data))

    args = argparse.Namespace(action="start", target="all", background=True, mode="daemon")
    await cmd_module(args)

    assert called == ["presales", "operations", "aftersales"]
    assert len(outputs) == 1
    payload = outputs[0]
    assert payload["target"] == "all"
    assert payload["action"] == "start"
    assert set(payload["modules"].keys()) == {"presales", "operations", "aftersales"}


@pytest.mark.asyncio
async def test_cmd_messages_sla_benchmark_dispatch(monkeypatch) -> None:
    outputs: list[dict] = []

    async def fake_benchmark(**kwargs):
        return {
            "action": "messages_sla_benchmark",
            "config": kwargs,
            "summary": {"samples": int(kwargs.get("count", 0))},
        }

    monkeypatch.setattr("src.cli._run_messages_sla_benchmark", fake_benchmark)
    monkeypatch.setattr("src.cli._json_out", lambda data: outputs.append(data))

    args = argparse.Namespace(
        action="sla-benchmark",
        benchmark_count=32,
        concurrency=2,
        quote_ratio=0.8,
        quote_only=False,
        seed=7,
        warmup=1,
        slowest=5,
    )
    await cmd_messages(args)

    assert len(outputs) == 1
    payload = outputs[0]
    assert payload["action"] == "messages_sla_benchmark"
    assert payload["summary"]["samples"] == 32
    assert payload["config"]["concurrency"] == 2

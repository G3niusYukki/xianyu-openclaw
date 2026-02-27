"""doctor 自检报告测试。"""

from src.core.doctor import run_doctor
from src.core.startup_checks import StartupCheckResult


def test_doctor_report_not_ready_when_critical_check_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.core.doctor.run_all_checks",
        lambda skip_browser=False: [  # noqa: ARG005
            StartupCheckResult("OpenClaw Gateway", False, "无法连接", critical=True),
        ],
    )
    monkeypatch.setattr("src.core.doctor._extra_checks", lambda skip_quote=False: [])  # noqa: ARG005

    report = run_doctor(skip_gateway=False, skip_quote=True)

    assert report["ready"] is False
    assert report["summary"]["critical_failed"] == 1
    assert any("docker compose up -d" in step for step in report["next_steps"])


def test_doctor_report_ready_with_warning_only(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.core.doctor.run_all_checks",
        lambda skip_browser=False: [  # noqa: ARG005
            StartupCheckResult("Python版本", True, "ok", critical=True),
        ],
    )
    monkeypatch.setattr(
        "src.core.doctor._extra_checks",
        lambda skip_quote=False: [  # noqa: ARG005
            {
                "name": "AI服务",
                "passed": False,
                "critical": False,
                "message": "未配置",
                "suggestion": "配置 API Key",
                "meta": {},
            }
        ],
    )

    report = run_doctor(skip_gateway=True, skip_quote=True)

    assert report["ready"] is True
    assert report["summary"]["critical_failed"] == 0
    assert report["summary"]["warning_failed"] == 1
    assert report["next_steps"] == ["配置 API Key"]


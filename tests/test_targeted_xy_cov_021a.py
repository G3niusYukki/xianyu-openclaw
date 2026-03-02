from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import src.dashboard_server as ds
from src.dashboard_server import MimicOps, ModuleConsole


def test_parse_cookie_text_devtools_domain_filter_continue_branch() -> None:
    raw = "\n".join(
        [
            "cookie2\tabc123\t.example.com",
            "_tb_token_\ttoken_xyz\t.goofish.com",
            "sgcookie\tsgv\t.goofish.com",
            "unb\t4057\t.goofish.com",
        ]
    )

    payload = MimicOps.parse_cookie_text(raw)

    assert payload["success"] is True
    assert "cookie2=abc123" not in payload["cookie"]
    assert "_tb_token_=token_xyz" in payload["cookie"]
    assert payload["cookie_items"] == 3


def test_cookie_domain_filter_stats_walks_nested_json_lists() -> None:
    text = (
        '[{"domain":".example.com"}, '
        '{"nested": [{"domain": "passport.goofish.com"}, {"domain": ".bad.example.org"}]}]'
    )

    stats = MimicOps._cookie_domain_filter_stats(text)

    assert stats["applied"] is True
    assert stats["checked"] == 3
    assert stats["rejected"] == 2
    assert any("example.com" in s for s in stats["rejected_samples"])


def test_parse_markup_rules_json_like_list_supports_fallback_courier_keys(temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))

    parsed = ops._parse_markup_rules_from_json_like(
        [
            {
                "carrier": "圆通",
                "normal_first_add": 1.1,
                "member_first_add": 0.9,
                "normal_extra_add": 0.6,
                "member_extra_add": 0.4,
            }
        ]
    )

    assert "圆通" in parsed
    assert parsed["圆通"]["normal_first_add"] == pytest.approx(1.1)


def test_parse_markup_rules_from_file_xls_returns_empty_when_no_rows(monkeypatch, temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))

    class _Frame:
        empty = True

    pandas_stub = SimpleNamespace(read_excel=lambda *_a, **_k: {"s1": _Frame()})
    monkeypatch.setitem(sys.modules, "pandas", pandas_stub)

    parsed, fmt = ops._parse_markup_rules_from_file("rules.xls", b"fake")

    assert parsed == {}
    assert fmt == "excel"


def test_risk_control_status_handles_read_error_and_recovery_signals(monkeypatch, temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))

    class _BrokenPath:
        def exists(self) -> bool:
            return True

        def read_text(self, **_kwargs):
            raise RuntimeError("boom")

        def __str__(self) -> str:
            return "broken.log"

    monkeypatch.setattr(ops, "_module_runtime_log", lambda _target: _BrokenPath())
    broken = ops._risk_control_status_from_logs()
    assert broken["level"] == "unknown"
    assert "读取失败" in broken["label"]

    runtime_log = temp_dir / "data" / "module_runtime" / "presales.log"
    runtime_log.parent.mkdir(parents=True, exist_ok=True)
    runtime_log.write_text(
        "\n".join(
            [
                "2026-01-01 10:00:00 websocket http 400 temporary",
                "2026-01-01 10:00:01 FAIL_SYS_USER_VALIDATE",
                "2026-01-01 10:00:02 Connected to Goofish WebSocket transport",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(ops, "_module_runtime_log", lambda _target: runtime_log)
    recovered = ops._risk_control_status_from_logs()
    assert recovered["level"] == "normal"
    assert recovered["label"] == "已恢复连接"
    assert recovered["last_connected_at"] == "2026-01-01 10:00:02"


def test_test_reply_includes_volume_weight_in_structured_prompt(monkeypatch, temp_dir) -> None:
    captured: dict[str, object] = {}

    class _StubService:
        def __init__(self, controller, config):
            _ = (controller, config)

        async def _generate_reply_with_quote(self, message, item_title=""):
            captured["message"] = message
            captured["item_title"] = item_title
            return "ok", {"is_quote": False}

    monkeypatch.setattr(ds, "MessagesService", _StubService)
    monkeypatch.setattr(ds, "_run_async", lambda c: __import__("asyncio").run(c))

    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))
    out = ops.test_reply(
        {
            "origin": "杭州",
            "destination": "广州",
            "weight": 2,
            "volume_weight": 3.5,
            "message": "",
        }
    )

    assert out["success"] is True
    assert "体积重3.5kg" in str(captured["message"])

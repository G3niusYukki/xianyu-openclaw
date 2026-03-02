from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace

import pytest

from src.dashboard_server import MimicOps, ModuleConsole


def test_module_console_status_passes_window_and_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    console = ModuleConsole(project_root=".")
    called: dict[str, object] = {}

    def fake_run(action: str, target: str, extra_args=None, timeout_seconds: int = 120):
        called.update(
            {
                "action": action,
                "target": target,
                "extra_args": extra_args,
                "timeout": timeout_seconds,
            }
        )
        return {"ok": True}

    monkeypatch.setattr(console, "_run_module_cli", fake_run)
    out = console.status(window_minutes=9, limit=7)

    assert out == {"ok": True}
    assert called["action"] == "status"
    assert called["target"] == "all"
    assert called["extra_args"] == ["--window-minutes", "9", "--limit", "7"]
    assert called["timeout"] == 90


def test_cookie_extract_helpers_cover_skip_and_empty_domain() -> None:
    assert MimicOps._is_allowed_cookie_domain("") is True

    raw_json = '["bad", {"name": "a"}, {"name": "cookie2", "value": "v"}]'
    pairs = MimicOps._extract_cookie_pairs_from_json(raw_json)
    assert pairs == [("cookie2", "v")]

    pairs_from_lines = MimicOps._extract_cookie_pairs_from_lines("cookie2 value_only")
    assert pairs_from_lines == [("cookie2", "value_only")]


def test_parse_markup_rules_from_file_xls_rows_and_route_infer(monkeypatch: pytest.MonkeyPatch, temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))

    class _Values:
        def tolist(self):
            return [["圆通", 1, 2, 3, 4]]

    class _Frame:
        empty = False

        def fillna(self, _x):
            return SimpleNamespace(values=_Values())

    class _FakePd:
        @staticmethod
        def read_excel(*_a, **_k):
            return {"s1": _Frame()}

    import sys

    monkeypatch.setitem(sys.modules, "pandas", _FakePd)
    monkeypatch.setattr(ops, "_parse_markup_rules_from_rows", lambda rows: {"圆通": {"normal_first_add": 1.0}} if rows else {})
    parsed, fmt = ops._parse_markup_rules_from_file("rules.xls", b"xls-bytes")
    assert fmt == "excel"
    assert "圆通" in parsed

    monkeypatch.setattr(ops, "_parse_markup_rules_from_rows", lambda _rows: {})
    monkeypatch.setattr(ops, "_infer_markup_rules_from_route_table", lambda _f, _d: {"default": {"normal_first_add": 0.5}})
    inferred, fmt2 = ops._parse_markup_rules_from_file("rules.xls", b"xls-bytes")
    assert fmt2 == "route_cost_infer"
    assert inferred["default"]["normal_first_add"] == 0.5


def test_parse_markup_rules_from_file_csv_json_text_branch(temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))
    payload = b'{"default": {"normal_first_add": 0.66, "member_first_add": 0.2, "normal_extra_add": 0.3, "member_extra_add": 0.1}}'

    parsed, fmt = ops._parse_markup_rules_from_file("rules.csv", payload)

    assert fmt == "json_text"
    assert parsed["default"]["normal_first_add"] == 0.66


def test_import_markup_files_covers_skip_exception_and_empty_log_branch(monkeypatch: pytest.MonkeyPatch, temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        zf.writestr("__MACOSX/._x", b"x")
        zf.writestr("a.bin", b"x")
        zf.writestr("ok.csv", b"x")

    def boom(_filename: str, _data: bytes):
        raise RuntimeError("parse exploded")

    monkeypatch.setattr(ops, "_parse_markup_rules_from_file", boom)
    out = ops.import_markup_files([("bundle.zip", zip_buf.getvalue())])
    assert out["success"] is False
    assert any("bundle.zip:__MACOSX/._x" in s for s in out["skipped_files"])
    assert any("bundle.zip:a.bin" in s for s in out["skipped_files"])
    assert any("parse exploded" in d for d in out["details"])

    log_fp = ops._module_runtime_log("presales")
    log_fp.parent.mkdir(parents=True, exist_ok=True)
    log_fp.write_text("\n\n", encoding="utf-8")
    risk = ops._risk_control_status_from_logs("presales")
    assert risk["level"] == "unknown"
    assert risk["label"] == "未检测（空日志）"

    conv = ops._resolve_log_file("conversations/chat.log")
    assert str(conv).endswith("logs/conversations/chat.log")
    fallback = ops._resolve_log_file("not_exist.log")
    assert str(fallback).endswith("data/module_runtime/not_exist.log")

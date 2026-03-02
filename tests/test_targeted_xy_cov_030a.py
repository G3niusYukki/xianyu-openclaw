from __future__ import annotations

import io
import zipfile
from pathlib import Path
from unittest.mock import Mock

import pytest

import src.dashboard_server as ds
from src.dashboard_server import DashboardHandler, MimicOps, ModuleConsole


def _ops(temp_dir):
    return MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))


def _handler(path: str = "/") -> DashboardHandler:
    h = DashboardHandler.__new__(DashboardHandler)
    h.path = path
    h.headers = {}
    h.rfile = io.BytesIO()
    h.wfile = io.BytesIO()
    h.repo = Mock()
    h.module_console = Mock()
    h.mimic_ops = Mock()
    h.send_response = Mock()
    h.send_header = Mock()
    h.end_headers = Mock()
    h._send_json = Mock()
    h._send_html = Mock()
    h._send_bytes = Mock()
    return h


def test_cookie_diagnose_rejected_domain_action_and_empty_domain_stat(temp_dir) -> None:
    ops = _ops(temp_dir)
    stats = ops._cookie_domain_filter_stats("\t\t\t")
    assert stats["checked"] == 0
    assert stats["rejected"] == 0

    monkey = pytest.MonkeyPatch()
    monkey.setattr(ops, "_cookie_domain_filter_stats", lambda _t: {"rejected": 1, "applied": True})
    text = "_tb_token_=a; cookie2=b; sgcookie=c; unb=d; _m_h5_tk=t; _m_h5_tk_enc=e"
    out = ops.diagnose_cookie(text)
    assert out["success"] is True
    assert any("自动过滤" in a for a in out["actions"])
    monkey.undo()


def test_import_cookie_zip_read_exception_and_empty_parsed_cookie(monkeypatch: pytest.MonkeyPatch, temp_dir) -> None:
    ops = _ops(temp_dir)

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as zf:
        zf.writestr("cookies.txt", b"_tb_token_=a")

    class BoomZip(zipfile.ZipFile):
        def read(self, name, pwd=None):  # type: ignore[override]
            raise RuntimeError("zip read boom")

    monkeypatch.setattr(ds.zipfile, "ZipFile", BoomZip)
    bad = ops.import_cookie_plugin_files([("boom.zip", zbuf.getvalue())])
    assert bad["success"] is False
    assert any("zip read boom" in d for d in bad["details"])

    monkeypatch.setattr(ds.zipfile, "ZipFile", zipfile.ZipFile)
    monkeypatch.setattr(ops, "parse_cookie_text", lambda _t: {"success": True, "cookie": "", "cookie_items": 1, "length": 0})
    monkeypatch.setattr(ops, "_cookie_hint_hit_keys", lambda _t: ["_tb_token_"])
    empty_cookie = ops.import_cookie_plugin_files([("cookies.txt", b"_tb_token_=a")])
    assert empty_cookie["success"] is False
    assert empty_cookie["error"] == "Parsed cookie is empty."


def test_route_import_and_route_stats_edge_branches(monkeypatch: pytest.MonkeyPatch, temp_dir) -> None:
    ops = _ops(temp_dir)

    monkeypatch.setattr(ops, "_safe_filename", lambda _n: "bad.txt")
    with pytest.raises(ValueError, match="Unsupported file type"):
        ops._save_route_content(ops._quote_dir(), "bad.txt", b"x")
    monkeypatch.setattr(ops, "_safe_filename", lambda n: MimicOps._safe_filename(n))

    qd = ops._quote_dir()
    target = qd / "a.csv"
    target.write_bytes(b"1")
    saved_name = ops._save_route_content(qd, "a.csv", b"2")
    assert saved_name != "a.csv"

    class Repo:
        def __init__(self, table_dir):
            self._records = [type("R", (), {"courier": ""})(), type("R", (), {"courier": "YTO"})()]

        def get_stats(self, max_files=1):
            return {}

    monkeypatch.setattr(ds, "CostTableRepository", Repo)
    rs = ops.route_stats()
    assert rs["success"] is True
    assert rs["stats"]["couriers"] == 1
    assert rs["stats"]["routes"] >= 2


def test_markup_mapping_rows_and_file_parser_edges(monkeypatch: pytest.MonkeyPatch, temp_dir) -> None:
    ops = _ops(temp_dir)

    parsed = ops._parse_markup_rules_from_mapping({"首重加价": ["a"], "YTO": [1, 2, 3, 4]})
    assert "YTO" in parsed
    assert "首重加价" not in parsed

    rows = [[], ["???", "x"], ["YTO", "n/a", "n/a", "n/a", "n/a"]]
    row_parsed = ops._parse_markup_rules_from_rows(rows)
    assert row_parsed == {}

    list_payload = [{"name": "   "}, {"carrier": "申通", "normal_first_add": 1, "member_first_add": 2, "normal_extra_add": 3, "member_extra_add": 4}]
    json_like = ops._parse_markup_rules_from_json_like(list_payload)
    assert "申通" in json_like
    assert ops._parse_markup_rules_from_json_like("x") == {}

    monkeypatch.setattr(ops, "_parse_markup_rules_from_xlsx_bytes", lambda _b: {})
    monkeypatch.setattr(ops, "_infer_markup_rules_from_route_table", lambda _n, _b: {"YTO": {"normal_first_add": 1, "member_first_add": 1, "normal_extra_add": 1, "member_extra_add": 1}})
    inferred, fmt = ops._parse_markup_rules_from_file("x.xlsx", b"bin")
    assert fmt == "route_cost_infer"
    assert "YTO" in inferred


def test_markup_import_save_rules_and_logs_and_stream_finish(monkeypatch: pytest.MonkeyPatch, temp_dir) -> None:
    ops = _ops(temp_dir)

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as zf:
        zf.writestr("d/", b"")
        zf.writestr(".__ignored.csv", b"x")
        zf.writestr("a.json", b'{"YTO": {"normal_first_add": 1, "member_first_add": 2, "normal_extra_add": 3, "member_extra_add": 4}}')

    out = ops.import_markup_files([("rules.zip", zbuf.getvalue())])
    assert out["success"] is True
    assert any("rules.zip:.__ignored.csv" in x for x in out["skipped_files"])

    monkeypatch.setattr(ops, "_normalize_markup_rules", lambda _r: {})
    bad_save = ops.save_markup_rules({"x": 1})
    assert bad_save == {"success": False, "error": "No valid markup rules"}

    runtime_dir = Path(temp_dir) / "data" / "module_runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "presales.log").mkdir(exist_ok=True)

    logs_dir = Path(temp_dir) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "app.log").write_text("ok", encoding="utf-8")
    conv_dir = logs_dir / "conversations"
    conv_dir.mkdir(parents=True, exist_ok=True)
    (conv_dir / "x.log").write_text("ok", encoding="utf-8")

    listed = ops.list_log_files()
    assert listed["success"] is True
    names = [x["name"] for x in listed["files"]]
    assert "app/app.log" in names
    assert "conversations/x.log" in names

    resolved = ops._resolve_log_file("app.log")
    assert resolved.name == "app.log"
    assert resolved.exists()

    h = _handler("/api/logs/realtime/stream?file=presales&tail=1")
    h._send_json = DashboardHandler._send_json.__get__(h, DashboardHandler)
    h.mimic_ops.read_log_content.return_value = {"success": True, "lines": ["L1"]}
    monkeypatch.setattr(ds.time, "sleep", lambda _s: None)
    h.do_GET()
    payload = h.wfile.getvalue().decode("utf-8")
    assert "data:" in payload

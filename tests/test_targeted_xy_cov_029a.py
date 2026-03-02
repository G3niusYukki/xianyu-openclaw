from __future__ import annotations

import io
import zipfile

import pytest

from src.dashboard_server import MimicOps, ModuleConsole


def _ops(temp_dir):
    return MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))


def test_recovery_advice_default_and_update_cookie_empty_and_recover_failed(monkeypatch: pytest.MonkeyPatch, temp_dir) -> None:
    ops = _ops(temp_dir)

    assert ops._recovery_advice("something-unknown") == "监控中，请刷新状态查看最新结果。"

    monkeypatch.setattr(ops, "parse_cookie_text", lambda _t: {"success": True, "cookie": ""})
    out_empty = ops.update_cookie("x")
    assert out_empty == {"success": False, "error": "Cookie string cannot be empty"}

    monkeypatch.setattr(
        ops,
        "parse_cookie_text",
        lambda _t: {
            "success": True,
            "cookie": "_tb_token_=a; cookie2=b; sgcookie=c; unb=d",
            "cookie_items": 4,
            "detected_format": "header",
            "missing_required": [],
        },
    )
    monkeypatch.setattr(ops, "diagnose_cookie", lambda _t: {"grade": "可用", "actions": []})
    monkeypatch.setattr(ops, "_trigger_presales_recover_after_cookie_update", lambda _t: {"triggered": False})

    out_fail = ops.update_cookie("cookie: _tb_token_=a", auto_recover=True)
    assert out_fail["success"] is True
    assert out_fail["message"] == "Cookie updated, but presales recovery failed"
    assert out_fail["auto_recover"]["triggered"] is False


def test_cookie_domain_filter_stats_covers_blank_domain_tab3_and_json_queue(temp_dir) -> None:
    ops = _ops(temp_dir)

    tab_stats = ops._cookie_domain_filter_stats("\n".join(["\t\t", "name\tvalue\tbad.example.com"]))
    assert tab_stats["applied"] is True
    assert tab_stats["checked"] == 1
    assert tab_stats["rejected"] == 1
    assert "bad.example.com" in tab_stats["rejected_samples"]

    json_stats = ops._cookie_domain_filter_stats(
        '{"cookies": [{"domain": ".goofish.com"}, {"domain": "bad2.example.com"}], "extra": {"domain": "passport.goofish.com"}}'
    )
    assert json_stats["checked"] == 3
    assert json_stats["rejected"] == 1
    assert "bad2.example.com" in json_stats["rejected_samples"]


def test_diagnose_cookie_empty_and_parse_failure(temp_dir, monkeypatch: pytest.MonkeyPatch) -> None:
    ops = _ops(temp_dir)

    empty = ops.diagnose_cookie("")
    assert empty["success"] is False
    assert empty["grade"] == "不可用"
    assert empty["error"] == "Cookie text is empty"

    monkeypatch.setattr(ops, "parse_cookie_text", lambda _t: {"success": False, "error": "bad format"})
    failed = ops.diagnose_cookie("not-cookie")
    assert failed["success"] is False
    assert failed["grade"] == "不可用"
    assert failed["error"] == "bad format"
    assert failed["domain_filter"]["applied"] is True
    assert any("headers/json/cookies.txt" in item for item in failed["actions"])


def test_cookie_plugin_bundle_detection_negative_and_marker_positive() -> None:
    assert MimicOps._looks_like_cookie_plugin_bundle([]) is False
    assert (
        MimicOps._looks_like_cookie_plugin_bundle(
            [
                "manifest.json",
                "src/get_all_cookies.mjs",
                "assets/icon.png",
            ]
        )
        is True
    )


def test_import_cookie_plugin_files_no_files_and_skip_no_hint_keys(temp_dir) -> None:
    ops = _ops(temp_dir)

    no_files = ops.import_cookie_plugin_files([])
    assert no_files == {"success": False, "error": "No files uploaded"}

    bad = ops.import_cookie_plugin_files([("cookies.txt", b"a=b; c=d")])
    assert bad["success"] is False
    assert bad["error"] == "No valid cookie content found in uploaded files."
    assert "cookies.txt" in bad["skipped_files"]
    assert any("parsed but missing known keys" in x for x in bad["details"])


def test_import_cookie_plugin_files_zip_edge_cases_and_non_import_file(monkeypatch: pytest.MonkeyPatch, temp_dir) -> None:
    ops = _ops(temp_dir)

    parse_calls: list[str] = []

    def fake_parse(text: str):
        parse_calls.append(text)
        return {
            "success": True,
            "cookie": "_tb_token_=a; cookie2=b; sgcookie=c; unb=d",
            "cookie_items": 4,
            "length": 50,
            "missing_required": [],
        }

    monkeypatch.setattr(ops, "parse_cookie_text", fake_parse)
    monkeypatch.setattr(ops, "diagnose_cookie", lambda _t: {"grade": "可用", "actions": []})

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as zf:
        zf.writestr("dir/", b"")
        zf.writestr("__MACOSX/._cookies.txt", b"x")
        zf.writestr("cookies.txt", b"")  # empty file branch
        zf.writestr("good.cookies", b"_tb_token_=a")

    out = ops.import_cookie_plugin_files([("bundle.zip", zbuf.getvalue()), ("image.png", b"png")])

    assert out["success"] is True
    assert any("bundle.zip:__MACOSX/._cookies.txt" in x for x in out["skipped_files"])
    assert any("bundle.zip:cookies.txt -> empty file" in x for x in out["details"])
    assert "image.png" in out["skipped_files"]
    assert parse_calls, "zip内有效cookie文件应被解析"

    bad_zip = ops.import_cookie_plugin_files([("broken.zip", b"not-zip-content")])
    assert bad_zip["success"] is False
    assert "broken.zip" in bad_zip["skipped_files"]
    assert any("invalid zip file" in x for x in bad_zip["details"])

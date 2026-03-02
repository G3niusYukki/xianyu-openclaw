import io
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import src.dashboard_server as ds
from src.dashboard_server import DashboardHandler, ModuleConsole, _extract_json_payload


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
    return h


def test_extract_json_payload_branches() -> None:
    assert _extract_json_payload("") is None
    assert _extract_json_payload('{"a":1}') == {"a": 1}
    assert _extract_json_payload("prefix {\"b\":2} suffix") == {"b": 2}
    assert _extract_json_payload("xx [1,2,3] yy") == [1, 2, 3]
    assert _extract_json_payload("not-json") is None


def test_module_console_run_cli_all_paths(monkeypatch: pytest.MonkeyPatch, temp_dir) -> None:
    c = ModuleConsole(project_root=temp_dir)

    def boom(*_args, **_kwargs):
        raise RuntimeError("exec-fail")

    monkeypatch.setattr(ds.subprocess, "run", boom)
    err = c._run_module_cli("status", "all")
    assert "execution failed" in err["error"].lower()

    proc_fail = SimpleNamespace(returncode=2, stdout='{"k":1}', stderr="")
    monkeypatch.setattr(ds.subprocess, "run", lambda *a, **k: proc_fail)
    out_fail = c._run_module_cli("status", "all")
    assert out_fail["k"] == 1
    assert out_fail["_cli_code"] == 2

    proc_fail2 = SimpleNamespace(returncode=3, stdout="bad", stderr="oops")
    monkeypatch.setattr(ds.subprocess, "run", lambda *a, **k: proc_fail2)
    out_fail2 = c._run_module_cli("status", "all")
    assert out_fail2["_cli_stderr"] == "oops"

    proc_ok_dict = SimpleNamespace(returncode=0, stdout='{"ok":true}', stderr="")
    monkeypatch.setattr(ds.subprocess, "run", lambda *a, **k: proc_ok_dict)
    assert c._run_module_cli("status", "all")["ok"] is True

    proc_ok_list = SimpleNamespace(returncode=0, stdout='[{"a":1}]', stderr="")
    monkeypatch.setattr(ds.subprocess, "run", lambda *a, **k: proc_ok_list)
    assert c._run_module_cli("status", "all")["items"][0]["a"] == 1

    proc_ok_text = SimpleNamespace(returncode=0, stdout="plain", stderr="")
    monkeypatch.setattr(ds.subprocess, "run", lambda *a, **k: proc_ok_text)
    assert c._run_module_cli("status", "all")["stdout"] == "plain"


def test_module_console_logs_check_control_paths(monkeypatch: pytest.MonkeyPatch, temp_dir) -> None:
    c = ModuleConsole(project_root=temp_dir)
    called = []

    def fake_run(action, target, extra_args=None, timeout_seconds=120):
        called.append((action, target, extra_args, timeout_seconds))
        return {"ok": True}

    monkeypatch.setattr(c, "_run_module_cli", fake_run)
    c.logs("BAD", tail_lines=999)
    c.check(skip_gateway=True)
    c.control("start", "all")
    c.control("restart", "presales")
    c.control("recover", "operations")
    c.control("stop", "aftersales")

    bad1 = c.control("x", "all")
    bad2 = c.control("start", "x")
    assert "Unsupported" in bad1["error"]
    assert "Unsupported" in bad2["error"]

    assert called[0][1] == "all"
    assert "--tail-lines" in called[0][2]
    assert "--skip-gateway" in called[1][2]
    assert "--background" in called[2][2]


def test_handler_send_helpers_and_multipart_paths() -> None:
    h = _handler()
    h._send_json = DashboardHandler._send_json.__get__(h, DashboardHandler)
    h._send_html = DashboardHandler._send_html.__get__(h, DashboardHandler)
    h._send_bytes = DashboardHandler._send_bytes.__get__(h, DashboardHandler)

    h._send_json({"a": 1})
    h._send_html("<b>x</b>")
    h._send_bytes(b"abc", "application/octet-stream", download_name="a.bin")
    body = h.wfile.getvalue().decode("utf-8", errors="ignore")
    assert '"a": 1' in body
    assert "<b>x</b>" in body

    h2 = _handler()
    h2.headers = {"Content-Type": "multipart/form-data", "Content-Length": "x"}
    assert h2._read_multipart_files() == []

    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    payload = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="a.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        "hello\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    h2.headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(payload)),
    }
    h2.rfile = io.BytesIO(payload)
    files = h2._read_multipart_files()
    assert len(files) == 1
    assert files[0][0] == "a.txt"
    assert files[0][1] == b"hello"


def test_handler_missing_get_routes_and_download_success(monkeypatch: pytest.MonkeyPatch) -> None:
    h = _handler("/test")
    h._send_html = Mock()
    h.do_GET()
    assert h._send_html.called

    h2 = _handler("/logs")
    h2._send_html = Mock()
    h2.do_GET()
    assert h2._send_html.called

    h3 = _handler("/logs/realtime")
    h3._send_html = Mock()
    h3.do_GET()
    assert h3._send_html.called

    h4 = _handler("/api/download-cookie-plugin")
    h4._send_bytes = Mock()
    h4.mimic_ops.export_cookie_plugin_bundle.return_value = (b"zip", "plugin.zip")
    h4.do_GET()
    assert h4._send_bytes.called

    h5 = _handler("/api/logs/realtime/stream?file=x&tail=2")
    h5.mimic_ops.read_log_content.return_value = {"success": True, "lines": ["L1"]}

    def boom(_sec: int):
        raise ConnectionResetError

    monkeypatch.setattr(ds.time, "sleep", boom)
    h5.do_GET()
    assert h5.send_response.called


def test_handler_post_upload_error_branches_and_log_message() -> None:
    h = _handler("/api/import-cookie-plugin")
    h._send_json = Mock()
    h._read_multipart_files = Mock(side_effect=RuntimeError("parse boom"))
    h.do_POST()
    assert h._send_json.call_args.kwargs["status"] == 400

    h2 = _handler("/api/import-cookie-plugin")
    h2._send_json = Mock()
    h2._read_multipart_files = Mock(return_value=[])
    h2.mimic_ops.import_cookie_plugin_files.side_effect = RuntimeError("proc boom")
    h2.do_POST()
    assert h2._send_json.call_args.kwargs["status"] == 400

    h3 = _handler("/api/import-routes")
    h3._send_json = Mock()
    h3._read_multipart_files = Mock(side_effect=RuntimeError("parse boom"))
    h3.do_POST()
    assert h3._send_json.call_args.kwargs["status"] == 400

    h4 = _handler("/api/import-markup")
    h4._send_json = Mock()
    h4._read_multipart_files = Mock(return_value=[])
    h4.mimic_ops.import_markup_files.side_effect = RuntimeError("proc boom")
    h4.do_POST()
    assert h4._send_json.call_args.kwargs["status"] == 400

    assert h4.log_message("%s", "x") is None


def test_run_server_startup_lines_and_main(monkeypatch: pytest.MonkeyPatch, temp_dir) -> None:
    started = {"serve": 0}

    class FakeServer:
        def __init__(self, addr, handler):
            assert addr == ("127.0.0.1", 18888)
            assert handler is ds.DashboardHandler

        def serve_forever(self):
            started["serve"] += 1

    monkeypatch.setattr(ds, "ThreadingHTTPServer", FakeServer)
    monkeypatch.setattr(ds, "get_config", lambda: SimpleNamespace(database={"path": str(temp_dir / "x.db")}))
    ds.run_server(host="127.0.0.1", port=18888, db_path=None)
    assert started["serve"] == 1

    called = {}
    monkeypatch.setattr(ds, "parse_args", lambda: SimpleNamespace(host="h", port=9, db_path="d"))
    monkeypatch.setattr(ds, "run_server", lambda host, port, db_path: called.update({"host": host, "port": port, "db": db_path}))
    ds.main()
    assert called == {"host": "h", "port": 9, "db": "d"}


def test_repo_and_cookie_low_level_branches(monkeypatch: pytest.MonkeyPatch, temp_dir) -> None:
    # repo methods: get_recent_operations/get_top_products + invalid metric fallback branch
    from tests.test_dashboard_server import _init_db

    db_path = temp_dir / "dash.db"
    _init_db(str(db_path))
    repo = ds.DashboardRepository(str(db_path))
    assert repo.get_recent_operations(limit=5)
    assert repo.get_top_products(limit=5)
    assert len(repo.get_trend("unknown", days=2)) == 2

    ops = ds.MimicOps(project_root=temp_dir, module_console=ds.ModuleConsole(project_root=temp_dir))

    # _get_env_value fallback to os env
    monkeypatch.setenv("XIANYU_COOKIE_1", "cookie2=from_env")
    assert "from_env" in ops._get_env_value("XIANYU_COOKIE_1")

    # _set_env_value update existing line
    ops._set_env_value("XIANYU_COOKIE_1", "cookie2=v1")
    ops._set_env_value("XIANYU_COOKIE_1", "cookie2=v2")
    assert "cookie2=v2" in ops.env_path.read_text(encoding="utf-8")

    # cookie pair cleaners / validators
    txt, cnt = ops._cookie_pairs_to_text([("", "x"), ("bad key", "y"), ("cookie2", "a"), ("cookie2", "b")])
    assert cnt == 1 and txt == "cookie2=a"

    assert ops._extract_cookie_pairs_from_json("") == []
    assert ops._extract_cookie_pairs_from_json('{"name":"cookie2","value":"v"}')
    assert ops._extract_cookie_pairs_from_json('{"cookies":[{"name":"_tb_token_","value":"t"}],"items":[{"key":"unb","value":"1"}],"x":1}')

    assert ops._is_allowed_cookie_domain(".example.com") is False
    assert ops._extract_cookie_pairs_from_header("") == []
    assert ops._extract_cookie_pairs_from_lines("cookie2\tv\t.example.com") == []

    # parse empty/update empty branch
    assert ops.parse_cookie_text("")["success"] is False
    assert ops.update_cookie("")["success"] is False

    # recovery advice branches
    assert "重新登录" in ops._recovery_advice("waiting_cookie_update", "FAIL_SYS_USER_VALIDATE")
    assert "更新 Cookie" in ops._recovery_advice("waiting_cookie_update", "X")
    assert "一键恢复" in ops._recovery_advice("token_error", "WS_HTTP_400")
    assert "鉴权错误" in ops._recovery_advice("token_error", "X")
    assert "服务未运行" in ops._recovery_advice("inactive", None)
    assert "链路可用" in ops._recovery_advice("healthy", None)

    # empty cookie auto recover path
    assert ops._trigger_presales_recover_after_cookie_update("")["triggered"] is False


def test_markup_and_file_import_branches(monkeypatch: pytest.MonkeyPatch, temp_dir) -> None:
    ops = ds.MimicOps(project_root=temp_dir, module_console=ds.ModuleConsole(project_root=temp_dir))

    # route/table helpers
    assert ops._safe_filename("a.bad") == "a.xlsx"
    assert ops._repair_zip_name("") == ""

    qd = ops._quote_dir()
    (qd / "dup.csv").write_text("x", encoding="utf-8")
    saved = ops._save_route_content(qd, "dup.csv", b"y")
    assert saved.startswith("dup_") and saved.endswith(".csv")

    # import route no files
    assert ops.import_route_files([])["success"] is False

    # export routes / reset db
    data, name = ops.export_routes_zip()
    assert name.endswith(".zip") and isinstance(data, (bytes, bytearray))

    (temp_dir / "data").mkdir(parents=True, exist_ok=True)
    (temp_dir / "data" / "workflow.db").write_text("x", encoding="utf-8")
    (temp_dir / "data" / "message_workflow_state.json").write_text("{}", encoding="utf-8")
    reset = ops.reset_database("all")
    assert reset["success"] is True and "routes" in reset["results"] and "chat" in reset["results"]

    # template branches
    assert ops.get_template(default=True)["success"] is True
    ops.save_template("", "")
    assert ops.get_template(default=False)["success"] is True

    # decode/float/token/header/rows branches
    assert isinstance(ops._decode_text_bytes(b"\xff\xfe"), str)
    assert ops._markup_float(None) is None
    assert ops._markup_float("abc") is None
    assert ops._clean_markup_token("") == ""
    assert ops._match_markup_header("", "courier") is False
    assert ops._split_text_rows("plain text without sep") == []
    assert ops._split_text_rows("|a|b|\n|1|2|")
    assert ops._parse_markup_rules_from_rows([]) == {}
    assert ops._parse_markup_rules_from_mapping("bad") == {}
    assert ops._parse_markup_rules_from_text("圆通\n0.6 0.3\n0.4 0.2")
    assert ops._parse_markup_rules_from_json_like(None) == {}

    # coerce branches: list too short / numeric value
    assert ops._coerce_markup_row([1, 2, 3]) is None
    assert ops._coerce_markup_row("0.9")["normal_first_add"] == 0.9

    # xlsx parser via monkeypatch repo iterator
    class FakeRepo:
        def __init__(self, table_dir):
            self.table_dir = table_dir

        def _iter_xlsx_rows(self, _p):
            return {"s1": [["快递公司", "首重溢价(普通)", "首重溢价(会员)", "续重溢价(普通)", "续重溢价(会员)"], ["圆通", 0.1, 0.2, 0.3, 0.4]]}

        def get_stats(self, max_files=1):
            _ = max_files
            self._records = []

    monkeypatch.setattr(ds, "CostTableRepository", FakeRepo)
    assert isinstance(ops._parse_markup_rules_from_xlsx_bytes(b"dummy"), dict)
    assert ops._infer_markup_rules_from_route_table("x.txt", b"d") == {}

    # _parse_markup_rules_from_file branches + unsupported
    monkeypatch.setattr(ops, "_extract_text_from_image", lambda _b: "圆通 0.1 0.2 0.3 0.4")
    parsed, fmt = ops._parse_markup_rules_from_file("a.png", b"img")
    assert fmt == "image_ocr" and "圆通" in parsed

    monkeypatch.setattr(ops, "_parse_markup_rules_from_xlsx_bytes", lambda _b: {})
    monkeypatch.setattr(ops, "_infer_markup_rules_from_route_table", lambda _n, _b: {"圆通": dict(ds.DEFAULT_MARKUP_RULES["default"])})
    parsed2, fmt2 = ops._parse_markup_rules_from_file("a.xlsx", b"x")
    assert fmt2 == "route_cost_infer" and "圆通" in parsed2

    parsed3, fmt3 = ops._parse_markup_rules_from_file("a.json", "[{\"name\":\"圆通\",\"normal_first_add\":1,\"member_first_add\":1,\"normal_extra_add\":1,\"member_extra_add\":1}]".encode("utf-8"))
    assert fmt3 == "json"

    with pytest.raises(ValueError):
        ops._parse_markup_rules_from_file("a.bin", b"x")

    # import markup empty/failed save branches
    assert ops.import_markup_files([])["success"] is False
    monkeypatch.setattr(ops, "save_markup_rules", lambda rules: {"success": False, "error": "x"})
    fail = ops.import_markup_files([("a.csv", b"invalid")])
    assert fail["success"] is False

    # normalization + save with reload exception path
    assert ops._to_non_negative_float(-1) == 0.0
    norm = ops._normalize_markup_rules({"": {}, "A": {"normal_first_add": "2"}})
    assert "default" in norm and "A" in norm

    monkeypatch.setattr(ds, "get_config", lambda: SimpleNamespace(reload=lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom"))))
    ops2 = ds.MimicOps(project_root=temp_dir, module_console=ds.ModuleConsole(project_root=temp_dir))
    ok = ops2.save_markup_rules({"A": {"normal_first_add": 1, "member_first_add": 1, "normal_extra_add": 1, "member_extra_add": 1}})
    assert ok["success"] is True


def test_service_status_and_auto_fix_extra_branches(temp_dir) -> None:
    class Console:
        def status(self, window_minutes=60, limit=20):
            _ = (window_minutes, limit)
            return {"alive_count": 1, "total_modules": 3, "modules": {"presales": {"process": {"alive": True}, "sla": {}, "workflow": {}}}}

        def control(self, action: str, target: str):
            return {"ok": True, "action": action, "target": target}

        def check(self, skip_gateway=False):
            _ = skip_gateway
            return {"ready": True}

    ops = ds.MimicOps(project_root=temp_dir, module_console=Console())
    # make risk text map to specific token errors
    ops._risk_control_status_from_logs = lambda target="presales", tail_lines=300: {"level": "warning", "signals": ["websocket http 400 rgv587 token api failed"], "last_event": "x"}  # type: ignore[assignment]
    ops.route_stats = lambda: {"stats": {"courier_details": {}}}  # type: ignore[assignment]
    ops.get_cookie = lambda: {"success": True, "cookie": "unb=1001; cookie2=v; _tb_token_=t; sgcookie=s; _m_h5_tk=a; _m_h5_tk_enc=b", "length": 10}  # type: ignore[assignment]

    s = ops.service_status()
    assert s["token_error"] in {"RGV587_SERVER_BUSY", "TOKEN_API_FAILED", "WS_HTTP_400"}

    assert ops.service_recover("bad")["success"] is False

    ops.service_status = lambda: {"service_status": "suspended", "cookie_update_required": False, "xianyu_connected": False}  # type: ignore[assignment]
    auto = ops.service_auto_fix()
    assert "resume_service" in auto["actions"]

"""dashboard_server 测试。"""

import io
import json
import sqlite3
import zipfile

from src.dashboard_server import DASHBOARD_HTML, MIMIC_COOKIE_HTML, DashboardRepository, MimicOps, ModuleConsole, _safe_int


def _init_db(path: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE operation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_type TEXT,
                product_id TEXT,
                account_id TEXT,
                details TEXT,
                status TEXT,
                error_message TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE product_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT,
                product_title TEXT,
                views INTEGER DEFAULT 0,
                wants INTEGER DEFAULT 0,
                inquiries INTEGER DEFAULT 0,
                sales INTEGER DEFAULT 0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT,
                title TEXT,
                price REAL,
                cost_price REAL,
                status TEXT,
                category TEXT,
                account_id TEXT,
                product_url TEXT,
                views INTEGER DEFAULT 0,
                wants INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                sold_at DATETIME
            )
            """
        )

        conn.execute("INSERT INTO operation_logs (operation_type, status) VALUES ('PUBLISH','success')")
        conn.execute("INSERT INTO products (product_id, title, status) VALUES ('p1','商品A','active')")
        conn.execute("INSERT INTO product_metrics (product_id, views, wants, sales) VALUES ('p1', 100, 8, 1)")
        conn.commit()


def test_safe_int_clamps() -> None:
    assert _safe_int("200", default=10, min_value=1, max_value=120) == 120
    assert _safe_int("0", default=10, min_value=1, max_value=120) == 1
    assert _safe_int("abc", default=10, min_value=1, max_value=120) == 10


def test_dashboard_repository_summary(temp_dir) -> None:
    db_path = temp_dir / "dash.db"
    _init_db(str(db_path))

    repo = DashboardRepository(str(db_path))
    summary = repo.get_summary()

    assert summary["total_operations"] == 1
    assert summary["active_products"] == 1
    assert summary["total_views"] == 100

    trend = repo.get_trend("views", days=3)
    assert len(trend) == 3


def test_cookie_page_js_string_escape_regression() -> None:
    # 回归保护：防止在三引号模板里把 \n 直接变成 JS 字符串换行导致脚本解析失败。
    assert 'let text = "路线统计\n";' not in MIMIC_COOKIE_HTML
    assert 'let text = "导入成功\n";' not in MIMIC_COOKIE_HTML
    assert 'let text = "路线统计\\n";' in MIMIC_COOKIE_HTML
    assert 'let text = "导入成功\\n";' in MIMIC_COOKIE_HTML


def test_cookie_page_contains_detailed_guide() -> None:
    assert "Cookie 详细获取步骤" in MIMIC_COOKIE_HTML
    assert "0基础 Cookie 复制方式" in MIMIC_COOKIE_HTML
    assert "_tb_token_" in MIMIC_COOKIE_HTML
    assert "更新后如何确认生效" in MIMIC_COOKIE_HTML
    assert "Get-cookies.txt-LOCALLY" in MIMIC_COOKIE_HTML
    assert "插件一键导入并更新" in MIMIC_COOKIE_HTML
    assert "下载内置插件包" in MIMIC_COOKIE_HTML
    assert "/api/download-cookie-plugin" in MIMIC_COOKIE_HTML


def test_import_routes_supports_zip_archive(temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("成本表_1.csv", "origin,destination,cost\n安徽,广州,8\n")
        zf.writestr("nested/成本表_2.xlsx", b"fake-xlsx-bytes")
        zf.writestr("__MACOSX/nested/._成本表_2.xlsx", b"macos-meta")
        zf.writestr("readme.txt", "unsupported")

    payload = ops.import_route_files([("routes_bundle.zip", zip_buf.getvalue())])

    assert payload["success"] is True
    assert len(payload["saved_files"]) == 2
    assert any(name.endswith(".csv") for name in payload["saved_files"])
    assert any(name.endswith(".xlsx") for name in payload["saved_files"])
    assert "readme.txt" in payload["skipped_files"]
    assert "__MACOSX/nested/._成本表_2.xlsx" in payload["skipped_files"]


def test_import_routes_rejects_unsupported_files(temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))

    payload = ops.import_route_files([("notes.txt", b"abc"), ("bad.zip", b"not-a-zip")])

    assert payload["success"] is False
    assert "No supported route files found" in payload["error"]
    assert "notes.txt" in payload["skipped_files"]
    assert "bad.zip" in payload["skipped_files"]
    assert any("invalid zip file" in item for item in payload.get("details", []))


def test_safe_filename_keeps_xlsx_suffix_for_garbled_names() -> None:
    out = MimicOps._safe_filename("σ£åΘÇÜ.xlsx")
    assert out.endswith(".xlsx")
    assert out != "xlsx"


def test_route_stats_tolerates_bad_xlsx_files(temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))
    quote_dir = ops._quote_dir()

    (quote_dir / "bad.xlsx").write_bytes(b"not-a-real-xlsx")
    (quote_dir / "ok.csv").write_text(
        "快递公司,始发地,目的地,首重,续重,抛比\n圆通快递,安徽,广州,3.2,1.6,8000\n",
        encoding="utf-8",
    )

    payload = ops.route_stats()
    stats = payload["stats"]
    assert payload["success"] is True
    assert stats["tables"] >= 2
    assert stats["routes"] >= 1
    assert stats["couriers"] >= 1
    assert "bad.xlsx" in stats.get("parse_error", "")


def test_parse_cookie_text_supports_devtools_table(temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))
    raw = "\n".join(
        [
            "cookie2\tabc123\t.goofish.com\t/\t会话",
            "passport.goofish.com\t/\t2026-08-27T03:31:35.276Z",
            "_tb_token_\ttoken_xyz\t.goofish.com\t/\t会话",
            "sgcookie\tsgv\t.goofish.com\t/\t会话",
            "unb\t4057\t.goofish.com\t/\t会话",
        ]
    )
    parsed = ops.parse_cookie_text(raw)
    assert parsed["success"] is True
    assert "cookie2=abc123" in parsed["cookie"]
    assert "_tb_token_=token_xyz" in parsed["cookie"]
    assert parsed["cookie_items"] >= 4

    saved = ops.update_cookie(raw)
    assert saved["success"] is True
    assert saved["cookie_items"] >= 4
    assert saved["cookie_grade"] in {"可用", "高风险", "不可用"}
    assert "cookie2=abc123" in ops.get_cookie()["cookie"]


def test_parse_cookie_text_supports_netscape_and_json(temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))

    netscape = "\n".join(
        [
            "# Netscape HTTP Cookie File",
            ".goofish.com\tTRUE\t/\tFALSE\t0\tcookie2\tabc123",
            ".goofish.com\tTRUE\t/\tFALSE\t0\t_tb_token_\ttoken_xyz",
        ]
    )
    parsed_txt = ops.parse_cookie_text(netscape)
    assert parsed_txt["success"] is True
    assert parsed_txt["cookie_items"] == 2
    assert parsed_txt["detected_format"] in {"table_or_netscape", "header"}

    payload_json = '[{"name":"cookie2","value":"abc123"},{"name":"_tb_token_","value":"token_xyz"}]'
    parsed_json = ops.parse_cookie_text(payload_json)
    assert parsed_json["success"] is True
    assert parsed_json["cookie_items"] == 2
    assert "cookie2=abc123" in parsed_json["cookie"]


def test_parse_cookie_text_filters_non_goofish_domains(temp_dir) -> None:
    _ = temp_dir
    netscape = "\n".join(
        [
            "# Netscape HTTP Cookie File",
            ".example.com\tTRUE\t/\tFALSE\t0\tnonfish\tzzz",
            ".goofish.com\tTRUE\t/\tFALSE\t0\tcookie2\tabc123",
            "passport.goofish.com\tTRUE\t/\tFALSE\t0\t_tb_token_\ttoken_xyz",
        ]
    )

    parsed = MimicOps.parse_cookie_text(netscape)
    assert parsed["success"] is True
    assert "cookie2=abc123" in parsed["cookie"]
    assert "_tb_token_=token_xyz" in parsed["cookie"]
    assert "nonfish=zzz" not in parsed["cookie"]


def test_cookie_diagnose_reports_available_grade(temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))
    raw = "\n".join(
        [
            "# Netscape HTTP Cookie File",
            ".goofish.com\tTRUE\t/\tFALSE\t0\tcookie2\tabc123",
            ".goofish.com\tTRUE\t/\tFALSE\t0\t_tb_token_\ttoken_xyz",
            ".goofish.com\tTRUE\t/\tFALSE\t0\tsgcookie\tsgv",
            ".goofish.com\tTRUE\t/\tFALSE\t0\tunb\t4057",
            ".goofish.com\tTRUE\t/\tFALSE\t0\t_m_h5_tk\ttk_val_1772",
            ".goofish.com\tTRUE\t/\tFALSE\t0\t_m_h5_tk_enc\ttk_enc_val",
            ".goofish.com\tTRUE\t/\tFALSE\t0\tXSRF-TOKEN\txsrf_val",
            ".goofish.com\tTRUE\t/\tFALSE\t0\tlast_u_xianyu_web\tlogin_ctx",
            ".goofish.com\tTRUE\t/\tFALSE\t0\ttfstk\ttfstk_val",
            ".goofish.com\tTRUE\t/\tFALSE\t0\tt\tt_val",
            ".goofish.com\tTRUE\t/\tFALSE\t0\tcna\tcna_val",
        ]
    )

    result = ops.diagnose_cookie(raw)

    assert result["success"] is True
    assert result["grade"] == "可用"
    assert result["cookie_items"] >= 6
    assert result["required_missing"] == []
    assert result["recommended_missing"] == []
    assert result["domain_filter"]["applied"] is True


def test_cookie_diagnose_reports_unavailable_on_critical_missing(temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))
    raw = "cookie2=abc123; _tb_token_=token_xyz"

    result = ops.diagnose_cookie(raw)

    assert result["success"] is True
    assert result["grade"] == "不可用"
    assert "unb" in result["required_missing"]
    assert "sgcookie" in result["required_missing"]


def test_cookie_diagnose_reports_high_risk_when_recommended_keys_missing(temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))
    raw = "cookie2=abc123; _tb_token_=token_xyz; sgcookie=sgv; unb=4057; _m_h5_tk=tk_val_1772; _m_h5_tk_enc=tk_enc"

    result = ops.diagnose_cookie(raw)

    assert result["success"] is True
    assert result["grade"] == "高风险"
    assert "XSRF-TOKEN" in result["recommended_missing"]
    assert any("Export All Cookies" in action for action in result["actions"])


def test_import_cookie_plugin_files_supports_zip_export(temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))

    netscape = "\n".join(
        [
            "# Netscape HTTP Cookie File",
            ".goofish.com\tTRUE\t/\tFALSE\t0\tcookie2\tabc123",
            ".goofish.com\tTRUE\t/\tFALSE\t0\t_tb_token_\ttoken_xyz",
            ".goofish.com\tTRUE\t/\tFALSE\t0\tsgcookie\tsgv",
            ".goofish.com\tTRUE\t/\tFALSE\t0\tunb\t4057",
        ]
    )

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("cookies.txt", netscape)
        zf.writestr("README.md", "ignore")

    payload = ops.import_cookie_plugin_files([("plugin_export.zip", zip_buf.getvalue())])
    assert payload["success"] is True
    assert payload["cookie_items"] >= 4
    assert payload["cookie_grade"] in {"可用", "高风险", "不可用"}
    assert payload["source_file"].endswith("cookies.txt")
    assert payload["missing_required"] == []
    assert "cookie2=abc123" in ops.get_cookie()["cookie"]


def test_import_cookie_plugin_files_rejects_install_bundle_with_hint(temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Get-cookies.txt-LOCALLY/src/manifest.json", '{"name":"Get cookies"}')
        zf.writestr("Get-cookies.txt-LOCALLY/src/popup.mjs", "console.log('plugin source')")

    payload = ops.import_cookie_plugin_files([("Get-cookies.txt-LOCALLY_bundle.zip", zip_buf.getvalue())])

    assert payload["success"] is False
    assert "installation bundle" in payload["error"]
    assert "先在浏览器安装插件并导出" in payload.get("hint", "")


def test_import_cookie_plugin_files_rejects_root_plugin_zip_with_hint(temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", '{"name":"Get cookies"}')
        zf.writestr("popup.mjs", "console.log('plugin source')")

    payload = ops.import_cookie_plugin_files([("plugin_root_bundle.zip", zip_buf.getvalue())])

    assert payload["success"] is False
    assert "installation bundle" in payload["error"]
    assert "先在浏览器安装插件并导出" in payload.get("hint", "")


def test_import_cookie_plugin_files_supports_extensionless_cookie_file(temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))
    netscape = "\n".join(
        [
            "# Netscape HTTP Cookie File",
            ".goofish.com\tTRUE\t/\tFALSE\t0\tcookie2\tabc123",
            ".goofish.com\tTRUE\t/\tFALSE\t0\t_tb_token_\ttoken_xyz",
            ".goofish.com\tTRUE\t/\tFALSE\t0\tsgcookie\tsgv",
            ".goofish.com\tTRUE\t/\tFALSE\t0\tunb\t4057",
        ]
    )
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("cookies", netscape)

    payload = ops.import_cookie_plugin_files([("cookie_no_ext.zip", zip_buf.getvalue())])

    assert payload["success"] is True
    assert payload["cookie_items"] >= 4
    assert "cookie2=abc123" in ops.get_cookie()["cookie"]


def test_export_cookie_plugin_bundle(temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))
    base = temp_dir / "third_party" / "Get-cookies.txt-LOCALLY"
    src = base / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "manifest.json").write_text('{"name":"test-plugin"}', encoding="utf-8")
    (base / "LICENSE").write_text("MIT", encoding="utf-8")
    (base / "SOURCE_INFO.txt").write_text("source", encoding="utf-8")

    data, filename = ops.export_cookie_plugin_bundle()
    assert filename.endswith(".zip")
    assert len(data) > 0

    with zipfile.ZipFile(io.BytesIO(data), mode="r") as zf:
        names = set(zf.namelist())
        assert "Get-cookies.txt-LOCALLY/src/manifest.json" in names
        assert "Get-cookies.txt-LOCALLY/LICENSE" in names


def test_markup_rules_round_trip(temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))

    base = ops.get_markup_rules()
    assert base["success"] is True
    assert "default" in base["markup_rules"]

    rules = {
        "default": {
            "normal_first_add": 0.5,
            "member_first_add": 0.25,
            "normal_extra_add": 0.5,
            "member_extra_add": 0.3,
        },
        "圆通": {
            "normal_first_add": 0.66,
            "member_first_add": 0.35,
            "normal_extra_add": 0.55,
            "member_extra_add": 0.33,
        },
    }
    saved = ops.save_markup_rules(rules)
    assert saved["success"] is True
    assert "圆通" in saved["markup_rules"]
    assert saved["markup_rules"]["圆通"]["normal_first_add"] == 0.66

    loaded = ops.get_markup_rules()
    assert loaded["success"] is True
    assert loaded["markup_rules"]["圆通"]["member_extra_add"] == 0.33


def test_import_markup_supports_csv_and_zip(temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))

    csv_text = "\n".join(
        [
            "运力,首重溢价(普通),首重溢价(会员),续重溢价(普通),续重溢价(会员)",
            "圆通,0.66,0.35,0.55,0.33",
            "韵达,0.88,0.58,0.41,0.31",
        ]
    )

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("markup.csv", csv_text)
        zf.writestr("readme.txt", "ignore this")

    payload = ops.import_markup_files([("markup_bundle.zip", zip_buf.getvalue())])
    assert payload["success"] is True
    assert "圆通" in payload["markup_rules"]
    assert payload["markup_rules"]["圆通"]["normal_first_add"] == 0.66
    assert payload["markup_rules"]["韵达"]["member_first_add"] == 0.58
    assert any(item.endswith("markup.csv") for item in payload["imported_files"])


def test_import_markup_supports_json_yaml_and_text(temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))

    payload_json = json.dumps(
        {
            "markup_rules": {
                "default": {
                    "normal_first_add": 0.5,
                    "member_first_add": 0.25,
                    "normal_extra_add": 0.5,
                    "member_extra_add": 0.3,
                },
                "中通": {
                    "normal_first_add": 0.61,
                    "member_first_add": 0.31,
                    "normal_extra_add": 0.62,
                    "member_extra_add": 0.42,
                },
            }
        },
        ensure_ascii=False,
    )
    yaml_text = "\n".join(
        [
            "default:",
            "  normal_first_add: 0.5",
            "  member_first_add: 0.25",
            "  normal_extra_add: 0.5",
            "  member_extra_add: 0.3",
            "申通:",
            "  normal_first_add: 0.51",
            "  member_first_add: 0.26",
            "  normal_extra_add: 0.52",
            "  member_extra_add: 0.31",
        ]
    )
    txt_text = "\n".join(
        [
            "快递 首重普通 首重会员 续重普通 续重会员",
            "德邦 0.70 0.40 0.50 0.30",
        ]
    )

    payload = ops.import_markup_files(
        [
            ("markup.json", payload_json.encode("utf-8")),
            ("markup.yaml", yaml_text.encode("utf-8")),
            ("markup.txt", txt_text.encode("utf-8")),
        ]
    )

    assert payload["success"] is True
    assert payload["markup_rules"]["中通"]["normal_first_add"] == 0.61
    assert payload["markup_rules"]["申通"]["member_extra_add"] == 0.31
    assert payload["markup_rules"]["德邦"]["member_first_add"] == 0.4


def test_import_markup_can_infer_from_route_cost_csv(temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))
    route_csv = "\n".join(
        [
            "快递公司,始发地,目的地,首重,续重,抛比",
            "圆通快递,安徽,广州,3.2,1.6,8000",
            "韵达,安徽,上海,3.5,1.8,8000",
        ]
    )

    payload = ops.import_markup_files([("route_cost.csv", route_csv.encode("utf-8"))])
    assert payload["success"] is True
    assert "圆通" in payload["markup_rules"]
    assert "韵达" in payload["markup_rules"]
    assert payload["detected_formats"]["route_cost_infer"] >= 1


def test_dashboard_home_contains_risk_control_rows() -> None:
    assert "封控状态" in DASHBOARD_HTML
    assert "风险分/信号" in DASHBOARD_HTML
    assert "最近封控事件" in DASHBOARD_HTML
    assert "恢复阶段" in DASHBOARD_HTML
    assert "自动恢复触发" in DASHBOARD_HTML
    assert "降级运行" in DASHBOARD_HTML
    assert "Token异常" in DASHBOARD_HTML
    assert "需更新Cookie" in DASHBOARD_HTML
    assert "全链路体检" in DASHBOARD_HTML
    assert "一键修复" in DASHBOARD_HTML
    assert "售前一键恢复" in DASHBOARD_HTML


def test_risk_control_status_detects_blocked_signal(temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))
    runtime_dir = temp_dir / "data" / "module_runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "presales.log").write_text(
        "\n".join(
            [
                "\x1b[32m2026-02-28 15:15:01\x1b[0m | WARNING | WebSocket disconnected retrying",
                "\x1b[32m2026-02-28 15:15:05\x1b[0m | WARNING | Token API failed: ['FAIL_SYS_USER_VALIDATE', 'RGV587_ERROR']",
            ]
        ),
        encoding="utf-8",
    )

    risk = ops._risk_control_status_from_logs(target="presales", tail_lines=100)
    assert risk["level"] == "blocked"
    assert risk["label"] == "疑似封控"
    assert risk["score"] >= 75
    assert "FAIL_SYS_USER_VALIDATE" in risk["last_event"]
    assert risk["last_event_at"] == "2026-02-28 15:15:05"


def test_risk_control_status_detects_warning_signal(temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))
    runtime_dir = temp_dir / "data" / "module_runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    lines = [f"2026-02-28 15:14:{10 + i:02d} | WARNING | Goofish WebSocket disconnected: HTTP 400" for i in range(6)]
    (runtime_dir / "presales.log").write_text("\n".join(lines), encoding="utf-8")

    risk = ops._risk_control_status_from_logs(target="presales", tail_lines=120)
    assert risk["level"] == "warning"
    assert risk["label"] == "风险预警"
    assert risk["score"] > 0
    assert any("WebSocket HTTP 400" in item for item in risk["signals"])


def test_risk_control_status_recovers_when_connected_after_failures(temp_dir) -> None:
    ops = MimicOps(project_root=temp_dir, module_console=ModuleConsole(project_root=temp_dir))
    runtime_dir = temp_dir / "data" / "module_runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "presales.log").write_text(
        "\n".join(
            [
                "2026-02-28 15:15:05 | WARNING | Token API failed: ['FAIL_SYS_USER_VALIDATE', 'RGV587_ERROR']",
                "2026-02-28 15:15:10 | INFO | Connected to Goofish WebSocket transport",
            ]
        ),
        encoding="utf-8",
    )

    risk = ops._risk_control_status_from_logs(target="presales", tail_lines=100)
    assert risk["level"] == "normal"
    assert risk["label"] == "已恢复连接"
    assert "最近已恢复连接" in risk["signals"]
    assert risk["last_connected_at"] == "2026-02-28 15:15:10"


def test_service_status_marks_degraded_on_auth_failure(temp_dir) -> None:
    class StubModuleConsole:
        def status(self, window_minutes: int = 60, limit: int = 20) -> dict[str, object]:
            return {
                "alive_count": 1,
                "total_modules": 3,
                "modules": {
                    "presales": {
                        "process": {"alive": True, "pid": 12345},
                        "sla": {"event_count": 0},
                        "workflow": {"states": {}, "jobs": {}},
                    }
                },
            }

    ops = MimicOps(project_root=temp_dir, module_console=StubModuleConsole())
    (temp_dir / ".env").write_text(
        "XIANYU_COOKIE_1=unb=4057246664; _tb_token_=abc; cookie2=def; sgcookie=ghi\n",
        encoding="utf-8",
    )
    runtime_dir = temp_dir / "data" / "module_runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "presales.log").write_text(
        "2026-02-28 15:15:05 | WARNING | Token API failed: ['FAIL_SYS_USER_VALIDATE', 'RGV587_ERROR']\n",
        encoding="utf-8",
    )

    status = ops.service_status()
    assert status["service_status"] == "degraded"
    assert status["token_error"] == "FAIL_SYS_USER_VALIDATE"
    assert status["cookie_update_required"] is True
    assert status["xianyu_connected"] is False
    assert status["token_available"] is False
    assert status["user_id"] == "4057246664"
    assert status.get("recovery", {}).get("stage") in {"waiting_cookie_update", "waiting_reconnect"}
    assert status.get("recovery", {}).get("stage_label")
    assert status.get("recovery", {}).get("advice")


def test_service_status_clears_token_error_after_connected_event(temp_dir) -> None:
    class StubModuleConsole:
        def status(self, window_minutes: int = 60, limit: int = 20) -> dict[str, object]:
            return {
                "alive_count": 1,
                "total_modules": 3,
                "modules": {
                    "presales": {
                        "process": {"alive": True, "pid": 12345},
                        "sla": {"event_count": 0},
                        "workflow": {"states": {}, "jobs": {}},
                    }
                },
            }

    ops = MimicOps(project_root=temp_dir, module_console=StubModuleConsole())
    (temp_dir / ".env").write_text(
        "XIANYU_COOKIE_1=unb=4057246664; _tb_token_=abc; cookie2=def; sgcookie=ghi; _m_h5_tk=tk_1; _m_h5_tk_enc=enc_1\n",
        encoding="utf-8",
    )
    runtime_dir = temp_dir / "data" / "module_runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "presales.log").write_text(
        "\n".join(
            [
                "2026-02-28 15:15:05 | WARNING | Token API failed: ['FAIL_SYS_USER_VALIDATE', 'RGV587_ERROR']",
                "2026-02-28 15:15:10 | INFO | Connected to Goofish WebSocket transport",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    status = ops.service_status()
    assert status["token_error"] is None
    assert status["xianyu_connected"] is True
    assert status["risk_control"]["level"] == "normal"
    assert status["service_status"] == "running"


def test_service_status_auto_recover_on_cookie_change_after_validate_error(temp_dir) -> None:
    class StubModuleConsole:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def status(self, window_minutes: int = 60, limit: int = 20) -> dict[str, object]:
            _ = (window_minutes, limit)
            return {
                "alive_count": 1,
                "total_modules": 3,
                "modules": {
                    "presales": {
                        "process": {"alive": True, "pid": 12345},
                        "sla": {"event_count": 0},
                        "workflow": {"states": {}, "jobs": {}},
                    }
                },
            }

        def control(self, action: str, target: str) -> dict[str, object]:
            self.calls.append((action, target))
            return {"target": target, "action": action, "ok": True}

    console = StubModuleConsole()
    ops = MimicOps(project_root=temp_dir, module_console=console)
    env_path = temp_dir / ".env"
    env_path.write_text(
        "XIANYU_COOKIE_1=unb=1001; _tb_token_=aaa; cookie2=bbb; sgcookie=ccc; _m_h5_tk=tk1_1; _m_h5_tk_enc=enc1\n",
        encoding="utf-8",
    )
    runtime_dir = temp_dir / "data" / "module_runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "presales.log").write_text(
        "2026-02-28 15:15:05 | WARNING | Token API failed: ['FAIL_SYS_USER_VALIDATE', 'RGV587_ERROR']\n",
        encoding="utf-8",
    )

    first = ops.service_status()
    assert first["token_error"] == "FAIL_SYS_USER_VALIDATE"
    assert first["recovery"]["auto_recover_triggered"] is False
    assert console.calls == []

    env_path.write_text(
        "XIANYU_COOKIE_1=unb=1001; _tb_token_=aaa2; cookie2=bbb2; sgcookie=ccc2; _m_h5_tk=tk2_2; _m_h5_tk_enc=enc2\n",
        encoding="utf-8",
    )
    second = ops.service_status()
    assert second["recovery"]["auto_recover_triggered"] is True
    assert second["recovery"]["stage"] == "recover_triggered"
    assert console.calls == [("recover", "presales")]

    third = ops.service_status()
    assert third["recovery"]["auto_recover_triggered"] is False
    assert len(console.calls) == 1


def test_update_cookie_with_auto_recover_triggers_presales_recover(temp_dir) -> None:
    class StubModuleConsole:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def control(self, action: str, target: str) -> dict[str, object]:
            self.calls.append((action, target))
            return {"target": target, "action": action, "ok": True}

    console = StubModuleConsole()
    ops = MimicOps(project_root=temp_dir, module_console=console)

    payload = ops.update_cookie(
        "unb=1001; _tb_token_=aaa; cookie2=bbb; sgcookie=ccc; _m_h5_tk=tk1_1; _m_h5_tk_enc=enc1",
        auto_recover=True,
    )

    assert payload["success"] is True
    assert payload.get("auto_recover", {}).get("triggered") is True
    assert console.calls == [("recover", "presales")]


def test_import_cookie_plugin_files_with_auto_recover_triggers_presales_recover(temp_dir) -> None:
    class StubModuleConsole:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def control(self, action: str, target: str) -> dict[str, object]:
            self.calls.append((action, target))
            return {"target": target, "action": action, "ok": True}

    console = StubModuleConsole()
    ops = MimicOps(project_root=temp_dir, module_console=console)
    netscape = "\n".join(
        [
            "# Netscape HTTP Cookie File",
            ".goofish.com\tTRUE\t/\tFALSE\t0\tcookie2\tabc123",
            ".goofish.com\tTRUE\t/\tFALSE\t0\t_tb_token_\ttoken_xyz",
            ".goofish.com\tTRUE\t/\tFALSE\t0\tsgcookie\tsgv",
            ".goofish.com\tTRUE\t/\tFALSE\t0\tunb\t4057",
            ".goofish.com\tTRUE\t/\tFALSE\t0\t_m_h5_tk\ttk_1",
            ".goofish.com\tTRUE\t/\tFALSE\t0\t_m_h5_tk_enc\tenc_1",
        ]
    )

    payload = ops.import_cookie_plugin_files([("cookies.txt", netscape.encode("utf-8"))], auto_recover=True)

    assert payload["success"] is True
    assert payload.get("auto_recover", {}).get("triggered") is True
    assert console.calls == [("recover", "presales")]


def test_service_recover_calls_module_recover_and_returns_state(temp_dir) -> None:
    class StubModuleConsole:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def control(self, action: str, target: str) -> dict[str, object]:
            self.calls.append((action, target))
            return {"target": target, "action": action, "ok": True}

        def status(self, window_minutes: int = 60, limit: int = 20) -> dict[str, object]:
            _ = (window_minutes, limit)
            return {
                "alive_count": 1,
                "total_modules": 3,
                "modules": {
                    "presales": {
                        "process": {"alive": True, "pid": 12345},
                        "sla": {"event_count": 0},
                        "workflow": {"states": {}, "jobs": {}},
                    }
                },
            }

    console = StubModuleConsole()
    ops = MimicOps(project_root=temp_dir, module_console=console)
    (temp_dir / ".env").write_text(
        "XIANYU_COOKIE_1=unb=4057246664; _tb_token_=abc; cookie2=def; sgcookie=ghi\n",
        encoding="utf-8",
    )

    payload = ops.service_recover("presales")

    assert payload["success"] is True
    assert payload["target"] == "presales"
    assert console.calls == [("recover", "presales")]


def test_service_auto_fix_returns_cookie_update_required_when_validate_failed(temp_dir) -> None:
    class StubModuleConsole:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def status(self, window_minutes: int = 60, limit: int = 20) -> dict[str, object]:
            _ = (window_minutes, limit)
            return {
                "alive_count": 1,
                "total_modules": 3,
                "modules": {
                    "presales": {
                        "process": {"alive": True, "pid": 12345},
                        "sla": {"event_count": 0},
                        "workflow": {"states": {}, "jobs": {}},
                    }
                },
            }

        def control(self, action: str, target: str) -> dict[str, object]:
            self.calls.append((action, target))
            return {"target": target, "action": action, "ok": True}

        def check(self, skip_gateway: bool = False) -> dict[str, object]:
            _ = skip_gateway
            return {"target": "all", "ready": True, "blockers": []}

    console = StubModuleConsole()
    ops = MimicOps(project_root=temp_dir, module_console=console)
    (temp_dir / ".env").write_text(
        "XIANYU_COOKIE_1=unb=4057246664; _tb_token_=abc; cookie2=def; sgcookie=ghi\n",
        encoding="utf-8",
    )
    runtime_dir = temp_dir / "data" / "module_runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "presales.log").write_text(
        "2026-02-28 15:15:05 | WARNING | Token API failed: ['FAIL_SYS_USER_VALIDATE', 'RGV587_ERROR']\n",
        encoding="utf-8",
    )

    payload = ops.service_auto_fix()

    assert payload["success"] is False
    assert payload["needs_cookie_update"] is True
    assert "更新 Cookie" in payload["message"]

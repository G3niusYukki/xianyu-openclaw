"""dashboard_server 测试。"""

import io
import json
import sqlite3
import zipfile

from src.dashboard_server import MIMIC_COOKIE_HTML, DashboardRepository, MimicOps, ModuleConsole, _safe_int


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
    assert payload["source_file"].endswith("cookies.txt")
    assert payload["missing_required"] == []
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

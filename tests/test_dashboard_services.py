"""Tests for the dashboard service-layer modules extracted from dashboard_server.py.

Covers:
- config_service: read/write/mask/update system_config.json
- repository: DashboardRepository SQLite queries
- module_console: ModuleConsole CLI wrapper + _extract_json_payload
- router: route registration decorators and dispatch
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.dashboard.config_service import (
    read_system_config,
    write_system_config,
    mask_sensitive,
    update_config,
    CONFIG_SECTIONS,
    _ALLOWED_CONFIG_SECTIONS,
    _SENSITIVE_CONFIG_KEYS,
)
from src.dashboard.repository import DashboardRepository
from src.dashboard.module_console import ModuleConsole, MODULE_TARGETS, _extract_json_payload
from src.dashboard import router as route_mod


# ---------------------------------------------------------------------------
# config_service
# ---------------------------------------------------------------------------

class TestConfigService:

    def test_read_write_roundtrip(self, tmp_path: Path):
        cfg_file = tmp_path / "server" / "data" / "system_config.json"
        with patch("src.dashboard.config_service._SYS_CONFIG_FILE", cfg_file):
            data = {"ai": {"api_key": "sk-test123"}}
            write_system_config(data)
            assert cfg_file.exists()
            loaded = read_system_config()
            assert loaded == data

    def test_read_missing_file(self, tmp_path: Path):
        cfg_file = tmp_path / "nonexistent" / "system_config.json"
        with patch("src.dashboard.config_service._SYS_CONFIG_FILE", cfg_file):
            assert read_system_config() == {}

    def test_read_corrupt_file(self, tmp_path: Path):
        cfg_file = tmp_path / "system_config.json"
        cfg_file.write_text("not json!", encoding="utf-8")
        with patch("src.dashboard.config_service._SYS_CONFIG_FILE", cfg_file):
            assert read_system_config() == {}

    def test_mask_sensitive_keys(self):
        cfg = {
            "ai": {"api_key": "sk-secretvalue123", "model": "qwen-plus"},
            "xianguanjia": {"app_key": "public", "app_secret": "topsecret99"},
        }
        masked = mask_sensitive(cfg)
        assert masked["ai"]["api_key"] == "sk-s****"
        assert masked["ai"]["model"] == "qwen-plus"
        assert masked["xianguanjia"]["app_key"] == "public"
        assert masked["xianguanjia"]["app_secret"] == "tops****"

    def test_mask_sensitive_empty_values(self):
        cfg = {"ai": {"api_key": "", "model": "gpt-4o"}}
        masked = mask_sensitive(cfg)
        assert masked["ai"]["api_key"] == ""

    def test_mask_non_dict_section(self):
        cfg = {"version": 2, "ai": {"api_key": "sk-123"}}
        masked = mask_sensitive(cfg)
        assert masked["version"] == 2

    def test_update_config_merges(self, tmp_path: Path):
        cfg_file = tmp_path / "server" / "data" / "system_config.json"
        with patch("src.dashboard.config_service._SYS_CONFIG_FILE", cfg_file):
            write_system_config({"ai": {"api_key": "old", "model": "qwen"}})
            result = update_config({"ai": {"model": "deepseek-chat"}})
            assert result["ai"]["model"] == "deepseek-chat"
            assert result["ai"]["api_key"] == "old"

    def test_update_config_ignores_unknown_section(self, tmp_path: Path):
        cfg_file = tmp_path / "server" / "data" / "system_config.json"
        with patch("src.dashboard.config_service._SYS_CONFIG_FILE", cfg_file):
            write_system_config({})
            result = update_config({"unknown_section": {"foo": "bar"}})
            assert "unknown_section" not in result

    def test_update_config_skips_masked_values(self, tmp_path: Path):
        cfg_file = tmp_path / "server" / "data" / "system_config.json"
        with patch("src.dashboard.config_service._SYS_CONFIG_FILE", cfg_file):
            write_system_config({"ai": {"api_key": "real-key"}})
            result = update_config({"ai": {"api_key": "real****"}})
            assert result["ai"]["api_key"] == "real-key"

    def test_config_sections_structure(self):
        assert len(CONFIG_SECTIONS) > 0
        keys = {s["key"] for s in CONFIG_SECTIONS}
        assert "xianguanjia" in keys
        assert "ai" in keys
        assert "notifications" in keys
        for section in CONFIG_SECTIONS:
            assert "key" in section
            assert "name" in section
            assert "fields" in section

    def test_allowed_sections_match(self):
        assert "ai" in _ALLOWED_CONFIG_SECTIONS
        assert "store" in _ALLOWED_CONFIG_SECTIONS
        assert "random_junk" not in _ALLOWED_CONFIG_SECTIONS


# ---------------------------------------------------------------------------
# repository
# ---------------------------------------------------------------------------

def _create_test_db(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS operation_logs (
            id INTEGER PRIMARY KEY,
            operation_type TEXT,
            product_id TEXT,
            account_id TEXT,
            status TEXT,
            timestamp TEXT DEFAULT (datetime('now','localtime')),
            message TEXT
        );
        CREATE TABLE IF NOT EXISTS products (
            product_id TEXT PRIMARY KEY,
            title TEXT,
            status TEXT DEFAULT 'active',
            price INTEGER DEFAULT 0,
            pic_url TEXT
        );
        CREATE TABLE IF NOT EXISTS product_metrics (
            id INTEGER PRIMARY KEY,
            product_id TEXT,
            views INTEGER DEFAULT 0,
            wants INTEGER DEFAULT 0,
            sales INTEGER DEFAULT 0,
            inquiries INTEGER DEFAULT 0,
            timestamp TEXT DEFAULT (datetime('now','localtime'))
        );
    """)
    conn.execute("INSERT INTO products VALUES ('p1','Test Product','active',1000,NULL)")
    conn.execute("INSERT INTO products VALUES ('p2','Sold Item','sold',2000,NULL)")
    conn.execute("INSERT INTO product_metrics (product_id,views,wants,sales,inquiries) VALUES ('p1',100,10,2,5)")
    conn.execute("INSERT INTO product_metrics (product_id,views,wants,sales,inquiries) VALUES ('p2',50,5,1,3)")
    conn.execute("""INSERT INTO operation_logs (operation_type,product_id,account_id,status,message)
                    VALUES ('publish','p1','acc1','success','Published product')""")
    conn.execute("""INSERT INTO operation_logs (operation_type,product_id,account_id,status,message)
                    VALUES ('price_adjust','p2','acc1','failed','Error adjusting price')""")
    conn.commit()
    conn.close()


class TestDashboardRepository:

    @pytest.fixture
    def repo(self, tmp_path: Path) -> DashboardRepository:
        db = str(tmp_path / "test.db")
        _create_test_db(db)
        return DashboardRepository(db)

    def test_get_summary(self, repo: DashboardRepository):
        summary = repo.get_summary()
        assert summary["active_products"] == 1
        assert summary["sold_products"] == 1
        assert summary["total_views"] == 150
        assert summary["total_wants"] == 15
        assert summary["total_sales"] == 3
        assert summary["total_operations"] == 2

    def test_get_trend_default_metric(self, repo: DashboardRepository):
        trend = repo.get_trend("views", 7)
        assert len(trend) == 7
        assert all("date" in d and "value" in d for d in trend)
        total = sum(d["value"] for d in trend)
        assert total == 150

    def test_get_trend_invalid_metric_falls_back(self, repo: DashboardRepository):
        trend = repo.get_trend("invalid_metric", 3)
        assert len(trend) == 3

    def test_get_recent_operations(self, repo: DashboardRepository):
        ops = repo.get_recent_operations(10)
        assert len(ops) == 2
        assert ops[0]["operation_type"] in ("publish", "price_adjust")

    def test_get_recent_operations_limit(self, repo: DashboardRepository):
        ops = repo.get_recent_operations(1)
        assert len(ops) == 1

    def test_get_top_products(self, repo: DashboardRepository):
        top = repo.get_top_products(5)
        assert len(top) == 2
        assert top[0]["wants"] >= top[1]["wants"]


# ---------------------------------------------------------------------------
# module_console
# ---------------------------------------------------------------------------

class TestExtractJsonPayload:

    def test_valid_json_object(self):
        assert _extract_json_payload('{"ok": true}') == {"ok": True}

    def test_valid_json_array(self):
        assert _extract_json_payload('[1, 2, 3]') == [1, 2, 3]

    def test_json_embedded_in_text(self):
        result = _extract_json_payload('some log output\n{"status":"running"}\nmore text')
        assert result == {"status": "running"}

    def test_empty_string(self):
        assert _extract_json_payload("") is None

    def test_none_input(self):
        assert _extract_json_payload(None) is None

    def test_no_json(self):
        assert _extract_json_payload("just plain text") is None


class TestModuleConsole:

    def test_module_targets_tuple(self):
        assert "presales" in MODULE_TARGETS
        assert "operations" in MODULE_TARGETS
        assert "aftersales" in MODULE_TARGETS

    def test_control_invalid_action(self):
        mc = ModuleConsole("/tmp/fake_project")
        result = mc.control("destroy", "all")
        assert "error" in result

    def test_control_invalid_target(self):
        mc = ModuleConsole("/tmp/fake_project")
        result = mc.control("start", "nonexistent")
        assert "error" in result

    @patch("subprocess.run")
    def test_status_calls_cli(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"modules":{"presales":{"status":"running"}}}',
            stderr="",
        )
        mc = ModuleConsole("/tmp/fake_project")
        result = mc.status()
        assert result.get("modules") is not None
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_logs_sanitizes_target(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='{"ok":true}', stderr="")
        mc = ModuleConsole("/tmp/fake_project")
        result = mc.logs("evil_target")
        assert result["ok"]
        args = mock_run.call_args[0][0]
        assert "--target" in args
        idx = args.index("--target")
        assert args[idx + 1] == "all"


# ---------------------------------------------------------------------------
# router
# ---------------------------------------------------------------------------

class TestRouter:

    def setup_method(self):
        route_mod._GET_ROUTES.clear()
        route_mod._POST_ROUTES.clear()
        route_mod._PUT_ROUTES.clear()

    def test_get_decorator_registers(self):
        @route_mod.get("/test")
        def handler(h): pass

        assert route_mod.dispatch_get("/test") is handler

    def test_post_decorator_registers(self):
        @route_mod.post("/submit")
        def handler(h): pass

        assert route_mod.dispatch_post("/submit") is handler

    def test_put_decorator_registers(self):
        @route_mod.put("/update")
        def handler(h): pass

        assert route_mod.dispatch_put("/update") is handler

    def test_dispatch_unknown_returns_none(self):
        assert route_mod.dispatch_get("/nonexistent") is None
        assert route_mod.dispatch_post("/nonexistent") is None
        assert route_mod.dispatch_put("/nonexistent") is None

    def test_all_routes_summary(self):
        @route_mod.get("/a")
        def h1(h): pass

        @route_mod.post("/b")
        def h2(h): pass

        summary = route_mod.all_routes()
        assert "/a" in summary["GET"]
        assert "/b" in summary["POST"]
        assert summary["PUT"] == []

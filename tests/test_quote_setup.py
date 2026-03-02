"""Tests for src.modules.quote.setup."""

from pathlib import Path

import pytest

from src.modules.quote.setup import QuoteSetupService


def test_apply_rejects_invalid_mode_and_profile(tmp_path: Path) -> None:
    """分支：非法 mode / pricing_profile 抛 ValueError。"""
    svc = QuoteSetupService(config_path=str(tmp_path / "config.yaml"))

    with pytest.raises(ValueError, match="Unsupported quote mode"):
        svc.apply(mode="invalid", origin_city=None, pricing_profile="normal", cost_table_dir="d")

    with pytest.raises(ValueError, match="pricing_profile"):
        svc.apply(mode="rule_only", origin_city=None, pricing_profile="vip", cost_table_dir="d")


def test_apply_creates_from_example_and_fills_defaults(tmp_path: Path) -> None:
    """分支：配置不存在时从 config.example 读取；pattern 空列表回退默认；目录不存在扫描分支。"""
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.example.yaml").write_text("quote: {}\n", encoding="utf-8")

    svc = QuoteSetupService(config_path=str(cfg_dir / "config.yaml"))
    result = svc.apply(
        mode="rule_only",
        origin_city=None,
        pricing_profile="normal",
        cost_table_dir=str(tmp_path / "missing"),
        cost_table_patterns=["  ", ""],
    )

    assert result["success"] is True
    assert result["backup_path"] == ""
    assert result["quote"]["cost_table_patterns"] == ["*.xlsx", "*.csv"]
    assert result["cost_table"]["exists"] is False


def test_apply_existing_config_backup_and_api_mode_updates(tmp_path: Path, monkeypatch) -> None:
    """分支：已有配置触发备份；api 模式写入 cost_api_url/key；保留已有 markup_rules。"""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "quote:\n"
        "  markup_rules:\n"
        "    default:\n"
        "      normal_first_add: 9\n"
        "      normal_extra_add: 8\n",
        encoding="utf-8",
    )

    class _FixedNow:
        @staticmethod
        def now():
            from datetime import datetime

            return datetime(2026, 3, 1, 4, 30, 0)

    monkeypatch.setattr("src.modules.quote.setup.datetime", _FixedNow)

    table_dir = tmp_path / "tables"
    table_dir.mkdir()
    (table_dir / "a.csv").write_text("x", encoding="utf-8")
    (table_dir / "b.xlsx").write_text("x", encoding="utf-8")

    svc = QuoteSetupService(config_path=str(cfg))
    result = svc.apply(
        mode="api_cost_plus_markup",
        origin_city="杭州",
        pricing_profile="member",
        cost_table_dir=str(table_dir),
        cost_table_patterns=["*.csv", "*.xlsx", "*.csv"],
        api_cost_url="https://api.local/quote",
        cost_api_key_env="MY_TOKEN",
    )

    assert result["backup_path"].endswith("config.yaml.bak.20260301043000")
    assert result["quote"]["cost_api_url"] == "https://api.local/quote"
    assert result["quote"]["pricing_profile"] == "member"

    written = cfg.read_text(encoding="utf-8")
    assert "cost_api_key: ${MY_TOKEN}" in written
    assert "normal_first_add: 9" in written

    assert result["cost_table"]["exists"] is True
    assert result["cost_table"]["file_count"] == 2
    assert set(result["cost_table"]["files"]) == {"a.csv", "b.xlsx"}


def test_scan_cost_table_dir_file_path_branch(tmp_path: Path) -> None:
    """分支：_scan_cost_table_dir 入参是文件路径时 file_count=1。"""
    fp = tmp_path / "single.csv"
    fp.write_text("x", encoding="utf-8")

    stats = QuoteSetupService._scan_cost_table_dir(str(fp), patterns=None)
    assert stats == {"exists": True, "file_count": 1, "files": ["single.csv"]}

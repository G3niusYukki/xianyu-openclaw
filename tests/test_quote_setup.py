"""自动报价一键配置测试。"""

from pathlib import Path

import pytest
import yaml

from src.modules.quote.setup import QuoteSetupService


def _read_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {}
    return data


def test_quote_setup_apply_local_mode_with_backup(temp_dir: Path) -> None:
    config_path = temp_dir / "config.yaml"
    config_path.write_text("app:\n  name: demo\n", encoding="utf-8")

    cost_dir = temp_dir / "costs"
    cost_dir.mkdir(parents=True, exist_ok=True)
    (cost_dir / "cost.csv").write_text(
        "快递公司,始发地,目的地,首重,续重\n圆通,安徽,上海,3.2,1.6\n",
        encoding="utf-8",
    )

    service = QuoteSetupService(str(config_path))
    result = service.apply(
        mode="cost_table_plus_markup",
        origin_city="安徽",
        pricing_profile="normal",
        cost_table_dir=str(cost_dir),
    )

    assert result["success"] is True
    assert result["backup_path"]
    assert Path(result["backup_path"]).exists()
    assert result["cost_table"]["file_count"] == 1

    cfg = _read_yaml(config_path)
    assert cfg["quote"]["mode"] == "cost_table_plus_markup"
    assert cfg["quote"]["origin_city"] == "安徽"
    assert cfg["quote"]["pricing_profile"] == "normal"
    assert cfg["quote"]["cost_table_dir"] == str(cost_dir)
    assert isinstance(cfg["quote"]["markup_rules"], dict)
    assert "default" in cfg["quote"]["markup_rules"]


def test_quote_setup_apply_api_mode_sets_api_fields(temp_dir: Path) -> None:
    config_path = temp_dir / "config.yaml"
    config_path.write_text("quote: {}\n", encoding="utf-8")

    service = QuoteSetupService(str(config_path))
    service.apply(
        mode="api_cost_plus_markup",
        origin_city="杭州",
        pricing_profile="member",
        cost_table_dir=str(temp_dir / "costs"),
        api_cost_url="https://example.com/cost",
        cost_api_key_env="MY_QUOTE_KEY",
    )

    cfg = _read_yaml(config_path)
    assert cfg["quote"]["mode"] == "api_cost_plus_markup"
    assert cfg["quote"]["origin_city"] == "杭州"
    assert cfg["quote"]["pricing_profile"] == "member"
    assert cfg["quote"]["cost_api_url"] == "https://example.com/cost"
    assert cfg["quote"]["cost_api_key"] == "${MY_QUOTE_KEY}"
    assert cfg["quote"]["api_fallback_to_table_parallel"] is True


def test_quote_setup_apply_rejects_invalid_mode(temp_dir: Path) -> None:
    config_path = temp_dir / "config.yaml"
    service = QuoteSetupService(str(config_path))

    with pytest.raises(ValueError):
        service.apply(
            mode="invalid_mode",
            origin_city="杭州",
            pricing_profile="normal",
            cost_table_dir="data/quote_costs",
        )

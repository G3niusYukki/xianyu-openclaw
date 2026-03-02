from pathlib import Path

from src.modules.quote import providers
from src.modules.quote.setup import QuoteSetupService


def test_quote_providers_and_setup_remaining_lines(tmp_path: Path):
    rules = providers._normalize_markup_rules({"sf": {"normal_first_add": 2}})
    assert "default" in rules

    parsed = providers._parse_cost_api_response(["bad-item"])
    assert isinstance(parsed, dict)

    cfg = tmp_path / "config.yaml"
    cfg.write_text("- just\n- list\n", encoding="utf-8")
    data, exists = QuoteSetupService(config_path=str(cfg))._load_yaml()
    assert exists is True and data == {}

    cfg.unlink()
    ex = tmp_path / "config.example.yaml"
    ex.write_text("- just\n- list\n", encoding="utf-8")
    data, exists = QuoteSetupService(config_path=str(cfg))._load_yaml()
    assert exists is False and data == {}

from __future__ import annotations

import builtins
import inspect
from pathlib import Path

from src.modules.quote import providers as qp
from src.modules.quote.providers import _normalize_markup_rules, _parse_cost_api_response
from src.modules.quote.setup import QuoteSetupService


def test_quote_setup_load_yaml_truthy_non_dict_hits_guard_lines(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text("[1]\n", encoding="utf-8")
    svc = QuoteSetupService(config_path=str(cfg))
    data, existed = svc._load_yaml()
    assert existed is True and data == {}

    conf = tmp_path / "config"
    conf.mkdir()
    (conf / "config.example.yaml").write_text("[1]\n", encoding="utf-8")
    svc2 = QuoteSetupService(config_path=str(conf / "config.yaml"))
    data2, existed2 = svc2._load_yaml()
    assert existed2 is False and data2 == {}


def test_normalize_markup_rules_can_restore_default_branch(monkeypatch) -> None:
    real_normalize = qp.normalize_courier_name

    def _spy_normalize(name: str):
        frame = inspect.currentframe()
        assert frame is not None and frame.f_back is not None
        caller_locals = frame.f_back.f_locals
        rules = caller_locals.get("rules")
        if isinstance(rules, dict):
            rules.pop("default", None)
        return real_normalize(name)

    monkeypatch.setattr(qp, "normalize_courier_name", _spy_normalize)
    rules = _normalize_markup_rules({"圆通快递": {"normal_first_add": 1.5}})
    assert "default" in rules


def test_parse_cost_api_response_payload_not_dict_guard(monkeypatch) -> None:
    sentinel = "NON_DICT_SENTINEL"
    calls = {"sentinel_dict_checks": 0}

    def _fake_isinstance(obj, typ):
        if typ is dict and obj == sentinel:
            calls["sentinel_dict_checks"] += 1
            # First check (line 421): pretend dict to set payload=sentinel.
            # Second check (line 427): return False so payload resets to {}.
            return calls["sentinel_dict_checks"] == 1
        return builtins.isinstance(obj, typ)

    monkeypatch.setattr(qp, "isinstance", _fake_isinstance, raising=False)
    parsed = _parse_cost_api_response({"data": sentinel})
    assert parsed["provider"] is None

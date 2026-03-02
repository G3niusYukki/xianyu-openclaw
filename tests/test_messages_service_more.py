from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.modules.messages.service import MessagesService


@pytest.fixture
def cfg(monkeypatch, tmp_path):
    c = SimpleNamespace(
        browser={"delay": {"min": 0.0, "max": 0.0}},
        accounts=[{"enabled": True, "cookie": "acc_cookie=v"}],
    )

    def get_section(name, default=None):
        if name == "messages":
            return {}
        if name == "quote":
            return {}
        if name == "content":
            return {"templates": {"path": str(tmp_path)}}
        return default or {}

    c.get_section = get_section
    monkeypatch.setattr("src.modules.messages.service.get_config", lambda: c)
    monkeypatch.setattr("src.modules.messages.service.get_compliance_guard", lambda: object())


def test_transport_mode_and_safe_float(cfg):
    assert MessagesService._normalized_transport_mode("X") == "ws"
    assert MessagesService._safe_float("1.2") == 1.2
    assert MessagesService._safe_float(None) == 0.0


def test_load_templates_and_select(cfg, tmp_path):
    p = tmp_path / "reply_templates.json"
    p.write_text(json.dumps({"weight_template": "W", "volume_template": "V"}), encoding="utf-8")

    s = MessagesService(controller=None, config={})
    tpl = s._load_reply_templates()
    assert tpl["weight_template"] == "W"
    assert s._select_quote_reply_template({"actual_weight_kg": 1, "billing_weight_kg": 2}) == "V"
    assert s._select_quote_reply_template({"actual_weight_kg": 2, "billing_weight_kg": 2}) == "W"


def test_resolve_ws_cookie_fallbacks(monkeypatch, cfg):
    s = MessagesService(controller=None, config={"cookie": "cfg_cookie=v"})
    monkeypatch.delenv("XIANYU_COOKIE_1", raising=False)
    assert s._resolve_ws_cookie() == "cfg_cookie=v"

    monkeypatch.setenv("XIANYU_COOKIE_1", "env_cookie=v")
    assert s._resolve_ws_cookie() == "env_cookie=v"

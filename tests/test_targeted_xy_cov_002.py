from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.dashboard_server import _extract_json_payload, _safe_int
from src.modules.messages.service import MessagesService
from src.modules.quote.models import QuoteRequest


@pytest.fixture
def cfg(monkeypatch, tmp_path):
    c = SimpleNamespace(
        browser={"delay": {"min": 0.0, "max": 0.0}},
        accounts=[{"enabled": False, "cookie": ""}],
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
    return tmp_path


def test_dashboard_helpers_cover_edge_branches() -> None:
    assert _safe_int(None, default=7, min_value=1, max_value=9) == 7

    text = "prefix {bad json} middle [1, 2, 3] suffix"
    assert _extract_json_payload(text) == [1, 2, 3]


def test_messages_load_templates_missing_stat_error_and_bad_json(cfg, monkeypatch) -> None:
    s = MessagesService(controller=None, config={})

    # file missing -> direct cache path
    s._reply_templates_path = cfg / "not_exists" / "reply_templates.json"
    tpl = s._load_reply_templates()
    assert "weight_template" in tpl

    # parse warning path
    bad_json = cfg / "bad_json.json"
    bad_json.write_text("{not-json}", encoding="utf-8")
    s._reply_templates_path = bad_json
    warned: list[str] = []
    monkeypatch.setattr(s.logger, "warning", lambda *args, **kwargs: warned.append(str(args[0]) if args else ""))
    s._reply_templates_mtime = -999
    s._load_reply_templates()
    assert warned


def test_messages_quote_candidate_and_eta_error_paths(cfg) -> None:
    s = MessagesService(controller=None, config={})

    class Repo:
        def find_candidates(self, **_kwargs):
            raise RuntimeError("repo down")

    s.quote_engine = SimpleNamespace(cost_table_provider=SimpleNamespace(repo=Repo()))
    s.logger.warning = lambda *args, **kwargs: None
    req = QuoteRequest(origin="A", destination="B", weight=1.0)
    assert s._resolve_quote_candidate_couriers(req) == []

    assert MessagesService._format_eta_days("oops") == "1天"
    assert MessagesService._format_eta_days(2160) == "1.5天"


@pytest.mark.asyncio
async def test_messages_quote_all_couriers_empty(cfg) -> None:
    s = MessagesService(controller=None, config={})
    s._resolve_quote_candidate_couriers = lambda _r: []
    rows = await s._quote_all_couriers(QuoteRequest(origin="A", destination="B", weight=1.0))
    assert rows == []

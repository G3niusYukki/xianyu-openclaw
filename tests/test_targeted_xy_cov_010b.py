from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import src.dashboard_server as ds
from src.modules.messages.service import MessagesService
from src.modules.messages.ws_live import MessagePackDecoder, decode_sync_payload, extract_chat_event
from src.modules.quote.cost_table import CostRecord, CostTableRepository, normalize_courier_name, region_of_location


@pytest.fixture
def msg_service(monkeypatch, tmp_path: Path):
    cfg = SimpleNamespace(
        browser={"delay": {"min": 0.0, "max": 0.0}},
        accounts=[{"enabled": True, "cookie": "acc_cookie=v"}],
    )

    def get_section(name, default=None):
        if name == "messages":
            return {"transport": "auto", "ws": {}}
        if name == "quote":
            return {}
        if name == "content":
            return {"templates": {"path": str(tmp_path)}}
        return default or {}

    cfg.get_section = get_section
    monkeypatch.setattr("src.modules.messages.service.get_config", lambda: cfg)
    monkeypatch.setattr("src.modules.messages.service.get_compliance_guard", lambda: object())
    return MessagesService(controller=None, config={})


@pytest.mark.asyncio
async def test_messages_get_unread_sessions_ws_not_ready_paths(msg_service: MessagesService):
    class T:
        def __init__(self):
            self.called = 0

        async def get_unread_sessions(self, limit=20):
            self.called += 1
            return []

        def is_ready(self):
            raise RuntimeError("boom")

    t = T()
    msg_service._ws_transport = t
    msg_service.transport_mode = "ws"
    out = await msg_service.get_unread_sessions(limit=1)
    assert out == []
    assert t.called == 1


def test_messages_template_and_trigger_edge_paths(msg_service: MessagesService, monkeypatch):
    class BadStatPath:
        def exists(self):
            return True

        def stat(self):
            raise OSError("x")

    monkeypatch.setattr(msg_service, "_reply_templates_path", BadStatPath())
    got = msg_service._load_reply_templates()
    assert "weight_template" in got

    assert msg_service._compose_multi_courier_quote_reply([]) == ""
    assert msg_service._is_standard_format_trigger("") is False


def test_ws_live_decode_and_extract_guard_paths(monkeypatch):
    with pytest.raises(ValueError):
        MessagePackDecoder(b"").decode()
    with pytest.raises(ValueError):
        MessagePackDecoder(b"\xc4\x02a").decode()

    monkeypatch.setattr("src.modules.messages.ws_live.base64.b64decode", lambda _t: (_ for _ in ()).throw(ValueError("x")))
    monkeypatch.setattr(
        "src.modules.messages.ws_live.base64.urlsafe_b64decode", lambda _t: (_ for _ in ()).throw(ValueError("y"))
    )
    assert decode_sync_payload("ab") is None

    evt = extract_chat_event(
        {
            "1": {
                "2": "chat_9@goofish",
                "5": "not-int",
                "10": {"content": "hi", "fromUserId": "u9", "senderNick": "n9"},
            }
        }
    )
    assert evt is not None
    assert evt["chat_id"] == "chat_9"


def test_cost_table_controlled_branches(tmp_path: Path):
    assert normalize_courier_name("  ") == ""
    assert normalize_courier_name("京东") == "京东"
    assert normalize_courier_name("圆通速递") == "圆通"
    assert region_of_location(None) == ""

    repo = CostTableRepository(table_dir=tmp_path)
    row = CostRecord(courier="圆通", origin="杭州西湖", destination="广州天河", first_cost=2.0, extra_cost=1.0)
    repo._records = [row]
    repo._reload_if_needed = lambda: None
    # 直接构造精确索引，避免依赖 fuzzy 行为波动
    repo._index_route = {("杭州西湖", "广州天河"): [row]}
    repo._index_courier_route = {("圆通", "杭州西湖", "广州天河"): [row]}
    repo._index_destination = {"广州天河": [row]}
    repo._index_courier_destination = {("圆通", "广州天河"): [row]}

    got = repo.find_candidates("杭州西湖", "广州天河", courier=None, limit=3)
    assert got and got[0].courier == "圆通"


def test_dashboard_helpers_more_paths():
    assert ds._safe_int("x", default=7, min_value=1, max_value=10) == 7
    assert ds._safe_int("99", default=7, min_value=1, max_value=10) == 10
    assert ds._extract_json_payload("prefix {\"a\": 1} suffix") == {"a": 1}
    assert ds._extract_json_payload("xx") is None

    async def _coro():
        return "ok"

    assert ds._run_async(_coro()) == "ok"

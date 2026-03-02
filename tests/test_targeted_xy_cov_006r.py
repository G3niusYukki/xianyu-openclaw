from __future__ import annotations

import zipfile
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET
import time

import pytest

from src.modules.messages.service import MessagesService
from src.modules.quote.cost_table import CostRecord, CostTableRepository


class _Guard:
    def __init__(self, blocked: bool = False):
        self._blocked = blocked

    def evaluate_content(self, _text: str) -> dict:
        return {"blocked": self._blocked}


@pytest.fixture
def msg_service(monkeypatch, tmp_path):
    cfg = SimpleNamespace(
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

    cfg.get_section = get_section
    monkeypatch.setattr("src.modules.messages.service.get_config", lambda: cfg)
    monkeypatch.setattr("src.modules.messages.service.get_compliance_guard", lambda: _Guard(False))
    return MessagesService(controller=None, config={})


def test_messages_pure_extract_and_boundaries(msg_service: MessagesService):
    assert MessagesService._extract_weight_kg("2斤") == 1.0
    assert MessagesService._extract_weight_kg("500g") == 0.5
    assert MessagesService._extract_weight_kg("") is None

    assert MessagesService._extract_volume_cm3("10x20x30") == 6000.0
    assert MessagesService._extract_volume_cm3("0x10x10") is None

    assert MessagesService._extract_volume_weight_kg("体积重: 3斤") == 1.5
    assert MessagesService._extract_volume_weight_kg("材积重: 600g") == 0.6

    assert msg_service._is_quote_request("到货 2kg") is False
    assert msg_service._is_quote_request("从杭州寄到广州 2kg") is True


def test_messages_context_and_exception_fallback_paths(msg_service: MessagesService):
    msg_service._quote_context_memory["s1"] = {
        "pending_missing_fields": ["origin"],
        "destination": "广州",
        "weight": "abc",
        "updated_at": time.time(),
    }
    req, missing, fields, hit = msg_service._build_quote_request_with_context("杭州", session_id="s1")
    assert req is None
    assert "weight" in missing
    assert fields["origin"] == "杭州"
    assert hit is True

    msg_service.courier_lock_template = "{bad"
    reply, matched = msg_service._build_courier_lock_reply(
        {
            "courier_choice": "圆通",
            "last_quote_rows": [{"courier": "圆通", "total_fee": "oops", "eta_days": "2天"}],
        }
    )
    assert "已为你锁定 圆通" in reply
    assert matched is True


def test_messages_empty_and_compliance(msg_service: MessagesService, monkeypatch):
    assert "请先按格式发送" in msg_service._build_available_couriers_hint({"last_quote_rows": [{"courier": ""}]})
    assert msg_service._detect_courier_choice("  圆通  ") == "圆通"

    assert msg_service._sanitize_reply("加微信聊") == msg_service.safe_fallback_reply

    monkeypatch.setattr(msg_service, "compliance_guard", _Guard(True))
    assert msg_service._sanitize_reply("正常文本") == msg_service.safe_fallback_reply


def test_cost_table_helpers_and_empty_input(tmp_path: Path):
    repo = CostTableRepository(table_dir=tmp_path)

    mapped = repo._resolve_header_map(["快递公司", "始发地", "目的地", "首重1KG费用", "续重1KG费用"])
    assert {"courier", "origin", "destination", "first_cost", "extra_cost"}.issubset(mapped)

    assert repo._cell_text(["a"], 9) == ""
    assert repo._cell_float(["a"], 9) is None
    assert repo._to_float("￥1,234.56") == 1234.56
    assert repo._to_float(None) is None

    assert repo._origin_similarity("", "浙江") == 0
    assert repo._origin_similarity("浙江", "杭州市") == 2


def test_cost_table_xlsx_xml_edge_paths(tmp_path: Path):
    repo = CostTableRepository(table_dir=tmp_path)

    zpath = tmp_path / "bad.xlsx"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("dummy.txt", "x")
    with zipfile.ZipFile(zpath) as zf:
        assert repo._read_sheet_paths(zf) == []
        assert repo._read_shared_strings(zf) == []

    cell_s_bad = ET.fromstring('<c xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" t="s"><v>not-int</v></c>')
    assert repo._read_cell_value(cell_s_bad, ["x"]) == ""

    cell_s_idx = ET.fromstring('<c xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" t="s"><v>5</v></c>')
    assert repo._read_cell_value(cell_s_idx, ["x"]) == ""

    cell_v = ET.fromstring('<c xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><v>42</v></c>')
    assert repo._read_cell_value(cell_v, []) == "42"

    assert repo._excel_col_to_index("aa") == 27


def test_cost_table_find_candidates_destination_similarity_fallback(tmp_path: Path):
    repo = CostTableRepository(table_dir=tmp_path)
    row = CostRecord(courier="圆通", origin="浙江", destination="广东", first_cost=2.0, extra_cost=1.0)
    repo._records = [row]
    repo._index_destination = {"广东": [row]}
    repo._index_courier_destination = {("圆通", "广东"): [row]}

    # 触发 destination 索引 + origin 相似度兜底
    rows = repo.find_candidates("杭州", "广州", courier="圆通", limit=5)
    assert rows and rows[0].courier == "圆通"

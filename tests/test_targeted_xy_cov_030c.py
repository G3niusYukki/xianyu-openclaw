from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest

from src.modules.operations.service import OperationsService
from src.modules.quote.cost_table import CostRecord, CostTableRepository, normalize_location_name


@pytest.mark.asyncio
async def test_operations_polish_listing_returns_disabled() -> None:
    svc = OperationsService(controller=None)
    result = await svc.polish_listing("pid-1")

    assert result["success"] is False
    assert result["action"] == "polish"
    assert result["product_id"] == "pid-1"
    assert result["error"] == "feature_disabled"
    assert "擦亮功能已停用" in result["message"]


@pytest.mark.asyncio
async def test_operations_batch_polish_returns_disabled_status() -> None:
    svc = OperationsService(controller=None, analytics=None)

    summary = await svc.batch_polish(product_ids=["a", "b"], max_items=2)

    assert summary == {
        "success": 0,
        "failed": 0,
        "total": 0,
        "action": "batch_polish",
        "blocked": True,
        "message": "擦亮功能已停用：闲鱼平台已限制擦亮效果",
        "details": [],
    }


def test_cost_table_normalize_location_via_geo_alias(monkeypatch) -> None:
    monkeypatch.setattr("src.modules.quote.cost_table.GeoResolver.normalize", staticmethod(lambda _x: "北京市"))
    assert normalize_location_name("  beijing-any  ") == "北京"


def test_cost_table_read_cell_value_out_of_range_and_invalid_index() -> None:
    c_out = ET.fromstring(
        '<c xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" t="s"><v>3</v></c>'
    )
    c_bad = ET.fromstring(
        '<c xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" t="s"><v>NaN</v></c>'
    )

    assert CostTableRepository._read_cell_value(c_out, ["only0"]) == ""
    assert CostTableRepository._read_cell_value(c_bad, ["only0"]) == ""


def test_cost_table_find_candidates_courier_destination_fallback_with_region(monkeypatch, tmp_path) -> None:
    repo = CostTableRepository(table_dir=tmp_path)
    record = CostRecord(courier="圆通", origin="浙江", destination="上海", first_cost=4, extra_cost=1)
    repo._records = [record]
    repo._index_courier_destination = {("圆通", "上海"): [record]}
    repo._index_destination = {"上海": [record]}

    monkeypatch.setattr(repo, "_reload_if_needed", lambda: None)
    monkeypatch.setattr("src.modules.quote.cost_table.route_candidates", lambda *_a, **_k: [("杭州", "上海")])
    monkeypatch.setattr("src.modules.quote.cost_table.contains_match", lambda *_a, **_k: False)
    monkeypatch.setattr(
        "src.modules.quote.cost_table.region_of_location",
        lambda value, resolver=None: "浙江" if "杭州" in str(value) or str(value) == "浙江" else "",
    )

    got = repo.find_candidates("杭州西湖", "上海浦东", courier="圆通", limit=5)

    assert len(got) == 1
    assert got[0] is record
    assert got[0].origin == "浙江" and got[0].destination == "上海"

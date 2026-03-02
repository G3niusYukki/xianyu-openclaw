from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.error_handler import BrowserError
from src.modules.operations.service import OperationsService
import src.modules.quote.cost_table as ct
from src.modules.quote.cost_table import CostRecord, CostTableRepository


@pytest.mark.asyncio
async def test_operations_controller_guard_branches_raise() -> None:
    svc = OperationsService(controller=None)

    with pytest.raises(BrowserError, match="Cannot polish listing"):
        await svc.polish_listing("p1")
    with pytest.raises(BrowserError, match="Cannot update price"):
        await svc.update_price("p1", 9.9)
    with pytest.raises(BrowserError, match="Cannot delist"):
        await svc.delist("p1")
    with pytest.raises(BrowserError, match="Cannot relist"):
        await svc.relist("p1")


@pytest.mark.asyncio
async def test_operations_batch_update_price_exception_and_delay(monkeypatch) -> None:
    analytics = SimpleNamespace(log_operation=AsyncMock())
    svc = OperationsService(controller=object(), analytics=analytics)

    async def fake_update(pid, _new, _old=None):
        if pid == "bad":
            raise RuntimeError("boom")
        return {"success": True, "product_id": pid, "action": "price_update"}

    sleep = AsyncMock()
    monkeypatch.setattr(svc, "update_price", fake_update)
    monkeypatch.setattr("src.modules.operations.service.asyncio.sleep", sleep)
    monkeypatch.setattr("src.modules.operations.service.random.uniform", lambda a, b: 1.25)

    summary = await svc.batch_update_price(
        [{"product_id": "bad", "new_price": 1}, {"product_id": "ok", "new_price": 2}], delay_range=(1, 2)
    )

    assert summary["total"] == 2
    assert summary["success"] == 1
    assert summary["failed"] == 1
    assert summary["details"][0]["success"] is False
    assert summary["details"][0]["error"] == "boom"
    assert summary["details"][1]["success"] is True
    sleep.assert_awaited_once_with(1.25)
    analytics.log_operation.assert_awaited_once()


def test_cost_table_targeted_missing_branches(monkeypatch, tmp_path) -> None:
    monkeypatch.setitem(ct.COURIER_ALIASES, "AbC", "X")
    assert ct.normalize_courier_name("AbC") == "X"

    repo = CostTableRepository(table_dir=tmp_path)
    record = CostRecord(courier="圆通", origin="杭州", destination="上海", first_cost=3.0, extra_cost=1.0)
    repo._records = [record]
    repo._index_destination = {"d1": [record], "d2": [record]}
    monkeypatch.setattr(repo, "_reload_if_needed", lambda: None)
    monkeypatch.setattr(ct, "route_candidates", lambda *_a, **_k: [("o", "d1"), ("o", "d2")])

    calls = {"n": 0}

    def fake_rank(_pool, _origin):
        calls["n"] += 1
        return [] if calls["n"] == 1 else [record]

    monkeypatch.setattr(repo, "_rank_by_origin_similarity", fake_rank)
    monkeypatch.setattr(ct, "region_of_location", lambda *_a, **_k: "")

    out = repo.find_candidates("o", "d", courier=None, limit=3)
    assert out == [record]
    assert calls["n"] == 2


def test_cost_table_reload_unknown_suffix_and_decode_fallback(monkeypatch, tmp_path) -> None:
    repo = CostTableRepository(table_dir=tmp_path, include_patterns=["*"])
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    (tmp_path / "b.csv").write_text("快递公司,始发地,目的地,首重,续重\n圆通,杭州,上海,5,1\n", encoding="utf-8")

    csv_called = {"n": 0}

    def fake_load_csv(path):
        csv_called["n"] += 1
        assert path.suffix == ".csv"
        return []

    xlsx_called = {"n": 0}

    def fake_load_xlsx(_path):
        xlsx_called["n"] += 1
        return []

    monkeypatch.setattr(repo, "_load_csv", fake_load_csv)
    monkeypatch.setattr(repo, "_load_xlsx", fake_load_xlsx)
    monkeypatch.setattr(repo, "_rebuild_indexes", lambda _records: None)

    repo._reload_if_needed()
    assert csv_called["n"] == 1
    assert xlsx_called["n"] == 0

    class _BadBytes:
        def decode(self, _encoding):
            raise UnicodeDecodeError("x", b"", 0, 1, "bad")

    class _BadPath:
        def read_bytes(self):
            return _BadBytes()

    assert CostTableRepository._read_text_file(_BadPath()) == ""


def test_cost_table_origin_similarity_sheet_paths_and_excel_lowercase(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(ct, "region_of_location", lambda *_a, **_k: "浙江")
    assert CostTableRepository._origin_similarity("杭州东", "杭州西") == 1

    xlsx = tmp_path / "wb.xlsx"
    import zipfile

    with zipfile.ZipFile(xlsx, "w") as zf:
        zf.writestr(
            "xl/workbook.xml",
            """
            <workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">
              <sheets>
                <sheet name=\"S1\" r:id=\"rId1\"/>
                <sheet name=\"S2\" r:id=\"rId2\"/>
              </sheets>
            </workbook>
            """,
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            """
            <Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">
              <Relationship Id=\"rId2\" Type=\"x\" Target=\"worksheets/sheet2.xml\"/>
            </Relationships>
            """,
        )

    repo = CostTableRepository(table_dir=tmp_path)
    with zipfile.ZipFile(xlsx) as zf:
        assert repo._read_sheet_paths(zf) == [("S2", "xl/worksheets/sheet2.xml")]

    assert CostTableRepository._excel_col_to_index("aZ") == 52

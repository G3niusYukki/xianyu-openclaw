from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from src.modules.analytics.report_generator import ReportFormatter, ReportGenerator
from src.modules.analytics.service import AnalyticsService, DateRange
from src.modules.compliance.center import ComplianceCenter, ComplianceDecision
from src.modules.content import service as content_service_module
from src.modules.content.service import ContentService
from src.modules.followup.service import FollowUpEngine
from src.modules.growth.service import GrowthService
from src.modules.listing.models import Listing
from src.modules.listing.service import ListingService
from src.modules.media.service import MediaService
from src.modules.operations.service import OperationsService
from src.modules.orders.service import OrderFulfillmentService


class DummyController:
    def __init__(self):
        self.calls = []
        self._click_results = []
        self._scripts = []

    def set_click_results(self, values):
        self._click_results = list(values)

    def set_script_results(self, values):
        self._scripts = list(values)

    async def new_page(self):
        return "p1"

    async def navigate(self, page_id, url):
        self.calls.append(("navigate", page_id, url))

    async def click(self, page_id, selector):
        self.calls.append(("click", selector))
        if self._click_results:
            return self._click_results.pop(0)
        return True

    async def close_page(self, page_id):
        self.calls.append(("close", page_id))

    async def find_elements(self, page_id, selector):
        return [object(), object()]

    async def execute_script(self, page_id, script):
        self.calls.append(("script", script))
        if self._scripts:
            return self._scripts.pop(0)
        return []

    async def type_text(self, page_id, selector, text):
        self.calls.append(("type", selector, text))
        return True

    async def upload_files(self, page_id, selector, image_paths):
        self.calls.append(("upload", selector, tuple(image_paths)))

    async def get_text(self, page_id, selector):
        return "title"


@pytest.mark.asyncio
async def test_operations_missing_branches(monkeypatch):
    async def _no_sleep(*_a, **_k):
        return None

    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    c = DummyController()
    svc = OperationsService(controller=c)

    with pytest.raises(Exception):
        await OperationsService(controller=None).refresh_inventory()

    c.set_click_results([True, True])
    out = await svc.delist("p1", confirm=True)
    assert out["success"] is True

    c.set_click_results([False])
    out2 = await svc.relist("p2")
    assert out2["success"] is False

    c.set_script_results([["id1", "id2"], None])
    ids = await svc._extract_product_ids("p1", limit=1)
    assert ids == ["id1"]
    fallback = await svc._extract_product_ids("p1", limit=2)
    assert fallback == ["unknown_1", "unknown_2"]

    c.set_click_results([True, True])
    summary = await svc.batch_polish(product_ids=["a", "b"], max_items=1)
    assert summary["action"] == "batch_polish"
    assert "total" in summary


@pytest.mark.asyncio
async def test_listing_missing_branches(monkeypatch):
    async def _no_sleep(*_a, **_k):
        return None

    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    c = DummyController()
    svc = ListingService(controller=c)

    lst = Listing(title="t", description="d", price=1.0, images=[], tags=["unknown"])

    failed = await ListingService(controller=None).create_listing(lst)
    assert failed.success is False

    await svc._step_upload_images("p", [])

    async def _none(*_a, **_k):
        return []

    c.find_elements = _none
    await svc._step_upload_images("p", [" "])

    async def _some(*_a, **_k):
        return [object()]

    c.find_elements = _some
    await svc._step_upload_images("p", ["/a.jpg", " "])

    async def _false(*_a, **_k):
        return False

    c.type_text = _false
    await svc._step_fill_title("p", "title")
    await svc._step_fill_description("p", "desc")
    await svc._step_set_price("p", 9.9)

    svc._click_text_option = _false
    await svc._step_select_condition("p", ["no-match"])
    with pytest.raises(Exception):
        await ListingService(controller=None).get_my_listings()


def test_media_missing_branches(tmp_path, monkeypatch):
    img_path = tmp_path / "a.png"
    Image.new("RGBA", (20, 20), (0, 0, 0, 0)).save(img_path)

    svc = MediaService(
        config={
            "supported_formats": ["png", "jpg"],
            "max_width": 10,
            "max_height": 10,
            "watermark": {"enabled": True, "text": "wm", "color": "#FFFFFF", "font_size": 12},
        }
    )

    out = svc.resize_image_for_xianyu(str(img_path), None)
    assert out == str(img_path)

    def boom(*_a, **_k):
        raise OSError("font")

    monkeypatch.setattr("src.modules.media.service.ImageFont.truetype", boom)
    wm = svc.add_watermark(str(img_path), position="center")
    assert wm == str(img_path)

    bad = tmp_path / "bad.txt"
    bad.write_text("x", encoding="utf-8")
    ok, msg = svc.validate_image(str(bad))
    assert ok is False and "不支持" in msg

    svc2 = MediaService(config={"supported_formats": ["png"], "watermark": {"enabled": False}})
    processed = svc2.batch_process_images([str(tmp_path / "missing.png")])
    assert processed == []


def test_content_missing_branches(monkeypatch):
    monkeypatch.setattr(content_service_module, "OpenAI", lambda **_k: (_ for _ in ()).throw(RuntimeError("x")))
    svc = ContentService(config={"api_key": "k", "usage_mode": "always", "task_switches": {}, "cache_max_entries": 1})
    assert svc.client is None
    assert ContentService._normalize_config_value("${AI_KEY}") is None

    svc.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **_k: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])
            )
        )
    )
    assert svc._should_call_ai("x", "a" * 400) is True
    assert svc._call_ai("p", task="title") == "ok"
    assert svc._call_ai("p", task="title") == "ok"

    svc._response_cache = {}
    svc._cache_set("a", "t", "1")
    svc._cache_set("b", "t", "2")
    assert len(svc._response_cache) == 1


@pytest.mark.asyncio
async def test_analytics_and_report_missing(tmp_path):
    import aiosqlite

    db = tmp_path / "a.db"
    svc = AnalyticsService(config={"path": str(db)})

    dr = DateRange(datetime(2024, 1, 1), None)
    assert dr.end_date >= dr.start_date

    await svc._init_db()

    conn = await aiosqlite.connect(str(db))
    try:
        assert await svc._fetchone(conn, "SELECT 1 WHERE 0") == ()
    finally:
        await conn.close()

    await svc.log_operation("PUBLISH", "pid", details={"x": 1})
    await svc.add_product("p", "t", 9, "c", "a")
    await svc.update_product_status("p", "active")
    logs = await svc.get_operation_logs(operation_type="PUBLISH", start_date=datetime(2000, 1, 1), end_date=datetime(2999, 1, 1))
    assert logs

    m = await svc.get_monthly_report(year=2024, month=12)
    assert m["period"]["month"] == 12

    fp = await svc.export_data(data_type="metrics", format="json")
    assert Path(fp).exists()

    rg = ReportGenerator()
    rg.analytics = svc
    summary = rg._generate_summary({"new_listings": 1, "polished_count": 1, "total_views": 1, "total_wants": 101, "total_sales": 1})
    assert "擦亮了" in summary
    weekly = rg._generate_weekly_insights({"summary": {"total_wants": 101, "new_listings": 1, "polished_count": 1}})
    assert weekly["highlights"]
    monthly = rg._generate_monthly_insights({"summary": {"total_revenue": 1200, "total_sold": 11}, "top_categories": [{"category": "数码"}]})
    assert len(monthly["highlights"]) >= 3
    md = ReportFormatter.to_markdown({"report_type": "daily", "period": {"date": "2024-01-01"}})
    assert "**Date:**" in md


def test_orders_growth_compliance_lines(tmp_path):
    orders = OrderFulfillmentService(db_path=str(tmp_path / "o.db"))
    assert orders.map_status("cancel now") == "closed"
    assert orders.map_status("mystery") == "processing"
    with pytest.raises(ValueError):
        orders.deliver("missing")
    with pytest.raises(ValueError):
        orders.create_after_sales_case("missing")
    with pytest.raises(ValueError):
        orders.record_after_sales_followup(order_id="missing", issue_type="d", reply_text="x", sent=False, dry_run=True)
    with pytest.raises(ValueError):
        orders.trace_order("missing")

    growth = GrowthService(db_path=str(tmp_path / "g.db"))
    assert growth.rollback_to_baseline("none") is None
    assert growth._z_test(1, 0, 0, 0) == 1.0

    policy = tmp_path / "policy.yaml"
    policy.write_text("global: {whitelist: [safe]}\n", encoding="utf-8")
    cc = ComplianceCenter(policy_path=str(policy), db_path=str(tmp_path / "c.db"))
    d = cc.evaluate_before_send("safe channel")
    assert isinstance(d, ComplianceDecision)
    assert d.to_dict()["allowed"] is True
    assert cc.replay(limit=1)


def test_followup_get_touch_stats(tmp_path):
    e = FollowUpEngine(db_path=str(tmp_path / "f.db"))
    c = e.record_trigger("s", "a", "followup", "t", "sent", {})
    assert c == 1
    daily, last = e._get_touch_stats("s")
    assert daily >= 1 and last > 0


@pytest.mark.asyncio
async def test_analytics_export_else_and_empty_csv_branch(tmp_path):
    svc = AnalyticsService(config={"path": str(tmp_path / "ana.db")})
    svc._allowed_export_types = {"custom"}
    fp = await svc.export_data(data_type="custom", format="csv", filepath=str(tmp_path / "x.csv"))
    assert fp.endswith("x.csv")
    assert Path(fp).exists() is False or Path(fp).read_text(encoding="utf-8", errors="ignore") == ""

# ISSUES FOUND:
# - dashboard_server.py 覆盖缺口极大（~589行），本轮先补齐聚焦子模块与analytics分支，dashboard需继续拆分专测。

import types

import pytest

from src.modules.accounts.monitor import Monitor
from src.modules.accounts.scheduler import Scheduler, Task, TaskStatus, TaskType
from src.modules.analytics.report_generator import ReportFormatter, ReportGenerator
from src.modules.analytics.service import AnalyticsService
from src.modules.content.service import ContentService
from src.modules.listing.models import Listing
from src.modules.listing.service import ListingService
from src.modules.media.service import MediaService
from src.modules.operations.service import OperationsService


class _Obj:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class DummyController:
    def __init__(self, click_result=True):
        self.click_result = click_result
        self.closed = []

    async def new_page(self):
        return "p1"

    async def navigate(self, *_):
        return True

    async def click(self, *_):
        return self.click_result

    async def close_page(self, page_id):
        self.closed.append(page_id)

    async def find_elements(self, *_):
        return [1, 2, 3]

    async def execute_script(self, *_):
        return ["id1", "id2"]

    async def type_text(self, *_):
        return True

    async def upload_files(self, *_):
        return True

    async def get_text(self, *_):
        return "title"


@pytest.mark.asyncio
async def test_scheduler_execute_and_should_run_paths(monkeypatch, tmp_path):
    s = Scheduler()
    s.task_file = tmp_path / "tasks.json"

    t = Task(task_id="t1", task_type=TaskType.POLISH, interval=1)
    s.tasks[t.task_id] = t

    async def ok_polish(_):
        return {"success": True, "message": "ok"}

    monkeypatch.setattr(s, "_execute_polish", ok_polish)
    res = await s.execute_task(t)
    assert res["success"] is True
    assert t.status == TaskStatus.COMPLETED

    t2 = Task(task_id="t2", task_type="unknown")
    res2 = await s.execute_task(t2)
    assert "Unknown task type" in res2["message"]

    t3 = Task(task_id="t3", task_type=TaskType.PUBLISH)

    async def boom(_):
        raise RuntimeError("x")

    monkeypatch.setattr(s, "_execute_publish", boom)
    res3 = await s.execute_task(t3)
    assert res3["success"] is False and t3.status == TaskStatus.FAILED

    t4 = Task(task_id="t4", enabled=False)
    assert s._should_run(t4) is False
    t4.enabled = True
    s.running_tasks[t4.task_id] = object()
    assert s._should_run(t4) is False
    s.running_tasks.clear()
    assert s._should_run(t4) is True


@pytest.mark.asyncio
async def test_scheduler_publish_metrics_and_cron(monkeypatch):
    s = Scheduler()

    class DummyListing:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class DummyResult:
        def __init__(self, product_id, success):
            self.product_id = product_id
            self.success = success

    class DummyClient:
        async def disconnect(self):
            return None

    class DummyListingService:
        def __init__(self, controller=None):
            self.controller = controller

        async def batch_create_listings(self, listings):
            return [DummyResult("p1", True), DummyResult("p2", False)]

    async def mk_client():
        return DummyClient()

    monkeypatch.setattr("src.modules.accounts.scheduler.create_browser_client", mk_client)
    monkeypatch.setitem(__import__("sys").modules, "src.modules.listing.models", types.SimpleNamespace(Listing=DummyListing))
    monkeypatch.setitem(__import__("sys").modules, "src.modules.listing.service", types.SimpleNamespace(ListingService=DummyListingService))

    ok = await s._execute_publish({"listings": [{"title": "a"}]})
    assert ok["success"] is True and len(ok["details"]) == 2
    no = await s._execute_publish({"listings": []})
    assert no["success"] is False

    class DummyAnalytics:
        async def get_dashboard_stats(self):
            return {"x": 1}

    monkeypatch.setitem(__import__("sys").modules, "src.modules.analytics.service", types.SimpleNamespace(AnalyticsService=DummyAnalytics))
    mt = await s._execute_metrics({})
    assert mt["success"] is True and mt["stats"]["x"] == 1

    nxt = s._get_next_cron_run("* * * * *", __import__("datetime").datetime.now())
    assert nxt is not None


@pytest.mark.asyncio
async def test_monitor_paths(monkeypatch, tmp_path):
    m = Monitor(config={})
    m.alert_file = tmp_path / "alerts.json"

    seen = []

    async def cb(alert):
        seen.append(alert.alert_id)

    m.register_callback(cb)

    alert = await m.raise_alert("browser_connection", "t", "m", source="browser_connection", auto_resolve=False)
    assert alert.status == "active"

    async def quick_sleep(_):
        return None

    monkeypatch.setattr("src.modules.accounts.monitor.asyncio.sleep", quick_sleep)
    await m._auto_resolve_alert(alert)
    assert alert.status == "resolved"

    ok = await m.resolve_alert(alert.alert_id)
    assert ok is True
    bad = await m.resolve_alert("none")
    assert bad is False

    active = await m.get_active_alerts(level="error")
    assert isinstance(active, list)


@pytest.mark.asyncio
async def test_operations_listing_media_content_analytics(monkeypatch, tmp_path):
    monkeypatch.setattr("src.modules.operations.service.get_config", lambda: _Obj(browser={"delay": {"min": 0, "max": 0}}))

    async def no_sleep(*_):
        return None

    monkeypatch.setattr("src.modules.operations.service.asyncio.sleep", no_sleep)

    class Cmp:
        async def evaluate_batch_polish_rate(self, _):
            return {"blocked": False, "warn": False, "message": ""}

    monkeypatch.setattr("src.modules.operations.service.get_compliance_guard", lambda: Cmp())
    ops = OperationsService(controller=DummyController())
    rp = await ops.batch_polish(product_ids=["a", "b"], max_items=1)
    assert rp["total"] == 1
    err = ops._error_result("x", None, "e")
    assert err["success"] is False

    monkeypatch.setattr("src.modules.listing.service.get_config", lambda: _Obj(browser={"delay": {"min": 0, "max": 0}}))

    class LCmp:
        def evaluate_content(self, *_):
            return {"warn": False, "blocked": False, "message": "", "hits": []}

        async def evaluate_publish_rate(self, *_):
            return {"warn": False, "blocked": False, "message": ""}

    monkeypatch.setattr("src.modules.listing.service.get_compliance_guard", lambda: LCmp())
    svc = ListingService(controller=DummyController())
    listing = Listing(title="t", description="d", price=1.0, images=["a.jpg"], category="General", tags=["9成新"])

    async def fake_verify(*_):
        return "id", "https://x/success/id"

    monkeypatch.setattr(svc, "_step_verify_success", fake_verify)
    out = await svc.create_listing(listing)
    assert out.success is True
    assert svc._extract_product_id("https://a/b/c") == "c"

    media = MediaService(config={"watermark": {"enabled": False}, "supported_formats": ["jpg"], "max_image_size": 1})
    ok, msg = media.validate_image("/not_exists.jpg")
    assert ok is False and "不存在" in msg
    assert media._get_save_format("zzz") == "JPEG"

    c = ContentService(config={"api_key": None, "provider": "openai"})
    assert c._normalize_config_value("${X}") is None
    assert isinstance(c.get_ai_cost_stats(), dict)

    db = tmp_path / "a.db"
    an = AnalyticsService(config={"path": str(db), "timeout": 1})
    await an.log_operation("PUBLISH", "p1")
    await an.record_metrics("p1", views=1, wants=2, sales=0)
    await an.add_product("p1", "t", 10, "cat", "acc")
    await an.update_product_status("p1", "sold")
    await an.get_dashboard_stats()
    await an.get_daily_report()
    await an.get_weekly_report()
    await an.get_monthly_report(year=2025, month=1)
    await an.get_product_performance()
    await an.get_trend_data("views", 1)
    with pytest.raises(ValueError):
        await an.get_trend_data("bad", 1)
    await an.export_data("products", "json", str(tmp_path / "x.json"))
    with pytest.raises(ValueError):
        await an.export_data("bad", "json", str(tmp_path / "y.json"))
    await an.cleanup_old_data(0)

    rg = ReportGenerator()
    rg.analytics = an
    rep = await rg.generate_daily_report()
    assert rep["report_type"] == "daily"
    md = ReportFormatter.to_markdown({"report_type": "daily", "operations": {"a": 1}, "summary": {"b": 2}})
    slack = ReportFormatter.to_slack({"report_type": "daily", "summary": {"total_wants": 1, "total_views": 2, "total_sales": 3}})
    assert "Report" in md and "📊" in slack

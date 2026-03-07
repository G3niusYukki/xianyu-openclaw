import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.modules.accounts.monitor import HealthChecker, Monitor
from src.modules.accounts.scheduler import Scheduler, Task, TaskType
from src.modules.analytics.report_generator import ReportFormatter, ReportGenerator
from src.modules.analytics.service import AnalyticsService
from src.modules.analytics.visualization import ChartExporter, DataVisualizer
from src.modules.content.service import ContentService
from src.modules.listing.models import Listing, PublishResult
from src.modules.listing.service import ListingService
from src.modules.media.service import MediaService
from src.modules.operations.service import OperationsService


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch):
    async def _fast_sleep(_=0):
        return None

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)


@pytest.mark.asyncio
async def test_operations_service_branches(mock_controller):
    service = OperationsService(controller=mock_controller)
    service.analytics = Mock(log_operation=AsyncMock())

    res = await service.polish_listing("pid1")
    assert res["action"] == "polish"
    assert res["success"] is False
    assert res["error"] == "feature_disabled"

    summary = await service.batch_polish(max_items=2)
    assert summary["total"] == 0
    assert summary["blocked"] is True
    assert "擦亮功能已停用" in summary["message"]

    blocked = await service.batch_polish(max_items=2)
    assert blocked["blocked"] is True

    assert (await service.update_price("p", 9.9))["action"] == "price_update"
    assert (await service.batch_update_price([{"product_id": "p", "new_price": 1.0}]))["total"] == 1
    assert (await service.delist("p"))["action"] == "delist"
    assert (await service.relist("p"))["action"] == "relist"
    assert (await service.refresh_inventory())["success"] is False
    assert "error" in (await service.get_listing_stats())

    assert (await service.polish_listing("p"))["success"] is False


@pytest.mark.asyncio
async def test_listing_service_branches(mock_controller):
    svc = ListingService(controller=mock_controller)

    mock_api = Mock()
    mock_api.create_product = Mock(return_value=SimpleNamespace(
        ok=True,
        data={"xianyu_product_id": "abc"},
        error_message=None,
        error_code=None,
        to_dict=lambda: {"ok": True, "data": {"xianyu_product_id": "abc"}},
    ))
    mock_api.list_products = Mock(return_value=SimpleNamespace(
        ok=True,
        data={"list": [{"id": 1}, {"id": 2}, {"id": 3}]},
        error_message=None,
    ))
    svc._build_open_platform_client = Mock(return_value=mock_api)

    svc.compliance = Mock(
        evaluate_content=Mock(return_value={"warn": True, "blocked": False, "message": "w", "hits": ["x"]}),
        evaluate_publish_rate=AsyncMock(return_value={"warn": False, "blocked": False, "message": "ok"}),
    )
    svc.analytics = Mock(log_operation=AsyncMock())

    listing = Listing(title="t", description="d", price=10, category="General", images=["a.jpg"], tags=["99新"])
    out = await svc.create_listing(listing, account_id="a1")
    assert out.success is True
    assert out.product_id == "abc"

    svc.compliance.evaluate_content = Mock(return_value={"warn": False, "blocked": True, "message": "ban", "hits": []})
    blocked = await svc.create_listing(listing)
    assert blocked.success is False

    svc.compliance.evaluate_content = Mock(return_value={"warn": False, "blocked": False, "message": "ok", "hits": []})
    svc.compliance.evaluate_publish_rate = AsyncMock(return_value={"warn": True, "blocked": True, "message": "too fast"})
    rate_block = await svc.create_listing(listing)
    assert rate_block.success is False

    mock_controller.get_text = AsyncMock(return_value="name")
    assert (await svc.verify_listing("x"))["exists"] is True
    assert await svc.update_listing("x", {"price": 99}) is True
    assert await svc.delete_listing("x") is True
    assert len(await svc.get_my_listings(page=2)) == 3

    mock_controller.execute_script = AsyncMock(return_value=False)
    assert await svc._click_text_option("p", ".x", "k") is False
    assert svc._extract_product_id("bad-url")

    svc.create_listing = AsyncMock(side_effect=[PublishResult(success=True), RuntimeError("e")])
    lst = [listing, listing]
    results = await svc.batch_create_listings(lst)
    assert len(results) == 2 and results[1].success is False


def test_media_service_branches(temp_dir):
    img_path = temp_dir / "a.png"
    from PIL import Image

    Image.new("RGBA", (20, 10), (255, 0, 0, 128)).save(img_path)

    svc = MediaService(
        config={
            "supported_formats": ["jpg", "jpeg", "png", "webp"],
            "max_width": 10,
            "max_height": 10,
            "output_format": "JPEG",
            "output_quality": 80,
            "watermark": {"enabled": True, "text": "wm", "font_size": 10, "color": "#FFFFFF"},
            "max_image_size": 1024 * 1024,
        }
    )

    out = svc.resize_image_for_xianyu(str(img_path), str(temp_dir / "r.jpg"))
    assert Path(out).exists()
    wm = svc.add_watermark(out, position="center")
    assert Path(wm).exists()
    assert svc.compress_image(wm, str(temp_dir / "c.jpg"), quality=70)
    ok, _ = svc.validate_image(str(temp_dir / "c.jpg"))
    assert ok is True

    miss_ok, msg = svc.validate_image(str(temp_dir / "none.jpg"))
    assert miss_ok is False and "不存在" in msg
    bad = temp_dir / "x.txt"
    bad.write_text("x", encoding="utf-8")
    ok2, _ = svc.validate_image(str(bad))
    assert ok2 is False

    arr = svc.batch_process_images([str(temp_dir / "none.jpg"), str(img_path)], output_dir=str(temp_dir / "out"))
    assert len(arr) == 1


def test_content_service_branches():
    cfg = {
        "provider": "deepseek",
        "api_key": "k",
        "base_url": "https://x",
        "model": "m",
        "usage_mode": "minimal",
        "task_switches": {"title": True},
        "max_calls_per_run": 1,
        "cache_ttl_seconds": 60,
        "cache_max_entries": 1,
    }
    svc = ContentService(config=cfg)

    fake_resp = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok title"))])
    svc.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(return_value=fake_resp))))

    r1 = svc._call_ai("prompt", task="title")
    r2 = svc._call_ai("prompt", task="title")
    assert r1 == r2 == "ok title"
    assert svc._call_ai("another", task="title") is None

    svc.client = None
    assert "【转卖】" in svc.generate_title("iPhone", ["99新"], "General")
    assert "商品详情" in svc.generate_description("iPhone", "95新", "换新", ["tag"])

    reviewed = svc.review_before_publish("t", "d")
    assert "allowed" in reviewed and "mode" in reviewed
    assert svc.optimize_title("原始标题", "General") == "原始标题"
    assert len(svc.generate_seo_keywords("a", "General")) >= 1
    assert "title" in svc.generate_listing_content({"name": "a"})


@pytest.mark.asyncio
async def test_monitor_health_scheduler_and_analytics(temp_dir, monkeypatch: pytest.MonkeyPatch):
    mon = Monitor(config={})
    mon.alert_file = temp_dir / "alerts.json"
    cb = Mock()
    mon.register_callback(cb)
    mon.monitoring_rules["x"] = {"max_failures": 0, "window_minutes": 10, "level": "warning"}
    await mon.raise_alert("x", "T", "M", source="x", auto_resolve=False)
    await mon.check_condition("x", lambda _ctx: True, context={"k": 1})
    actives = await mon.get_active_alerts()
    assert len(actives) >= 1
    aid = actives[0].alert_id
    assert await mon.resolve_alert(aid) is True
    summary = await mon.get_alert_summary()
    assert summary["total_alerts"] >= 1
    assert await mon.cleanup_old_alerts(days=0) >= 0

    hc = HealthChecker()

    class _BC:
        async def connect(self):
            return False

    class _AS:
        def get_accounts(self):
            return [{"id": "a1"}]

        def validate_cookie(self, _):
            return False

    import src.modules.accounts.monitor as monitor_mod

    monkeypatch.setattr(monitor_mod, "BrowserClient", _BC, raising=False)
    monkeypatch.setattr(monitor_mod, "AccountsService", _AS, raising=False)

    res = await hc.run_health_check()
    assert res["checks"]["browser"]["status"] in {"healthy", "unhealthy"}

    sch = Scheduler()
    sch.task_file = temp_dir / "tasks.json"
    t = sch.create_task(TaskType.CUSTOM, name="x", interval=1)
    assert sch.get_task(t.task_id)
    assert sch.update_task(t.task_id, enabled=False) is True
    assert all(task.enabled for task in sch.list_tasks(enabled_only=True))
    assert sch._should_run(t) is False
    t.enabled = True
    t.last_run = datetime.now() - timedelta(seconds=10)
    t.interval = 1
    assert sch._should_run(t) is True
    assert sch.delete_task(t.task_id) is True

    t2 = Task(task_type=TaskType.CUSTOM, interval=1)
    sch.tasks[t2.task_id] = t2
    rr = await sch.execute_task(t2)
    assert rr["message"].startswith("Unknown")
    started = await sch.run_task_now(t2.task_id)
    assert started["success"] is True
    already = await sch.run_task_now(t2.task_id)
    assert already["success"] is False
    await sch.stop()

    db_path = temp_dir / "a.db"
    an = AnalyticsService(config={"path": str(db_path), "timeout": 30})
    await an.log_operation("PUBLISH", product_id="p1", details={"x": 1})
    await an.record_metrics("p1", views=10, wants=2, sales=1)
    await an.add_product("p1", "title", 10.0, category="数码")
    await an.update_product_status("p1", "sold")
    assert len(await an.get_operation_logs(limit=5)) >= 1
    assert isinstance(await an.get_dashboard_stats(), dict)
    assert isinstance(await an.get_daily_report(), dict)
    assert isinstance(await an.get_weekly_report(), dict)
    assert isinstance(await an.get_monthly_report(year=2025, month=1), dict)
    assert isinstance(await an.get_product_performance(days=30), list)
    assert isinstance(await an.get_trend_data(metric="views", days=3), list)
    with pytest.raises(ValueError):
        await an.get_trend_data(metric="bad", days=1)

    p_csv = await an.export_data("products", "csv", filepath=str(temp_dir / "x.csv"))
    p_json = await an.export_data("logs", "json", filepath=str(temp_dir / "x.json"))
    assert Path(p_csv).exists() and Path(p_json).exists()
    with pytest.raises(ValueError):
        await an.export_data("bad", "csv")
    with pytest.raises(ValueError):
        await an.export_data("products", "xml")
    cleaned = await an.cleanup_old_data(days=0)
    assert "logs_deleted" in cleaned

    rg = ReportGenerator()
    rg.analytics = an
    daily = await rg.generate_daily_report()
    weekly = await rg.generate_weekly_report()
    monthly = await rg.generate_monthly_report(2025, 1)
    product = await rg.generate_product_report("p1", 7)
    compare = await rg.generate_comparison_report(["p1"], 7)
    assert daily["report_type"] == "daily"
    assert weekly["report_type"] == "weekly"
    assert monthly["report_type"] == "monthly"
    assert product["report_type"] == "product"
    assert compare["report_type"] == "comparison"

    md = ReportFormatter.to_markdown({"report_type": "daily", "generated_at": "x", "operations": {"a": 1}, "summary": {"b": 2}})
    sk = ReportFormatter.to_slack({"report_type": "daily", "period": {"date": "2025-01-01"}, "summary": {"total_views": 1, "total_wants": 2, "total_sales": 3}})
    assert "# Daily Report" in md
    assert "📊" in sk

    vz = DataVisualizer()
    vz.analytics = an
    assert "No data" in vz.generate_bar_chart([], "k", "v")
    assert "No data" in vz.generate_bar_chart([{"x": 0}], "x", "x")
    assert "Need at least 2" in vz.generate_line_chart([{"a": 1}], "a", "a")
    assert "No variation" in vz.generate_line_chart([{"a": 1}, {"a": 1}], "a", "a")
    assert "📊" in (await vz.generate_metrics_dashboard())
    assert isinstance(await vz.generate_weekly_trend(weeks=1), str)

    rpath = await ChartExporter.export_report({"report_type": "daily", "summary": {"a": 1}}, format="markdown", filepath=str(temp_dir / "rep"))
    assert Path(rpath).exists()
    assert "每日运营摘要" in (await ChartExporter.export_daily_summary(format="text"))

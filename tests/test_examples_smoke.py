import sys
import types

import pytest


@pytest.mark.asyncio
async def test_examples_demo_module_smoke(monkeypatch, capsys):
    import examples.demo as demo

    class DummyResult:
        def __init__(self, success=True, error_message=None):
            self.success = success
            self.product_id = "pid-1"
            self.product_url = "https://example/pid-1"
            self.error_message = error_message

    class DummyListingService:
        async def create_listing(self, listing):
            return DummyResult(success=True, error_message="warn")

        async def batch_create_listings(self, listings):
            return [DummyResult(True), DummyResult(False)]

    class DummyContentService:
        def generate_title(self, **kwargs):
            return "title"

        def generate_description(self, **kwargs):
            return "desc" * 40

        def generate_seo_keywords(self, *args):
            return ["k1", "k2"]

    class DummyMediaService:
        def batch_process_images(self, images):
            return ["a.jpg", "b.jpg"]

    class DummyOperationsService:
        async def polish_listing(self, item_id):
            return {"success": True}

        async def batch_polish(self, max_items=10):
            return {"success": 3, "total": max_items}

        async def update_price(self, *args, **kwargs):
            return {"success": True, "old_price": 1, "new_price": 2}

    class DummyAnalyticsService:
        async def get_dashboard_stats(self):
            return {
                "total_operations": 1,
                "today_operations": 1,
                "total_products": 1,
                "active_products": 1,
            }

    class DummyAccountsService:
        def get_accounts(self):
            return [{"name": "n1", "id": "a1"}]

        def get_current_account(self):
            return {"name": "n1"}

    monkeypatch.setattr(demo, "get_config", lambda: object())
    monkeypatch.setattr(demo, "get_logger", lambda: object())
    monkeypatch.setattr(demo, "ListingService", DummyListingService)
    monkeypatch.setattr(demo, "ContentService", DummyContentService)
    monkeypatch.setattr(demo, "MediaService", DummyMediaService)
    monkeypatch.setattr(demo, "OperationsService", DummyOperationsService)
    monkeypatch.setattr(demo, "AnalyticsService", DummyAnalyticsService)
    monkeypatch.setattr(demo, "AccountsService", DummyAccountsService)

    await demo.demo_listing_creation()
    await demo.demo_batch_publish()
    await demo.demo_content_generation()
    await demo.demo_media_processing()
    await demo.demo_operations()
    await demo.demo_data_analytics()
    await demo.demo_accounts()
    await demo.main()

    out = capsys.readouterr().out
    assert "演示完成" in out


@pytest.mark.asyncio
async def test_examples_demo_browser_smoke(monkeypatch, capsys):
    import examples.demo_browser as mod

    class DummyController:
        async def connect(self):
            return True

        async def disconnect(self):
            return True

        async def new_page(self):
            return "p1"

        async def close_page(self, page_id):
            return True

        async def navigate(self, page_id, url):
            return True

        async def take_screenshot(self, page_id, path):
            return True

        async def execute_script(self, page_id, script):
            return "title"

        async def find_elements(self, page_id, selector):
            return [1, 2]

        async def find_element(self, page_id, selector):
            return object()

    class DummyListingService:
        def __init__(self, controller=None, analytics=None):
            pass

        async def create_listing(self, listing):
            return types.SimpleNamespace(
                success=True,
                product_id="pid",
                product_url="url",
                error_message="err",
            )

    class DummyOperationsService:
        def __init__(self, controller=None, analytics=None):
            pass

        async def polish_listing(self, product_id):
            return {"success": True}

        async def batch_polish(self, max_items=5):
            return {"success": 2, "total": max_items}

        async def update_price(self, **kwargs):
            return {"success": True, "old_price": 1, "new_price": 2}

    class DummyAnalyticsService:
        pass

    monkeypatch.setattr(mod, "OpenClawController", DummyController)
    monkeypatch.setattr(mod, "ListingService", DummyListingService)
    monkeypatch.setattr(mod, "OperationsService", DummyOperationsService)
    monkeypatch.setattr(mod, "AnalyticsService", DummyAnalyticsService)

    async def _no_sleep(*args, **kwargs):
        return None

    monkeypatch.setattr(mod.asyncio, "sleep", _no_sleep)

    assert await mod.demo_browser_connection() is True
    assert await mod.demo_publish_flow() is True
    assert await mod.demo_polish_flow() is True
    assert await mod.demo_price_update() is True
    assert await mod.demo_navigation() is True
    assert await mod.demo_element_operations() is True
    await mod.main()

    class DummyControllerFail(DummyController):
        async def connect(self):
            return False

    monkeypatch.setattr(mod, "OpenClawController", DummyControllerFail)
    assert await mod.demo_browser_connection() is False
    assert await mod.demo_publish_flow() is False
    assert await mod.demo_polish_flow() is False
    assert await mod.demo_price_update() is False
    assert await mod.demo_navigation() is False
    assert await mod.demo_element_operations() is False

    class DummyControllerNone(DummyController):
        async def find_element(self, page_id, selector):
            return None

    monkeypatch.setattr(mod, "OpenClawController", DummyControllerNone)
    assert await mod.demo_element_operations() is True

    async def _boom():
        raise RuntimeError('boom')

    monkeypatch.setattr(mod, "demo_browser_connection", _boom)
    await mod.main()

    out = capsys.readouterr().out
    assert "演示结果汇总" in out


@pytest.mark.asyncio
async def test_examples_advanced_and_analytics_smoke(monkeypatch, capsys):
    import examples.demo_advanced as adv
    import examples.demo_analytics as ana

    mod_accounts = types.ModuleType("src.modules.accounts.service")

    class AccountsService:
        def get_accounts(self):
            return [{"name": "a", "id": "1", "status": "ok"}]

        def get_all_accounts_health(self):
            return [{"account_id": "1", "health_score": 90}]

        def get_unified_dashboard(self):
            return {"total_accounts": 1, "active_accounts": 1, "total_products": 1}

        def distribute_publish(self, count=10):
            return [{"account": {"name": "a"}, "count": count}]

    mod_accounts.AccountsService = AccountsService

    mod_scheduler = types.ModuleType("src.modules.accounts.scheduler")

    class Task:
        def __init__(self, name, task_id, task_type="x", cron_expression="*", enabled=True):
            self.name = name
            self.task_id = task_id
            self.task_type = task_type
            self.cron_expression = cron_expression
            self.enabled = enabled

    class Scheduler:
        def create_polish_task(self, **kwargs):
            return Task("polish", "t1", "polish", "0 9 * * *")

        def create_metrics_task(self, **kwargs):
            return Task("metrics", "t2", "metrics", "0 */4 * * *")

        def list_tasks(self):
            return [Task("polish", "t1", enabled=True)]

        def get_scheduler_status(self):
            return {"total_tasks": 1, "enabled_tasks": 1}

    mod_scheduler.Scheduler = Scheduler

    mod_monitor = types.ModuleType("src.modules.accounts.monitor")

    class Alert:
        def __init__(self):
            self.alert_id = "a1"
            self.level = "info"
            self.title = "t"
            self.message = "m"

    class Monitor:
        def raise_alert(self, **kwargs):
            return Alert()

        def get_active_alerts(self):
            return [Alert()]

        def get_alert_summary(self):
            return {"total_alerts": 1, "active_alerts": 1, "resolved_alerts": 0}

    class HealthChecker:
        async def run_health_check(self):
            return {"checks": {"browser": {"status": "ok"}, "accounts": {"status": "ok"}}}

    mod_monitor.Monitor = Monitor
    mod_monitor.HealthChecker = HealthChecker

    mod_skill = types.ModuleType("skills.xianyu_accounts")

    class XianyuAccountsSkill:
        agent = None

        async def execute(self, action, payload):
            if action == "create_task":
                return {"status": "ok", "task_id": "t1"}
            return {"status": "ok", "total": 1}

    mod_skill.XianyuAccountsSkill = XianyuAccountsSkill

    monkeypatch.setitem(sys.modules, "src.modules.accounts.service", mod_accounts)
    monkeypatch.setitem(sys.modules, "src.modules.accounts.scheduler", mod_scheduler)
    monkeypatch.setitem(sys.modules, "src.modules.accounts.monitor", mod_monitor)
    monkeypatch.setitem(sys.modules, "skills.xianyu_accounts", mod_skill)

    await adv.demo_accounts()
    await adv.demo_scheduler()
    await adv.demo_monitor()
    await adv.demo_distribution()
    await adv.demo_skill_usage()
    await adv.main()
    assert await adv.MockLLM().chat('hello world')

    async def boom():
        raise RuntimeError("x")

    monkeypatch.setattr(adv, "demo_accounts", boom)
    await adv.main()

    mod_ana_service = types.ModuleType("src.modules.analytics.service")

    class AnalyticsService:
        async def get_dashboard_stats(self):
            return {
                "total_operations": 1,
                "today_operations": 1,
                "active_products": 1,
                "sold_products": 1,
                "total_revenue": 1.0,
            }

        async def get_trend_data(self, metric, days):
            return [{"date": "2024-01-01", "value": 1}]

        async def get_product_performance(self, days):
            return [{"product_id": "p1", "total_wants": 1}]

        async def export_data(self, t, f):
            return f"out.{f}"

    mod_ana_service.AnalyticsService = AnalyticsService

    mod_viz = types.ModuleType("src.modules.analytics.visualization")

    class DataVisualizer:
        def generate_metrics_dashboard(self):
            return "chart"

        def generate_line_chart(self, *args, **kwargs):
            return "line"

        def generate_bar_chart(self, *args, **kwargs):
            return "bar"

    class ChartExporter:
        pass

    mod_viz.DataVisualizer = DataVisualizer
    mod_viz.ChartExporter = ChartExporter

    mod_report = types.ModuleType("src.modules.analytics.report_generator")

    class ReportGenerator:
        async def generate_daily_report(self):
            return {"report_type": "daily", "date": "2024-01-01", "summary": "ok"}

        async def generate_weekly_report(self):
            return {"report_type": "weekly", "period": {"start": "s", "end": "e"}}

    class ReportFormatter:
        pass

    mod_report.ReportGenerator = ReportGenerator
    mod_report.ReportFormatter = ReportFormatter

    monkeypatch.setitem(sys.modules, "src.modules.analytics.service", mod_ana_service)
    monkeypatch.setitem(sys.modules, "src.modules.analytics.visualization", mod_viz)
    monkeypatch.setitem(sys.modules, "src.modules.analytics.report_generator", mod_report)

    await ana.demo_dashboard()
    await ana.demo_reports()
    await ana.demo_trends()
    await ana.demo_performance()
    await ana.demo_export()
    await ana.demo_charts()
    await ana.main()

    class AnalyticsServiceEmpty(AnalyticsService):
        async def get_trend_data(self, metric, days):
            return []

        async def get_product_performance(self, days):
            return []

    mod_ana_service.AnalyticsService = AnalyticsServiceEmpty
    monkeypatch.setitem(sys.modules, "src.modules.analytics.service", mod_ana_service)
    await ana.demo_trends()
    await ana.demo_performance()

    async def boom2():
        raise RuntimeError("x")

    monkeypatch.setattr(ana, "demo_dashboard", boom2)
    await ana.main()

    import examples

    assert "demo_listing_creation" in examples.__all__
    out = capsys.readouterr().out
    assert "演示完成" in out

import asyncio
import io
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.core.browser_client import BrowserError
from src.dashboard_server import DashboardHandler
from src.modules.accounts.monitor import Alert, AlertLevel, Monitor
from src.modules.accounts.scheduler import Scheduler, Task, TaskStatus, TaskType
from src.modules.analytics.visualization import ChartExporter, DataVisualizer


@pytest.mark.asyncio
async def test_scheduler_core_paths(temp_dir, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(temp_dir)
    scheduler = Scheduler()

    task = scheduler.create_task(task_type=TaskType.CUSTOM, interval=1, params={"a": 1})
    assert scheduler.get_task(task.task_id) is task
    assert scheduler.list_tasks(enabled_only=True)
    assert scheduler.update_task(task.task_id, enabled=False, name="n1") is True
    assert scheduler.update_task("missing", enabled=True) is False
    assert scheduler.delete_task("missing") is False
    assert scheduler.delete_task(task.task_id) is True

    assert (await scheduler.run_task_now("missing"))["success"] is False
    t2 = scheduler.create_task(task_type=TaskType.CUSTOM, interval=1)
    scheduler.running_tasks[t2.task_id] = asyncio.create_task(asyncio.sleep(0))
    assert (await scheduler.run_task_now(t2.task_id))["success"] is False
    scheduler.running_tasks.clear()


@pytest.mark.asyncio
async def test_scheduler_execute_and_task_type_branches(temp_dir, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(temp_dir)
    scheduler = Scheduler()

    unknown = Task(task_id="u1", task_type="unknown")
    result_unknown = await scheduler.execute_task(unknown)
    assert result_unknown["message"].startswith("Unknown task type")
    assert unknown.status == TaskStatus.COMPLETED

    ok_task = Task(task_id="p1", task_type=TaskType.POLISH)
    scheduler._execute_polish = AsyncMock(return_value={"success": True, "message": "ok"})
    res_ok = await scheduler.execute_task(ok_task)
    assert res_ok["success"] is True
    assert ok_task.run_count == 1

    bad_task = Task(task_id="p2", task_type=TaskType.POLISH)
    scheduler._execute_polish = AsyncMock(side_effect=RuntimeError("boom"))
    res_bad = await scheduler.execute_task(bad_task)
    assert res_bad["success"] is False
    assert bad_task.status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_scheduler_execute_polish_publish_metrics_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    scheduler = Scheduler()

    class FakeClient:
        def __init__(self) -> None:
            self.disconnected = False

        async def disconnect(self):
            self.disconnected = True

    fake_client = FakeClient()
    monkeypatch.setattr("src.modules.accounts.scheduler.create_browser_client", AsyncMock(return_value=fake_client))

    class FakeOpService:
        def __init__(self, controller):
            self.controller = controller

        async def batch_polish(self, max_items=50):
            return {"success": max_items}

    import src.modules.operations.service as op_mod

    monkeypatch.setattr(op_mod, "OperationsService", FakeOpService)
    res_polish = await scheduler._execute_polish({"max_items": 3})
    assert res_polish["success"] is True
    assert fake_client.disconnected is True

    monkeypatch.setattr(
        "src.modules.accounts.scheduler.create_browser_client",
        AsyncMock(side_effect=BrowserError("no browser")),
    )
    res_polish_err = await scheduler._execute_polish({})
    assert res_polish_err["error_code"] == "BROWSER_CONNECT_FAILED"

    assert (await scheduler._execute_publish({"listings": []}))["success"] is False

    class FakeResult:
        def __init__(self, success: bool, pid: str):
            self.success = success
            self.product_id = pid

    class FakeListingService:
        def __init__(self, controller):
            self.controller = controller

        async def batch_create_listings(self, listings):
            return [FakeResult(True, "p1"), FakeResult(False, "p2")]

    class FakeListing:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    import src.modules.listing.models as listing_models
    import src.modules.listing.service as listing_service

    monkeypatch.setattr("src.modules.accounts.scheduler.create_browser_client", AsyncMock(return_value=FakeClient()))
    monkeypatch.setattr(listing_models, "Listing", FakeListing)
    monkeypatch.setattr(listing_service, "ListingService", FakeListingService)
    res_publish = await scheduler._execute_publish({"listings": [{"title": "t"}]})
    assert res_publish["success"] is True
    assert "Published 1/2 items" in res_publish["message"]

    monkeypatch.setattr("src.modules.accounts.scheduler.create_browser_client", AsyncMock(side_effect=BrowserError("x")))
    res_publish_err = await scheduler._execute_publish({"listings": [{"title": "t"}]})
    assert res_publish_err["error_code"] == "BROWSER_CONNECT_FAILED"

    class FakeAnalytics:
        async def get_dashboard_stats(self):
            return {"v": 1}

    import src.modules.analytics.service as ana_service

    monkeypatch.setattr(ana_service, "AnalyticsService", lambda: FakeAnalytics())
    assert (await scheduler._execute_metrics({}))["success"] is True


@pytest.mark.asyncio
async def test_scheduler_timing_start_stop_and_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    scheduler = Scheduler()
    task = scheduler.create_task(task_type=TaskType.CUSTOM, interval=1)

    task.enabled = False
    assert scheduler._should_run(task) is False
    task.enabled = True
    scheduler.running_tasks[task.task_id] = asyncio.create_task(asyncio.sleep(0))
    assert scheduler._should_run(task) is False
    scheduler.running_tasks.clear()
    task.last_run = None
    assert scheduler._should_run(task) is True

    task.last_run = datetime.now() - timedelta(seconds=10)
    task.interval = 1
    task.cron_expression = None
    assert scheduler._should_run(task) is True

    task.cron_expression = "bad cron"
    assert scheduler._should_run(task) is False

    assert scheduler._get_next_cron_run("* * * * *", datetime.now()) > datetime.now() - timedelta(hours=1)
    assert scheduler._get_next_cron_run("bad", datetime.now()) > datetime.now() - timedelta(hours=1)

    called = {"run": 0, "sleep": 0}

    async def fake_run(task_id: str):
        called["run"] += 1
        return {"success": True}

    async def fake_sleep(_secs: int):
        called["sleep"] += 1
        raise asyncio.CancelledError

    scheduler._should_run = Mock(return_value=True)
    scheduler.run_task_now = fake_run
    monkeypatch.setattr("src.modules.accounts.scheduler.asyncio.sleep", fake_sleep)
    await scheduler._scheduler_loop()
    assert called["run"] >= 1
    assert called["sleep"] == 1

    await scheduler.start()
    assert scheduler._scheduler_task is not None
    await scheduler.stop()
    status = scheduler.get_scheduler_status()
    assert "total_tasks" in status and "tasks" in status


@pytest.mark.asyncio
async def test_monitor_paths(temp_dir, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(temp_dir)
    monitor = Monitor(config={})

    assert "browser_connection" in monitor._default_rules()
    assert "publish_failure" in monitor._default_recovery_actions()

    seen = {"sync": 0, "async": 0}

    def cb_sync(_a):
        seen["sync"] += 1

    async def cb_async(_a):
        seen["async"] += 1

    monitor.register_callback(cb_sync)
    monitor.register_callback(cb_async)

    monkeypatch.setattr("src.modules.accounts.monitor.asyncio.sleep", AsyncMock(return_value=None))

    alert = await monitor.raise_alert(
        alert_type="publish_failure",
        title="t",
        message="m",
        source="publish_failure",
        auto_resolve=True,
    )
    await monitor._trigger_callbacks(alert)
    assert alert.level in {AlertLevel.WARNING.value, AlertLevel.WARNING.name.lower()}
    assert seen["sync"] >= 1
    assert seen["async"] >= 1

    active = await monitor.get_active_alerts()
    assert active
    summary = await monitor.get_alert_summary()
    assert summary["active_alerts"] >= 0

    assert await monitor.resolve_alert(alert.alert_id) is True
    assert await monitor.resolve_alert("missing") is False

    monitor._alerts = [
        Alert(level="warning", source="publish_failure", details={}) for _ in range(6)
    ]

    triggered = {"n": 0}

    async def fake_raise_alert(**kwargs):
        triggered["n"] += 1
        return Alert(title=kwargs.get("title", ""))

    monitor.raise_alert = fake_raise_alert

    await monitor.check_condition("publish_failure", lambda _ctx: True, context={"x": 1})
    assert triggered["n"] == 1

    await monitor.check_condition("unknown", lambda _ctx: True)

    async def bad_check(_ctx):
        raise RuntimeError("x")

    await monitor.check_condition("publish_failure", bad_check)

    monitor._alerts.append(Alert(level="warning", source="publish_failure"))
    assert monitor._count_recent_failures("publish_failure", 60) >= 1

    removed = await monitor.cleanup_old_alerts(days=0)
    assert removed >= 0


@pytest.mark.asyncio
async def test_monitor_recovery_actions_and_health_checker(monkeypatch: pytest.MonkeyPatch) -> None:
    monitor = Monitor(config={})

    class FakeClient:
        async def connect(self):
            return True

    import src.core.browser_client as bc_mod

    monkeypatch.setattr(bc_mod, "BrowserClient", lambda: FakeClient())
    await monitor._action_reconnect_browser(Alert())

    monkeypatch.setattr("src.modules.accounts.monitor.asyncio.sleep", AsyncMock(return_value=None))
    await monitor._action_wait_and_retry(Alert())
    await monitor._action_wait_longer(Alert())

    from src.modules.accounts.monitor import HealthChecker

    hc = HealthChecker()
    hc.monitor = monitor

    async def fake_raise(**_kwargs):
        return Alert()

    monitor.raise_alert = fake_raise

    assert await hc.check_browser_connection() is True

    class BadClient:
        async def connect(self):
            raise RuntimeError("bad")

    monkeypatch.setattr(bc_mod, "BrowserClient", lambda: BadClient())
    assert await hc.check_browser_connection() is False

    class FakeAccounts:
        def get_accounts(self):
            return [{"id": "a1"}, {"id": "a2"}]

        def validate_cookie(self, account_id):
            return account_id == "a1"

    import src.modules.accounts.service as acc_mod

    monkeypatch.setattr(acc_mod, "AccountsService", lambda: FakeAccounts())
    issues = await hc.check_account_status()
    assert len(issues) == 1

    class BadAccounts:
        def __init__(self):
            raise RuntimeError("x")

    monkeypatch.setattr(acc_mod, "AccountsService", BadAccounts)
    assert await hc.check_account_status() == []

    hc.check_browser_connection = AsyncMock(return_value=True)
    hc.check_account_status = AsyncMock(return_value=[])
    result = await hc.run_health_check()
    assert result["checks"]["browser"]["status"] == "healthy"


def test_data_visualizer_sync_paths() -> None:
    viz = DataVisualizer()
    assert viz.generate_bar_chart([], "k", "v") == "No data available"
    assert viz.generate_bar_chart([{"v": 0}], "k", "v") == "No data to display"

    chart = viz.generate_bar_chart(
        [{"name": "ABCDEFGHIJKLMNZZ", "value": 10}, {"name": "B", "value": 5}],
        "name",
        "value",
        title="T",
        max_width=10,
    )
    assert "📊 T" in chart and "ABCDEFGHIJKLMNZ" in chart

    assert viz.generate_line_chart([], "d", "v") == "Need at least 2 data points"
    assert viz.generate_line_chart([{"d": "a", "v": 1}, {"d": "b", "v": 1}], "d", "v") == "No variation in data"
    line = viz.generate_line_chart([{"d": "a", "v": 1}, {"d": "b", "v": 3}], "d", "v", title="L")
    assert "📈 L" in line and "●" in line


@pytest.mark.asyncio
async def test_data_visualizer_async_and_exporter_paths(temp_dir, monkeypatch: pytest.MonkeyPatch) -> None:
    viz = DataVisualizer()

    class FakeAnalytics:
        async def get_dashboard_stats(self):
            return {
                "total_operations": 1,
                "today_operations": 2,
                "active_products": 3,
                "sold_products": 4,
                "total_revenue": 5.5,
                "today_views": 6,
                "today_wants": 7,
            }

        async def get_trend_data(self, _metric, _days):
            return [{"date": f"2026-02-{i:02d}", "value": i} for i in range(1, 20)]

    viz.analytics = FakeAnalytics()

    dashboard = await viz.generate_metrics_dashboard()
    assert "闲鱼运营仪表盘" in dashboard

    weekly = await viz.generate_weekly_trend(weeks=2)
    assert "Views Trend" in weekly

    viz.analytics = SimpleNamespace(get_trend_data=AsyncMock(return_value=[]))
    assert await viz.generate_weekly_trend(weeks=1) == "No trend data available"

    class FakeFormatter:
        @staticmethod
        def to_markdown(report):
            return f"# {report['report_type']}"

        @staticmethod
        def to_slack(report):
            return f"slack:{report['period']['date']}"

    import src.modules.analytics.report_generator as report_gen

    monkeypatch.setattr(report_gen, "ReportFormatter", FakeFormatter)

    path_md = await ChartExporter.export_report({"report_type": "daily"}, format="markdown", filepath=str(temp_dir / "r"))
    assert path_md.endswith(".md")

    path_json = await ChartExporter.export_report({"report_type": "daily"}, format="json", filepath=str(temp_dir / "r2"))
    assert path_json.endswith(".json")

    path_txt = await ChartExporter.export_report({"report_type": "daily"}, format="text", filepath=str(temp_dir / "r3"))
    assert path_txt.endswith(".txt")

    auto_path = await ChartExporter.export_report({"report_type": "auto"}, format="text")
    assert auto_path.endswith(".txt") and "data/report_auto_" in auto_path

    monkeypatch.setattr("src.modules.analytics.visualization.AnalyticsService", lambda: FakeAnalytics())
    txt = await ChartExporter.export_daily_summary(format="text")
    assert "每日运营摘要" in txt
    slack = await ChartExporter.export_daily_summary(format="slack")
    assert slack.startswith("slack:")


def _build_handler(path: str) -> DashboardHandler:
    handler = DashboardHandler.__new__(DashboardHandler)
    handler.path = path
    handler.headers = {}
    handler.rfile = io.BytesIO(b"")
    handler.wfile = io.BytesIO()
    handler.repo = Mock()
    handler.module_console = Mock()
    handler.mimic_ops = Mock()
    handler.send_response = Mock()
    handler.send_header = Mock()
    handler.end_headers = Mock()
    handler._send_json = Mock()
    handler._send_html = Mock()
    handler._send_bytes = Mock()
    return handler


def test_dashboard_handler_read_json_and_multipart() -> None:
    h = _build_handler("/")

    h.headers = {"Content-Length": "7"}
    h.rfile = io.BytesIO(b"{\"a\":1}")
    assert h._read_json_body() == {"a": 1}

    h.headers = {"Content-Length": "x"}
    h.rfile = io.BytesIO(b"bad")
    assert h._read_json_body() == {}

    h.headers = {"Content-Type": "text/plain"}
    assert h._read_multipart_files() == []


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/", "_send_html"),
        ("/cookie", "_send_html"),
        ("/api/summary", "_send_json"),
        ("/api/trend?metric=views&days=5", "_send_json"),
        ("/api/recent-operations?limit=3", "_send_json"),
        ("/api/top-products?limit=3", "_send_json"),
        ("/api/module/status?window=10&limit=2", "_send_json"),
        ("/api/module/check?skip_gateway=1", "_send_json"),
        ("/api/module/logs?target=all&tail=20", "_send_json"),
        ("/api/status", "_send_json"),
        ("/api/get-cookie", "_send_json"),
        ("/api/route-stats", "_send_json"),
        ("/api/export-routes", "_send_bytes"),
        ("/api/get-template?default=true", "_send_json"),
        ("/api/get-markup-rules", "_send_json"),
        ("/api/logs/files", "_send_json"),
        ("/api/logs/content?file=a&tail=20", "_send_json"),
        ("/not-found", "_send_json"),
    ],
)
def test_dashboard_handler_do_get_routes(path: str, expected: str) -> None:
    h = _build_handler(path)
    h.repo.get_summary.return_value = {"ok": True}
    h.repo.get_trend.return_value = {"ok": True}
    h.repo.get_recent_operations.return_value = {"ok": True}
    h.repo.get_top_products.return_value = {"ok": True}
    h.module_console.status.return_value = {"ok": True}
    h.module_console.check.return_value = {"ok": True}
    h.module_console.logs.return_value = {"ok": True}
    h.mimic_ops.service_status.return_value = {"ok": True}
    h.mimic_ops.get_cookie.return_value = {"ok": True}
    h.mimic_ops.route_stats.return_value = {"ok": True}
    h.mimic_ops.export_routes_zip.return_value = (b"zip", "a.zip")
    h.mimic_ops.get_template.return_value = {"ok": True}
    h.mimic_ops.get_markup_rules.return_value = {"ok": True}
    h.mimic_ops.list_log_files.return_value = {"ok": True}
    h.mimic_ops.read_log_content.return_value = {"success": True, "lines": ["x"]}

    h.do_GET()
    assert getattr(h, expected).called


def test_dashboard_handler_do_get_error_paths() -> None:
    h = _build_handler("/api/download-cookie-plugin")
    h.mimic_ops.export_cookie_plugin_bundle.side_effect = FileNotFoundError("missing")
    h.do_GET()
    assert h._send_json.called

    h2 = _build_handler("/api/summary")
    import sqlite3

    h2.repo.get_summary.side_effect = sqlite3.Error("db")
    h2.do_GET()
    assert h2._send_json.called


@pytest.mark.parametrize(
    "path,body,ok",
    [
        ("/api/module/control", {"action": "start", "target": "all"}, True),
        ("/api/service/control", {"action": "start"}, True),
        ("/api/service/recover", {"target": "presales"}, True),
        ("/api/update-cookie", {"cookie": "a=b"}, True),
        ("/api/parse-cookie", {"text": "cookie2=v"}, True),
        ("/api/cookie-diagnose", {"cookie": "cookie2=v"}, True),
        ("/api/reset-database", {"type": "all"}, True),
        ("/api/save-template", {"weight_template": "w", "volume_template": "v"}, True),
        ("/api/save-markup-rules", {"markup_rules": {}}, True),
        ("/api/test-reply", {"text": "hi"}, True),
    ],
)
def test_dashboard_handler_do_post_json_routes(path: str, body: dict, ok: bool) -> None:
    h = _build_handler(path)
    raw = json.dumps(body).encode("utf-8")
    h.headers = {"Content-Length": str(len(raw))}
    h.rfile = io.BytesIO(raw)

    h.module_console.control.return_value = {"ok": ok}
    h.mimic_ops.service_control.return_value = {"success": ok}
    h.mimic_ops.service_recover.return_value = {"success": ok}
    h.mimic_ops.update_cookie.return_value = {"success": ok}
    h.mimic_ops.parse_cookie_text.return_value = {"success": ok}
    h.mimic_ops.diagnose_cookie.return_value = {"success": ok}
    h.mimic_ops.reset_database.return_value = {"success": ok}
    h.mimic_ops.save_template.return_value = {"success": ok}
    h.mimic_ops.save_markup_rules.return_value = {"success": ok}
    h.mimic_ops.test_reply.return_value = {"success": ok}

    h.do_POST()
    assert h._send_json.called


def test_dashboard_handler_do_post_import_and_not_found_paths() -> None:
    h = _build_handler("/api/import-routes")
    h._read_multipart_files = Mock(side_effect=RuntimeError("bad parse"))
    h.do_POST()
    assert h._send_json.called

    h2 = _build_handler("/api/import-routes")
    h2._read_multipart_files = Mock(return_value=[])
    h2.mimic_ops.import_route_files.side_effect = RuntimeError("bad import")
    h2.do_POST()
    assert h2._send_json.called

    h3 = _build_handler("/api/import-markup")
    h3._read_multipart_files = Mock(return_value=[])
    h3.mimic_ops.import_markup_files.return_value = {"success": False}
    h3.do_POST()
    assert h3._send_json.called

    h4 = _build_handler("/api/import-cookie-plugin")
    h4._read_multipart_files = Mock(return_value=[])
    h4.mimic_ops.import_cookie_plugin_files.return_value = {"success": False}
    h4.do_POST()
    assert h4._send_json.called

    h5 = _build_handler("/api/service/auto-fix")
    h5.mimic_ops.service_auto_fix.return_value = {"success": True}
    h5.do_POST()
    assert h5._send_json.called

    h6 = _build_handler("/api/not-found")
    h6.do_POST()
    assert h6._send_json.called

# ISSUES FOUND:
# 1. [src/dashboard_server.py:5292-5320] _read_multipart_files 先把附件收集成 tuple，再按 item.filename/item.file 访问，
#    逻辑分支永远拿不到文件内容，multipart 上传在真实场景下会返回空列表。
# 2. [src/modules/analytics/report_generator.py:141] next(...) 的结果未被使用，疑似死代码或遗漏字段赋值。

import asyncio
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.dashboard_server import DashboardHandler, main, parse_args, run_server
from src.modules.accounts.monitor import HealthChecker, Monitor
from src.modules.accounts.scheduler import Scheduler, TaskType
from src.modules.analytics.report_generator import ReportFormatter, ReportGenerator
from src.modules.analytics.service import AnalyticsService
from src.modules.content.service import ContentService
from src.modules.listing.models import Listing
from src.modules.listing.service import ListingService
from src.modules.media.service import MediaService
from src.modules.operations.service import OperationsService


class _FakeController:
    def __init__(self) -> None:
        self.click_ret = True
        self.current_url = "https://www.goofish.com/success/item/abc"

    async def new_page(self):
        return "p1"

    async def navigate(self, *_args, **_kwargs):
        return None

    async def click(self, *_args, **_kwargs):
        return self.click_ret

    async def close_page(self, *_args, **_kwargs):
        return None

    async def type_text(self, *_args, **_kwargs):
        return False

    async def get_text(self, *_args, **_kwargs):
        return ""

    async def find_elements(self, *_args, **_kwargs):
        return []

    async def upload_files(self, *_args, **_kwargs):
        return None

    async def execute_script(self, _pid, script):
        if "window.location.href" in script:
            return self.current_url
        return False


@pytest.mark.asyncio
async def test_scheduler_branches_load_and_loop_error(temp_dir, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(temp_dir)
    p = temp_dir / "data" / "scheduler_tasks.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("not-json", encoding="utf-8")

    s = Scheduler()
    assert s.tasks == {}

    t = s.create_polish_task()
    assert t.task_type == TaskType.POLISH
    t2 = s.create_metrics_task()
    assert t2.task_type == TaskType.METRICS

    async def bad_run(_task_id: str):
        raise RuntimeError("loop-fail")

    async def fake_sleep(_secs: int):
        raise asyncio.CancelledError

    s._should_run = Mock(return_value=True)
    s.run_task_now = bad_run
    monkeypatch.setattr("src.modules.accounts.scheduler.asyncio.sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        await s._scheduler_loop()


@pytest.mark.asyncio
async def test_monitor_load_fail_and_health_checker_paths(temp_dir, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(temp_dir)
    p = temp_dir / "data" / "monitor_alerts.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{bad", encoding="utf-8")
    m = Monitor()
    assert m._alerts == []

    checker = HealthChecker()

    class BadBrowser:
        async def connect(self):
            raise RuntimeError("connect boom")

    monkeypatch.setattr("src.core.browser_client.BrowserClient", BadBrowser)
    checker.monitor.raise_alert = AsyncMock(return_value=None)
    assert await checker.check_browser_connection() is False

    class BadAccountsService:
        def get_accounts(self):
            raise RuntimeError("accounts fail")

    monkeypatch.setattr("src.modules.accounts.service.AccountsService", lambda: BadAccountsService())
    assert await checker.check_account_status() == []


@pytest.mark.asyncio
async def test_operations_service_missing_controller_and_error_paths() -> None:
    service = OperationsService(controller=None)
    with pytest.raises(Exception):
        await service.get_listing_stats()

    fc = _FakeController()
    service = OperationsService(controller=fc)
    service._random_delay = Mock(return_value=0)

    fc.current_url = "https://www.goofish.com/other"
    with pytest.raises(Exception):
        await service._step_verify_success("p1")

    fc.click_ret = False
    out = await service.delist("pid", confirm=True)
    assert out["success"] is False


@pytest.mark.asyncio
async def test_listing_service_targeted_branches() -> None:
    fc = _FakeController()
    svc = ListingService(controller=fc)
    svc._random_delay = Mock(return_value=0)

    listing = Listing(title="t", description="d", price=1, category="Unknown", images=["  ", "img.png"], tags=["none"])
    await svc._step_upload_images("p1", listing.images)
    await svc._step_fill_title("p1", "t")
    await svc._step_fill_description("p1", "d")
    await svc._step_set_price("p1", 1)
    await svc._step_select_category("p1", "Unknown")
    await svc._step_select_condition("p1", ["xxx"])
    await svc._step_submit("p1")

    fc.current_url = "https://www.goofish.com/item/123"
    with pytest.raises(Exception):
        await svc._step_verify_success("p1")

    svc.analytics = SimpleNamespace(log_operation=AsyncMock(side_effect=RuntimeError("ana fail")))
    await svc._audit_compliance_event("evt", "msg", None, "title", [], blocked=False)

    bad = await svc.verify_listing("p")
    assert bad["exists"] is False


@pytest.mark.asyncio
async def test_media_and_content_service_error_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    media = MediaService()
    assert media.resize_image_for_xianyu("/tmp/not_exist.png") == "/tmp/not_exist.png"
    with pytest.raises(AttributeError):
        media.add_watermark("/tmp/not_exist.png")

    content = ContentService()
    optimized = content.optimize_title("", category="Unknown")
    assert isinstance(optimized, str)


@pytest.mark.asyncio
async def test_analytics_service_and_report_generator_branches(temp_dir, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(temp_dir)
    svc = AnalyticsService(config={"path": str(temp_dir / "ana.db")})
    data = await svc.get_trend_data("views", 2)
    assert data == []

    fake_analytics = SimpleNamespace(
        get_monthly_report=AsyncMock(
            return_value={"period": {"start": "s", "end": "e"}, "summary": {"total_revenue": 0, "total_sold": 0}, "top_categories": []}
        ),
        get_product_metrics=AsyncMock(return_value=[{"views": 1, "wants": 2}]),
        get_product_performance=AsyncMock(return_value=[{"product_id": "p1", "total_wants": 1}]),
        get_trend_data=AsyncMock(return_value=[]),
    )
    rg = ReportGenerator()
    rg.analytics = fake_analytics
    monthly = await rg.generate_monthly_report(year=2025, month=12)
    assert monthly["period"]["start"] == "s"

    product = await rg.generate_product_report("none", days=7)
    assert product["ranking"]["rank"] is None

    md = ReportFormatter.to_markdown({"report_type": "daily", "period": {"start": "a", "end": "b"}, "summary": {}, "operations": {"x": 1}})
    assert "Period" in md
    slack = ReportFormatter.to_slack({"report_type": "daily", "period": {"start": "a", "end": "b"}, "summary": {}})
    assert "a - b" in slack


def _build_handler(path: str) -> DashboardHandler:
    h = DashboardHandler.__new__(DashboardHandler)
    h.path = path
    h.headers = {}
    h.rfile = io.BytesIO(b"")
    h.wfile = io.BytesIO()
    h.repo = Mock()
    h.module_console = Mock()
    h.mimic_ops = Mock()
    h.send_response = Mock()
    h.send_header = Mock()
    h.end_headers = Mock()
    h._send_json = Mock()
    h._send_html = Mock()
    h._send_bytes = Mock()
    return h


def test_dashboard_handler_multipart_and_stream_and_entrypoints(monkeypatch: pytest.MonkeyPatch) -> None:
    h = _build_handler("/")
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    payload = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="a.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        "hello\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    mime = b"Content-Type: multipart/form-data; boundary=" + boundary.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n"
    h.headers = {"Content-Type": f"multipart/form-data; boundary={boundary}", "Content-Length": str(len(mime + payload))}
    h.rfile = io.BytesIO(mime + payload)
    files = h._read_multipart_files()
    assert len(files) == 1
    payload_by_name = {name: body for name, body in files}
    assert "a.txt" in payload_by_name
    assert payload_by_name["a.txt"].rstrip(b"\r\n") == b"hello"

    h2 = _build_handler("/api/logs/realtime/stream?file=a&tail=1")
    h2.mimic_ops.read_log_content.return_value = {"success": True, "lines": ["L1"]}

    def boom(_sec: int):
        raise BrokenPipeError

    monkeypatch.setattr("src.dashboard_server.time.sleep", boom)
    h2.do_GET()
    assert h2.send_response.called

    class FakeServer:
        def __init__(self, *_a, **_k):
            self.called = False

        def serve_forever(self):
            self.called = True

    monkeypatch.setattr("src.dashboard_server.ThreadingHTTPServer", FakeServer)
    monkeypatch.setattr("src.dashboard_server.get_config", lambda: SimpleNamespace(database={"path": "data/agent.db"}))
    run_server(host="127.0.0.1", port=19091, db_path="/tmp/x.db")

    monkeypatch.setattr("sys.argv", ["prog", "--host", "0.0.0.0", "--port", "9999", "--db-path", "db.sqlite"])
    args = parse_args()
    assert args.port == 9999

    monkeypatch.setattr("src.dashboard_server.run_server", Mock())
    monkeypatch.setattr("src.dashboard_server.parse_args", lambda: SimpleNamespace(host="h", port=1, db_path="d"))
    main()

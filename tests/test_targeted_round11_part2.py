import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import src.dashboard_server as ds
from src.dashboard_server import DashboardHandler
from src.modules.accounts.monitor import Monitor
from src.modules.accounts.scheduler import Scheduler, Task, TaskType
from src.modules.compliance.center import ComplianceCenter, ComplianceDecision
from src.modules.content.service import ContentService
from src.modules.listing.models import Listing
from src.modules.listing.service import ListingService
from src.modules.media.service import MediaService
from src.modules.operations.service import OperationsService


def _handler(path: str = "/") -> DashboardHandler:
    h = DashboardHandler.__new__(DashboardHandler)
    h.path = path
    h.headers = {}
    h.rfile = io.BytesIO()
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


def test_dashboard_read_json_and_payload_helpers() -> None:
    h = _handler()
    h.headers = {"Content-Length": "2"}
    h.rfile = io.BytesIO(b"{}")
    assert h._read_json_body() == {}

    h.headers = {"Content-Length": "2"}
    h.rfile = io.BytesIO(b"[]")
    assert h._read_json_body() == {}

    h.headers = {"Content-Length": "4"}
    h.rfile = io.BytesIO(b"bad{")
    assert h._read_json_body() == {}

    assert ds._extract_json_payload("prefix {\"a\":1} suffix") == {"a": 1}
    assert ds._extract_json_payload("junk") is None


@pytest.mark.asyncio
async def test_scheduler_metrics_exception_and_should_run_none_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    s = Scheduler()

    class BadAnalytics:
        def __init__(self):
            raise RuntimeError("init failed")

    import sys

    monkeypatch.setitem(sys.modules, "src.modules.analytics.service", SimpleNamespace(AnalyticsService=BadAnalytics))
    out = await s._execute_metrics({})
    assert out["success"] is False and "init failed" in out["message"]

    task = Task(task_id="n1", task_type=TaskType.CUSTOM)
    from datetime import datetime

    task.enabled = True
    task.last_run = datetime.now()
    task.interval = None
    task.cron_expression = None
    assert s._should_run(task) is False


@pytest.mark.asyncio
async def test_monitor_load_alerts_and_reconnect_false_branch(monkeypatch: pytest.MonkeyPatch, temp_dir) -> None:
    alert_file = temp_dir / "alerts.json"
    alert_file.write_text(json.dumps([{"alert_id": "a1", "title": "t", "message": "m"}]), encoding="utf-8")
    m = Monitor(config={})
    m.alert_file = alert_file
    m._load_alerts()
    assert len(m._alerts) >= 1

    class BrowserNoConn:
        async def connect(self):
            return False

    import sys

    monkeypatch.setitem(sys.modules, "src.core.browser_client", SimpleNamespace(BrowserClient=BrowserNoConn))
    await m._action_reconnect_browser(SimpleNamespace(alert_id="x"))


@pytest.mark.asyncio
async def test_operations_and_listing_error_branches(mock_controller) -> None:
    ops = OperationsService(controller=mock_controller)
    mock_controller.execute_script = AsyncMock(return_value=[])
    assert (await ops._extract_product_ids("p", limit=2)) == ["unknown_1", "unknown_2"]

    mock_controller.new_page = AsyncMock(side_effect=RuntimeError("new page fail"))
    assert (await ops.update_price("p", 1.0))["success"] is False
    assert (await ops.delist("p", confirm=True))["success"] is False
    assert (await ops.relist("p"))["success"] is False
    assert (await ops.refresh_inventory())["success"] is False
    assert "error" in (await ops.get_listing_stats())

    ls = ListingService(controller=mock_controller)
    listing = Listing(title="t", description="d", price=1, category="General", images=[], tags=[])
    mock_controller.new_page = AsyncMock(side_effect=RuntimeError("boom"))
    res = await ls.create_listing(listing)
    assert res.success is False

    v = await ls.verify_listing("x")
    assert v["exists"] is False and v["product_id"] == "x" and v["error"] == "boom"
    assert await ls.update_listing("x", {}) is False
    assert await ls.delete_listing("x") is False
    assert await ls.get_my_listings() == []


def test_media_and_content_extra_branches(temp_dir) -> None:
    svc = MediaService(config={"watermark": {"enabled": True}, "supported_formats": ["jpg"]})
    assert svc._get_save_format("unknown") == "JPEG"

    p = temp_dir / "bad.jpg"
    p.write_text("not image", encoding="utf-8")
    assert svc.resize_image_for_xianyu(str(p)).endswith("bad.jpg")
    assert svc.add_watermark(str(p)).endswith("bad.jpg")
    assert svc.compress_image(str(p)).endswith("bad.jpg")

    ok, msg = svc.validate_image(str(p))
    assert ok is False and "无法读取图片" in msg

    ai = ContentService(config={"api_key": "k", "usage_mode": "auto", "task_switches": {"title": False}})
    ai.client = None
    assert ai._should_call_ai("title", "x" * 400) is True
    assert ai._should_call_ai("title", "short") is False
    assert ai._normalize_config_value("${SECRET}") is None
    assert ai._normalize_config_value("  ") is None


def test_compliance_center_decision_and_filters(temp_dir) -> None:
    policy = temp_dir / "p.yaml"
    policy.write_text("version: v2\nglobal:\n  whitelist: ['ok']\n", encoding="utf-8")
    center = ComplianceCenter(policy_path=str(policy), db_path=str(temp_dir / "c.db"))

    d = center.evaluate_before_send("ok content", account_id="a", session_id="s")
    assert d.allowed is True
    assert ComplianceDecision(True, False, "pass", [], "global").to_dict()["allowed"] is True

    center.evaluate_before_send("normal", account_id="a", session_id="s")
    all_rows = center.replay(limit=10)
    by_session = center.replay(session_id="s", limit=10)
    blocked = center.replay(session_id="s", blocked_only=True, limit=10)
    assert len(all_rows) >= len(by_session) >= len(blocked)

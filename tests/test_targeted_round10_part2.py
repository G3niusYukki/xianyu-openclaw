import asyncio
import io
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import src.dashboard_server as ds
from src.dashboard_server import DashboardHandler
from src.modules.accounts.monitor import Monitor
from src.modules.accounts.scheduler import Scheduler, Task, TaskType, TaskStatus


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


def test_dashboard_extract_text_from_image_fallback_and_errors(monkeypatch: pytest.MonkeyPatch, temp_dir) -> None:
    ops = ds.MimicOps(project_root=temp_dir, module_console=ds.ModuleConsole(project_root=temp_dir))

    class FakePytesseract:
        @staticmethod
        def image_to_string(*_a, **_k):
            return "   "

    monkeypatch.setitem(sys.modules, "pytesseract", FakePytesseract)
    monkeypatch.setattr(ds.subprocess, "run", lambda *_a, **_k: SimpleNamespace(returncode=0, stdout="ocr text", stderr=""))

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (2, 2), (255, 255, 255)).save(buf, format="PNG")
    out = ops._extract_text_from_image(buf.getvalue())
    assert out == "ocr text"

    monkeypatch.setattr(ds.subprocess, "run", lambda *_a, **_k: SimpleNamespace(returncode=1, stdout="", stderr="boom"))
    with pytest.raises(ValueError, match="tesseract failed"):
        ops._extract_text_from_image(buf.getvalue())


def test_dashboard_xls_parse_error_and_zip_import_error(monkeypatch: pytest.MonkeyPatch, temp_dir) -> None:
    ops = ds.MimicOps(project_root=temp_dir, module_console=ds.ModuleConsole(project_root=temp_dir))

    class FakePd:
        @staticmethod
        def read_excel(*_a, **_k):
            raise RuntimeError("xlsx bad")

    monkeypatch.setitem(sys.modules, "pandas", FakePd)
    with pytest.raises(ValueError, match="excel parse failed"):
        ops._parse_markup_rules_from_file("x.xls", b"abc")

    bad_zip = ops.import_markup_files([("x.zip", b"not-a-zip")])
    assert bad_zip["success"] is False


def test_dashboard_risk_control_status_variants(temp_dir) -> None:
    ops = ds.MimicOps(project_root=temp_dir, module_console=ds.ModuleConsole(project_root=temp_dir))
    log_path = ops._module_runtime_log("presales")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [f"2026-01-01 00:00:0{i} websocket http 400" for i in range(6)]
    log_path.write_text("\n".join(lines), encoding="utf-8")
    warn = ops._risk_control_status_from_logs("presales", tail_lines=300)
    assert warn["level"] == "warning"

    log_path.write_text(
        "\n".join([
            "2026-01-01 00:00:01 token api failed",
            "2026-01-01 00:00:02 connected to goofish websocket transport",
        ]),
        encoding="utf-8",
    )
    recovered = ops._risk_control_status_from_logs("presales", tail_lines=300)
    assert recovered["level"] == "normal"
    assert recovered["label"] == "已恢复连接"


def test_dashboard_handler_logs_content_paging_and_import_markup_parse_error() -> None:
    h = _handler("/api/logs/content?file=presales.log&page=2&size=99&search=err")
    h.mimic_ops.read_log_content.return_value = {"success": False, "error": "x"}
    DashboardHandler.do_GET(h)
    kwargs = h.mimic_ops.read_log_content.call_args.kwargs
    assert kwargs["page"] == 2 and kwargs["size"] == 99 and kwargs["search"] == "err"
    assert h._send_json.call_args.kwargs["status"] == 404

    h2 = _handler("/api/import-routes")
    h2._read_multipart_files = Mock(return_value=[])
    h2.mimic_ops.import_route_files.return_value = {"success": False}
    DashboardHandler.do_POST(h2)
    assert h2._send_json.call_args.kwargs["status"] == 400

    h3 = _handler("/api/import-markup")
    h3._read_multipart_files = Mock(side_effect=RuntimeError("parse fail"))
    DashboardHandler.do_POST(h3)
    assert h3._send_json.call_args.kwargs["status"] == 400


@pytest.mark.asyncio
async def test_scheduler_missing_branches(monkeypatch: pytest.MonkeyPatch, temp_dir) -> None:
    s = Scheduler()
    s.storage_file = temp_dir / "tasks.json"

    task = Task(task_id="t1", name="m", task_type=TaskType.METRICS, params={})
    s.tasks[task.task_id] = task

    async def boom_metrics(_params):
        raise RuntimeError("mfail")

    monkeypatch.setattr(s, "_execute_metrics", boom_metrics)
    out = await s.execute_task(task)
    assert out["success"] is False and task.status == TaskStatus.FAILED

    class FakeListing:
        def __init__(self, **_k):
            raise RuntimeError("build listing fail")

    monkeypatch.setitem(sys.modules, "src.modules.listing.models", SimpleNamespace(Listing=FakeListing))
    monkeypatch.setitem(sys.modules, "src.modules.listing.service", SimpleNamespace(ListingService=object))
    monkeypatch.setattr("src.modules.accounts.scheduler.create_browser_client", AsyncMock(return_value=SimpleNamespace(disconnect=AsyncMock())))
    res_pub = await s._execute_publish({"listings": [{"title": "x"}]})
    assert res_pub["error_code"] == "PUBLISH_EXECUTION_FAILED"

    monkeypatch.setattr("src.modules.accounts.scheduler.create_browser_client", AsyncMock(side_effect=RuntimeError("no browser")))
    res_polish = await s._execute_polish({})
    assert res_polish["error_code"] == "POLISH_EXECUTION_FAILED"

    task2 = Task(task_id="t2", name="x", task_type=TaskType.POLISH, params={})
    s.tasks[task2.task_id] = task2
    monkeypatch.setattr(s, "execute_task", AsyncMock(return_value={"success": True}))
    started = await s.run_task_now("t2")
    assert started["success"] is True
    await asyncio.sleep(0.02)
    assert "t2" not in s.running_tasks

    task_bad = Task(task_id="tb", name="b", task_type=TaskType.POLISH, cron_expression="* * * * *")
    task_bad.enabled = True
    from datetime import datetime
    task_bad.last_run = datetime.now()
    monkeypatch.setattr(s, "_get_next_cron_run", lambda *_a, **_k: (_ for _ in ()).throw(ValueError("bad cron")))
    assert s._should_run(task_bad) is False


@pytest.mark.asyncio
async def test_monitor_missing_branches(monkeypatch: pytest.MonkeyPatch, temp_dir) -> None:
    m = Monitor(config={"alerts_file": str(temp_dir / "alerts.json")})

    m._alerts = []
    m._save_alerts_sync()
    assert m.alert_file.exists()
    await m._save_alerts()

    def bad_cb(_alert):
        raise RuntimeError("cb fail")

    m.register_callback(bad_cb)
    alert = await m.raise_alert("browser_connection", "t", "m")
    await m._trigger_callbacks(alert)

    class BadBrowser:
        async def connect(self):
            raise RuntimeError("connect fail")

    monkeypatch.setitem(sys.modules, "src.core.browser_client", SimpleNamespace(BrowserClient=BadBrowser))
    await m._action_reconnect_browser(SimpleNamespace(alert_id="a"))

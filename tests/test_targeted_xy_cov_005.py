import io
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.dashboard_server import DashboardHandler, MimicOps
from src.modules.messages import workflow as wf
from src.modules.messages.workflow import WorkflowState, WorkflowStore, WorkflowWorker


class _DummyService:
    def __init__(self, sessions=None, detail=None):
        self._sessions = sessions or []
        self._detail = detail or {"sent": True}

    async def get_unread_sessions(self, limit=20):
        return self._sessions[:limit]

    async def process_session(self, session, dry_run=False, page_id=None, actor=None):
        _ = (session, dry_run, page_id, actor)
        return self._detail


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
    return h


def test_dashboard_read_json_body_empty_raw_branch() -> None:
    h = _handler()
    h._read_json_body = DashboardHandler._read_json_body.__get__(h, DashboardHandler)
    h.headers = {"Content-Length": "4"}
    h.rfile = io.BytesIO(b"")
    assert h._read_json_body() == {}


def test_dashboard_service_status_stopped_and_token_error_paths(temp_dir) -> None:
    class Console:
        def status(self, window_minutes=60, limit=20):
            _ = (window_minutes, limit)
            return {
                "alive_count": 0,
                "total_modules": 3,
                "modules": {"presales": {"process": {"alive": False}, "sla": {}, "workflow": {}}},
            }

    ops = MimicOps(project_root=temp_dir, module_console=Console())
    ops._service_state["stopped"] = True
    ops.get_cookie = lambda: {"success": True, "cookie": "cookie2=v; _tb_token_=t"}  # type: ignore[assignment]
    ops.route_stats = lambda: {"stats": {"courier_details": {}}}  # type: ignore[assignment]

    ops._risk_control_status_from_logs = lambda target="presales", tail_lines=300: {  # type: ignore[assignment]
        "level": "warning",
        "signals": ["token api failed"],
        "last_event": "x",
    }
    status1 = ops.service_status()
    assert status1["service_status"] == "stopped"
    assert status1["token_error"] == "TOKEN_API_FAILED"

    ops._risk_control_status_from_logs = lambda target="presales", tail_lines=300: {  # type: ignore[assignment]
        "level": "warning",
        "signals": ["websocket xx http 400"],
        "last_event": "x",
    }
    status2 = ops.service_status()
    assert status2["token_error"] == "WS_HTTP_400"


def test_maybe_auto_recover_presales_branches(temp_dir) -> None:
    class Console:
        def control(self, action: str, target: str):
            return {"ok": True, "action": action, "target": target}

    ops = MimicOps(project_root=temp_dir, module_console=Console())

    inactive = ops._maybe_auto_recover_presales(
        service_status="stopped", token_error="FAIL_SYS_USER_VALIDATE", cookie_text="cookie2=x"
    )
    assert inactive["stage"] == "inactive"

    waiting = ops._maybe_auto_recover_presales(
        service_status="running", token_error="FAIL_SYS_USER_VALIDATE", cookie_text=""
    )
    assert waiting["reason"] == "cookie_empty"

    # same-cookie path after one successful recover
    ops._last_token_error = "FAIL_SYS_USER_VALIDATE"
    first = ops._maybe_auto_recover_presales(
        service_status="running", token_error="FAIL_SYS_USER_VALIDATE", cookie_text="cookie2=changed"
    )
    assert first["auto_recover_triggered"] is True
    second = ops._maybe_auto_recover_presales(
        service_status="running", token_error="FAIL_SYS_USER_VALIDATE", cookie_text="cookie2=changed"
    )
    assert second["reason"] == "same_cookie_already_recovered"


@pytest.mark.asyncio
async def test_workflow_store_and_alert_branches(temp_dir) -> None:
    store = WorkflowStore(db_path=str(temp_dir / "workflow.db"))

    # early returns / missing session
    store.ensure_session({"last_message": "x"})
    assert store.get_session("") is None
    assert store.enqueue_job({"last_message": "x"}) is False

    # row is None branches in transition/force
    assert store.transition_state("missing", WorkflowState.REPLIED, reason="auto") is True
    assert store.force_state("missing2", WorkflowState.CLOSED, reason="force") is True

    # quote success-rate alert + cooldown no-repeat
    store.record_sla_event("s1", stage="quote", outcome="failed", latency_ms=10)
    alerts1 = store.evaluate_sla_alerts(
        {
            "window_minutes": 60,
            "min_samples": 1,
            "reply_p95_threshold_ms": 999999,
            "quote_success_rate_threshold": 1.0,
        }
    )
    assert any(a["type"] == "quote_success" for a in alerts1)
    alerts2 = store.evaluate_sla_alerts(
        {
            "window_minutes": 60,
            "min_samples": 1,
            "reply_p95_threshold_ms": 999999,
            "quote_success_rate_threshold": 1.0,
        }
    )
    assert alerts2 == []


@pytest.mark.asyncio
async def test_workflow_worker_notification_and_failure_paths(temp_dir, monkeypatch: pytest.MonkeyPatch) -> None:
    store = WorkflowStore(db_path=str(temp_dir / "workflow.db"))
    session = {"session_id": "s_fail", "last_message": "hi"}

    service = _DummyService(sessions=[session], detail={"sent": False})
    worker = WorkflowWorker(
        message_service=service,
        store=store,
        config={"scan_limit": 5, "claim_limit": 5, "max_attempts": 2, "backoff_seconds": 0, "notifications": []},
        notifier=None,
    )

    # _send_notification short-circuit branches
    assert await worker._send_notification("x") is False
    worker._notifier = SimpleNamespace()  # no send_text
    assert await worker._send_notification("x") is False

    class BadNotifier:
        def send_text(self, _text):
            raise RuntimeError("boom")

    warnings = []
    monkeypatch.setattr(worker.logger, "warning", lambda msg: warnings.append(msg))
    worker._notifier = BadNotifier()
    assert await worker._send_notification("x") is False
    assert warnings

    # process_session sent=False -> fail path
    worker._notifier = None
    result = await worker.run_once(dry_run=True)
    assert result["failed"] == 1
    assert result["success"] == 0


@pytest.mark.asyncio
async def test_workflow_worker_recovery_and_run_forever_paths(temp_dir, monkeypatch: pytest.MonkeyPatch) -> None:
    store = WorkflowStore(db_path=str(temp_dir / "workflow.db"))

    class N:
        def __init__(self):
            self.msgs = []

        async def send_text(self, text):
            self.msgs.append(str(text))
            return True

    notifier = N()

    # first run produces alert, second run recovers with no alert
    service = _DummyService(
        sessions=[{"session_id": "s", "last_message": "m"}],
        detail={"sent": True, "is_quote": False, "quote_success": False, "quote_fallback": False},
    )
    worker = WorkflowWorker(
        message_service=service,
        store=store,
        config={
            "scan_limit": 5,
            "claim_limit": 5,
            "sla": {"window_minutes": 60, "min_samples": 1, "reply_p95_threshold_ms": -1},
            "notifications": {"feishu": {"notify_on_alert": True, "notify_recovery": True}},
        },
        notifier=notifier,
    )

    r1 = await worker.run_once(dry_run=True)
    assert r1["alerts"]

    monkeypatch.setattr(store, "evaluate_sla_alerts", lambda config=None: [])
    await worker.run_once(dry_run=True)
    assert any("恢复" in m for m in notifier.msgs)

    # run_forever start + heartbeat + max_loops + sleep path
    calls = []

    async def fake_run_once(dry_run=False):
        _ = dry_run
        return {"ok": True}

    async def fake_sleep(sec):
        calls.append(sec)

    worker.run_once = fake_run_once  # type: ignore[assignment]
    worker.notify_on_start = True
    worker.heartbeat_minutes = 1

    t = iter([1000.0, 1000.0, 1061.0, 1122.0])
    monkeypatch.setattr(wf.time, "time", lambda: next(t))
    monkeypatch.setattr(wf.asyncio, "sleep", fake_sleep)

    out = await worker.run_forever(dry_run=True, max_loops=2)
    assert out["loops"] == 2
    assert calls and calls[0] >= 0.2


def test_workflow_worker_init_feishu_notifier_branch(temp_dir, monkeypatch: pytest.MonkeyPatch) -> None:
    created = {}

    class FakeNotifier:
        def __init__(self, webhook_url, bot_name, timeout_seconds):
            created.update({"webhook_url": webhook_url, "bot_name": bot_name, "timeout_seconds": timeout_seconds})

    monkeypatch.setattr(wf, "FeishuNotifier", FakeNotifier)
    worker = WorkflowWorker(
        message_service=_DummyService(),
        store=WorkflowStore(db_path=str(temp_dir / "workflow.db")),
        config={
            "notifications": {
                "feishu": {"enabled": True, "webhook": "https://example", "bot_name": "bot", "timeout_seconds": 1}
            }
        },
        notifier=None,
    )
    assert worker._notifier is not None
    assert created["webhook_url"] == "https://example"

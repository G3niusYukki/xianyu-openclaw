from __future__ import annotations

import argparse
from types import SimpleNamespace

import pytest

from src import cli


class _DummyClient:
    def __init__(self):
        self.disconnected = False

    async def disconnect(self):
        self.disconnected = True


class _DummyResult:
    def __init__(self, **kwargs):
        self.success = kwargs.get("success", True)
        self.product_id = kwargs.get("product_id", "p1")
        self.product_url = kwargs.get("product_url", "http://x")
        self.error_message = kwargs.get("error_message")


@pytest.mark.asyncio
async def test_listing_related_cmds_and_ai(monkeypatch):
    out: list[dict] = []
    client = _DummyClient()

    class ListingService:
        def __init__(self, controller=None):
            self.controller = controller

        async def create_listing(self, listing):
            assert listing.title == "t"
            return _DummyResult()

    class OpsService:
        def __init__(self, controller=None):
            self.controller = controller

        async def batch_polish(self, max_items=50):
            return {"batch": max_items}

        async def polish_listing(self, pid):
            return {"id": pid}

        async def update_price(self, pid, price, op):
            return {"id": pid, "price": price, "original": op}

        async def delist(self, pid, reason=""):
            return {"id": pid, "reason": reason}

        async def relist(self, pid):
            return {"id": pid, "relisted": True}

    class ContentService:
        def get_ai_cost_stats(self):
            return {"cost": 1}

        def generate_title(self, **kwargs):
            return f"title-{kwargs['product_name']}"

        def generate_description(self, **_kwargs):
            return "desc"

    async def _mk_client():
        return client

    monkeypatch.setattr("src.core.browser_client.create_browser_client", _mk_client)
    monkeypatch.setattr("src.modules.listing.service.ListingService", ListingService)
    monkeypatch.setattr("src.modules.operations.service.OperationsService", OpsService)
    monkeypatch.setattr("src.modules.content.service.ContentService", ContentService)
    monkeypatch.setattr("src.cli._json_out", lambda d: out.append(d))

    await cli.cmd_publish(argparse.Namespace(title="t", description="d", price=1, original_price=2, category="c", images=["a"], tags=["x"]))
    await cli.cmd_polish(argparse.Namespace(all=True, max=3, id=None))
    await cli.cmd_polish(argparse.Namespace(all=False, max=3, id="p2"))
    await cli.cmd_polish(argparse.Namespace(all=False, max=3, id=None))
    await cli.cmd_price(argparse.Namespace(id="p3", price=9.9, original_price=19.9))
    await cli.cmd_delist(argparse.Namespace(id="p4", reason="r"))
    await cli.cmd_relist(argparse.Namespace(id="p5"))
    await cli.cmd_ai(argparse.Namespace(action="cost-stats", product_name="n", category="c"))
    await cli.cmd_ai(argparse.Namespace(action="simulate-publish", product_name="n", category="c"))
    await cli.cmd_ai(argparse.Namespace(action="unknown", product_name="n", category="c"))

    assert out[0]["success"] is True
    assert out[1]["batch"] == 3
    assert out[2]["id"] == "p2"
    assert "Specify --all or --id" in out[3]["error"]
    assert out[4]["price"] == 9.9
    assert out[5]["reason"] == "r"
    assert out[6]["relisted"] is True
    assert out[7]["cost"] == 1
    assert out[8]["title"].startswith("title-")
    assert "Unknown ai action" in out[9]["error"]
    assert client.disconnected is True


@pytest.mark.asyncio
async def test_cmd_messages_full_branches(monkeypatch):
    out: list[dict] = []

    class MsgSvc:
        def __init__(self, controller=None):
            self.closed = False

        async def get_unread_sessions(self, limit=20):
            return [{"sid": "s1"}][:limit]

        async def reply_to_session(self, sid, text):
            return sid == "ok" and bool(text)

        async def auto_reply_unread(self, limit=20, dry_run=False):
            return {"limit": limit, "dry_run": dry_run}

        async def close(self):
            self.closed = True

    class Store:
        def __init__(self, db_path=None):
            self.db_path = db_path

        def get_workflow_summary(self):
            return {"wf": 1}

        def get_sla_summary(self, window_minutes=0):
            return {"window": window_minutes}

        def transition_state(self, **_kwargs):
            return False

        def force_state(self, **_kwargs):
            return False

        def get_session(self, sid):
            return {"sid": sid}

    class Worker:
        def __init__(self, message_service=None, config=None):
            self.config = config

        async def run_forever(self, dry_run=False, max_loops=None):
            return {"mode": "daemon", "dry_run": dry_run, "max_loops": max_loops}

        async def run_once(self, dry_run=False):
            return {"mode": "once", "dry_run": dry_run}

    monkeypatch.setattr("src.modules.messages.service.MessagesService", MsgSvc)
    monkeypatch.setattr("src.modules.messages.workflow.WorkflowStore", Store)
    monkeypatch.setattr("src.modules.messages.workflow.WorkflowWorker", Worker)
    monkeypatch.setattr("src.cli._resolve_workflow_state", lambda _s: SimpleNamespace(value="ordered"))
    monkeypatch.setattr("src.cli._messages_requires_browser_runtime", lambda: False)
    monkeypatch.setattr("src.cli._json_out", lambda d: out.append(d))

    await cli.cmd_messages(argparse.Namespace(action="workflow-stats", workflow_db="db", window_minutes=10))
    await cli.cmd_messages(argparse.Namespace(action="workflow-transition", session_id=None, stage="ordered", workflow_db="db", force_state=False))
    await cli.cmd_messages(argparse.Namespace(action="workflow-transition", session_id="s1", stage="ordered", workflow_db="db", force_state=False))
    await cli.cmd_messages(argparse.Namespace(action="list-unread", limit=1))
    await cli.cmd_messages(argparse.Namespace(action="reply", session_id=None, text="x"))
    await cli.cmd_messages(argparse.Namespace(action="reply", session_id="ok", text="hi"))
    await cli.cmd_messages(argparse.Namespace(action="auto-reply", limit=2, dry_run=True))
    await cli.cmd_messages(argparse.Namespace(action="auto-workflow", workflow_db="db", interval=1, limit=3, daemon=False, dry_run=True, max_loops=2))
    await cli.cmd_messages(argparse.Namespace(action="auto-workflow", workflow_db="db", interval=1, limit=3, daemon=True, dry_run=False, max_loops=2))

    assert out[0]["workflow"]["wf"] == 1
    assert "Specify --session-id and --stage" in out[1]["error"]
    assert out[2]["success"] is False
    assert out[3]["total"] == 1
    assert "Specify --session-id and --text" in out[4]["error"]
    assert out[5]["success"] is True
    assert out[6]["dry_run"] is True
    assert out[7]["mode"] == "once"
    assert out[8]["mode"] == "daemon"


@pytest.mark.asyncio
async def test_cmd_automation_and_doctor_edges(monkeypatch):
    out: list[dict] = []

    class SetupSvc:
        def __init__(self, config_path=None):
            self.config_path = config_path

        def status(self):
            return {"status": "ok"}

        def apply(self, **kwargs):
            return kwargs

        def get_feishu_webhook(self):
            return ""

    class Notifier:
        def __init__(self, webhook_url):
            self.webhook_url = webhook_url

        async def send_text(self, text):
            return text != "bad"

    monkeypatch.setattr("src.modules.messages.setup.AutomationSetupService", SetupSvc)
    monkeypatch.setattr("src.modules.messages.notifications.FeishuNotifier", Notifier)
    monkeypatch.setattr("src.core.doctor.run_doctor", lambda **_k: {"ready": True, "summary": {"warning_failed": 1}})
    monkeypatch.setattr("src.cli._json_out", lambda d: out.append(d))

    await cli.cmd_automation(argparse.Namespace(action="status", config_path="x"))
    await cli.cmd_automation(argparse.Namespace(action="setup", config_path="x", enable_feishu=True, feishu_webhook="", poll_interval=1, scan_limit=2, claim_limit=3, reply_target_seconds=4, notify_on_start=False, disable_notify_on_alert=False, disable_notify_recovery=False, heartbeat_minutes=5))
    with pytest.raises(SystemExit):
        await cli.cmd_automation(argparse.Namespace(action="test-feishu", config_path="x", feishu_webhook="", message="ok"))

    assert out[0]["status"] == "ok"
    assert out[1]["feishu_enabled"] is True

    with pytest.raises(SystemExit):
        await cli.cmd_doctor(argparse.Namespace(skip_gateway=False, skip_quote=False, strict=True))


@pytest.mark.asyncio
async def test_cmd_module_actions(monkeypatch):
    out: list[dict] = []
    monkeypatch.setattr("src.core.doctor.run_doctor", lambda **_k: {"summary": {}, "checks": [], "next_steps": [], "ready": True})
    monkeypatch.setattr("src.cli._module_check_summary", lambda target, doctor_report: {"target": target, "runtime": "auto", "ready": target != "operations", "blockers": [{"name": "x"}] if target == "operations" else []})
    monkeypatch.setattr("src.cli._module_process_status", lambda target: {"alive": target == "presales"})
    monkeypatch.setattr("src.cli._module_logs", lambda target, tail_lines=80: {"target": target, "lines": [tail_lines]})
    monkeypatch.setattr("src.cli._start_background_module", lambda target, args: {"target": target, "started": True})
    monkeypatch.setattr("src.cli._stop_background_module", lambda target, timeout_seconds=6.0: {"target": target, "stopped": True, "timeout": timeout_seconds})
    monkeypatch.setattr("src.cli._clear_module_runtime_state", lambda target: {"target": target, "removed": ["x"]})

    async def sp(_args):
        return {"target": "presales", "mode": "once"}

    async def so(_args):
        return {"target": "operations", "mode": "once"}

    async def sa(_args):
        return {"target": "aftersales", "mode": "once"}

    monkeypatch.setattr("src.cli._start_presales_module", sp)
    monkeypatch.setattr("src.cli._start_operations_module", so)
    monkeypatch.setattr("src.cli._start_aftersales_module", sa)

    class Scheduler:
        def get_scheduler_status(self):
            return {"ok": True}

    class Store:
        def __init__(self, db_path=None):
            pass

        def get_workflow_summary(self):
            return {"wf": 1}

        def get_sla_summary(self, window_minutes=0):
            return {"w": window_minutes}

    class OrderSvc:
        def __init__(self, db_path=None):
            pass

        def list_orders(self, **_kwargs):
            return [{"order_id": "o1", "session_id": "s1"}]

        def get_summary(self):
            return {"sum": 1}

    monkeypatch.setattr("src.modules.accounts.scheduler.Scheduler", Scheduler)
    monkeypatch.setattr("src.modules.messages.workflow.WorkflowStore", Store)
    monkeypatch.setattr("src.modules.orders.service.OrderFulfillmentService", OrderSvc)
    monkeypatch.setattr("src.cli._json_out", lambda d: out.append(d))

    await cli.cmd_module(argparse.Namespace(action="check", target="all", skip_gateway=False, strict=False))
    await cli.cmd_module(argparse.Namespace(action="status", target="all", workflow_db=None, window_minutes=10, orders_db="db", limit=5))
    await cli.cmd_module(argparse.Namespace(action="logs", target="all", tail_lines=5))
    await cli.cmd_module(argparse.Namespace(action="stop", target="all", stop_timeout=3.0))
    await cli.cmd_module(argparse.Namespace(action="restart", target="all", stop_timeout=3.0))
    await cli.cmd_module(argparse.Namespace(action="recover", target="all", stop_timeout=3.0))

    with pytest.raises(SystemExit):
        await cli.cmd_module(argparse.Namespace(action="start", target="all", background=False, mode="daemon"))
    await cli.cmd_module(argparse.Namespace(action="start", target="presales", background=False, mode="once"))
    await cli.cmd_module(argparse.Namespace(action="start", target="operations", background=False, mode="once"))
    await cli.cmd_module(argparse.Namespace(action="start", target="aftersales", background=False, mode="once"))
    await cli.cmd_module(argparse.Namespace(action="unknown", target="presales"))

    assert out[0]["target"] == "all"
    assert out[1]["alive_count"] == 1
    assert out[2]["modules"]["presales"]["lines"] == [5]
    assert out[3]["action"] == "stop"
    assert out[4]["action"] == "restart"
    assert out[5]["action"] == "recover"
    assert out[7]["target"] == "presales"
    assert out[10]["error"].startswith("Unknown module action")


def test_build_parser_and_main_keyboard_interrupt(monkeypatch):
    parser = cli.build_parser()
    parsed = parser.parse_args(["module", "--action", "logs", "--target", "all", "--tail-lines", "3"])
    assert parsed.tail_lines == 3

    class P:
        def parse_args(self):
            return argparse.Namespace(command="publish")

        def print_help(self):
            return None

    async def raise_interrupt(_args):
        raise KeyboardInterrupt

    monkeypatch.setattr("src.cli.build_parser", lambda: P())
    monkeypatch.setattr("src.cli.cmd_publish", raise_interrupt)
    cli.main()

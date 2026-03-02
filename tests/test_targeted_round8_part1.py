from __future__ import annotations

import argparse
import asyncio
import json
from types import SimpleNamespace

import pytest

from src import cli
from src.core.error_handler import BrowserError
from src.modules.messages.ws_live import GoofishWsTransport, MessagePackDecoder


@pytest.fixture
def ws_enabled(monkeypatch):
    class WSModule:
        async def connect(self, *_a, **_k):
            raise RuntimeError("stub")

    monkeypatch.setattr("src.modules.messages.ws_live.websockets", WSModule())


def _ws_transport(config=None):
    return GoofishWsTransport(
        cookie_text="unb=10001; _m_h5_tk=token_a_123; cookie2=a; XSRF-TOKEN=x",
        config=config or {},
        cookie_supplier=None,
    )


@pytest.mark.asyncio
async def test_cli_listing_commands_and_main_paths(monkeypatch):
    out = []

    class Client:
        async def disconnect(self):
            out.append({"client": "disconnected"})

    class ListingSvc:
        def __init__(self, controller=None):
            self.controller = controller

        async def create_listing(self, listing):
            return SimpleNamespace(success=True, product_id="p1", product_url="u", error_message="")

    class OpSvc:
        def __init__(self, controller=None):
            self.controller = controller

        async def batch_polish(self, max_items=50):
            return {"all": True, "max": max_items}

        async def polish_listing(self, listing_id):
            return {"id": listing_id, "ok": True}

        async def update_price(self, pid, price, original_price):
            return {"ok": True, "id": pid, "price": price, "original_price": original_price}

        async def delist(self, pid, reason=""):
            return {"ok": True, "id": pid, "reason": reason}

        async def relist(self, pid):
            return {"ok": True, "id": pid}

    async def mk_client():
        return Client()

    monkeypatch.setattr("src.core.browser_client.create_browser_client", mk_client)
    monkeypatch.setattr("src.modules.listing.service.ListingService", ListingSvc)
    monkeypatch.setattr("src.modules.operations.service.OperationsService", OpSvc)
    monkeypatch.setattr("src.cli._json_out", lambda data: out.append(data))

    await cli.cmd_publish(
        argparse.Namespace(
            title="t", description="d", price=1.0, original_price=2.0, category="c", images=["a"], tags=["x"]
        )
    )
    await cli.cmd_polish(argparse.Namespace(all=True, id=None, max=3))
    await cli.cmd_polish(argparse.Namespace(all=False, id="item1", max=3))
    await cli.cmd_polish(argparse.Namespace(all=False, id=None, max=3))
    await cli.cmd_price(argparse.Namespace(id="item1", price=9.9, original_price=None))
    await cli.cmd_delist(argparse.Namespace(id="item1", reason="xx"))
    await cli.cmd_relist(argparse.Namespace(id="item1"))

    payloads = [x for x in out if isinstance(x, dict) and "client" not in x]
    assert payloads[0]["success"] is True
    assert payloads[1]["all"] is True
    assert payloads[2]["id"] == "item1"
    assert "Specify --all" in payloads[3]["error"]



@pytest.mark.asyncio
async def test_cli_messages_and_module_more_branches(monkeypatch):
    out = []
    monkeypatch.setattr("src.cli._json_out", lambda data: out.append(data))

    class Store:
        def __init__(self, db_path=None):
            self.db_path = db_path

        def get_workflow_summary(self):
            return {"count": 1}

        def get_sla_summary(self, window_minutes=0):
            return {"window": window_minutes}

        def transition_state(self, **_k):
            return True

        def get_session(self, sid):
            return {"id": sid}

        def force_state(self, **_k):
            return False

    monkeypatch.setattr("src.modules.messages.workflow.WorkflowStore", Store)
    monkeypatch.setattr("src.cli._resolve_workflow_state", lambda _s: SimpleNamespace(value="quoted"))

    await cli.cmd_messages(argparse.Namespace(action="workflow-stats", workflow_db="db", window_minutes=11))
    await cli.cmd_messages(argparse.Namespace(action="workflow-transition", session_id="s1", stage="quoted", workflow_db="db", force_state=False))
    await cli.cmd_messages(argparse.Namespace(action="workflow-transition", session_id=None, stage=None, workflow_db="db", force_state=False))
    monkeypatch.setattr("src.cli._resolve_workflow_state", lambda _s: None)
    await cli.cmd_messages(argparse.Namespace(action="workflow-transition", session_id="s1", stage="bad", workflow_db="db", force_state=False))

    class MsgSvc:
        def __init__(self, controller=None):
            self.controller = controller

        async def get_unread_sessions(self, limit=20):
            return [{"sid": "1"}] * min(limit, 2)

        async def reply_to_session(self, sid, text):
            return sid == "ok" and bool(text)

        async def auto_reply_unread(self, limit=20, dry_run=False):
            return {"limit": limit, "dry_run": dry_run}

        async def close(self):
            return None

    class Worker:
        def __init__(self, message_service=None, config=None):
            self.config = config or {}

        async def run_forever(self, dry_run=False, max_loops=None):
            return {"mode": "daemon", "dry_run": dry_run, "max_loops": max_loops}

        async def run_once(self, dry_run=False):
            return {"mode": "once", "dry_run": dry_run}

    class Client:
        async def disconnect(self):
            return None

    async def mk_client2():
        return Client()

    monkeypatch.setattr("src.modules.messages.service.MessagesService", MsgSvc)
    monkeypatch.setattr("src.modules.messages.workflow.WorkflowWorker", Worker)
    monkeypatch.setattr("src.cli._messages_requires_browser_runtime", lambda: True)
    monkeypatch.setattr("src.core.browser_client.create_browser_client", mk_client2)

    await cli.cmd_messages(argparse.Namespace(action="list-unread", limit=2))
    await cli.cmd_messages(argparse.Namespace(action="reply", session_id=None, text=None))
    await cli.cmd_messages(argparse.Namespace(action="reply", session_id="ok", text="hi"))
    await cli.cmd_messages(argparse.Namespace(action="auto-reply", limit=4, dry_run=True))
    await cli.cmd_messages(
        argparse.Namespace(
            action="auto-workflow", daemon=False, dry_run=True, workflow_db="db", interval=1.0, limit=2, max_loops=1
        )
    )
    await cli.cmd_messages(
        argparse.Namespace(
            action="auto-workflow", daemon=True, dry_run=False, workflow_db="db", interval=1.0, limit=2, max_loops=1
        )
    )

    monkeypatch.setattr("src.core.doctor.run_doctor", lambda **_k: {"summary": {}, "checks": [], "next_steps": []})
    monkeypatch.setattr(
        "src.cli._module_check_summary",
        lambda target, doctor_report: {
            "target": target,
            "runtime": "auto",
            "ready": True,
            "required_checks": [],
            "blockers": [],
            "next_steps": doctor_report.get("next_steps", []),
            "doctor_summary": doctor_report.get("summary", {}),
        },
    )

    class Sched:
        def get_scheduler_status(self):
            return {"running": False}

    class OrderSvc:
        def __init__(self, db_path=None):
            self.db_path = db_path

        def get_summary(self):
            return {"sum": 1}

        def list_orders(self, **_k):
            return [{"order_id": "o1", "session_id": "s1", "manual_takeover": False, "updated_at": "n"}]

    monkeypatch.setattr("src.modules.accounts.scheduler.Scheduler", Sched)
    monkeypatch.setattr("src.modules.orders.service.OrderFulfillmentService", OrderSvc)

    args_common = dict(
        workflow_db="w.db",
        orders_db="o.db",
        window_minutes=5,
        limit=1,
        skip_gateway=False,
        strict=False,
        stop_timeout=1.0,
        tail_lines=3,
        max_loops=1,
        interval=0.01,
        claim_limit=1,
        dry_run=True,
        issue_type="delay",
        include_manual=False,
        init_default_tasks=False,
        skip_polish=True,
        skip_metrics=True,
        polish_max_items=1,
        polish_cron="",
        metrics_cron="",
    )

    monkeypatch.setattr("src.cli._module_process_status", lambda _t: {"alive": False})
    monkeypatch.setattr("src.cli._start_background_module", lambda target, args: {"target": target, "started": True})
    monkeypatch.setattr("src.cli._stop_background_module", lambda target, timeout_seconds=0: {"target": target, "stopped": True})
    monkeypatch.setattr("src.cli._module_logs", lambda target, tail_lines=10: {"target": target, "lines": ["x"]})
    monkeypatch.setattr("src.cli._clear_module_runtime_state", lambda target: {"target": target, "removed": [target]})
    monkeypatch.setattr("src.cli._start_presales_module", lambda args: asyncio.sleep(0, result={"target": "presales"}))
    monkeypatch.setattr("src.cli._start_operations_module", lambda args: asyncio.sleep(0, result={"target": "operations"}))
    monkeypatch.setattr("src.cli._start_aftersales_module", lambda args: asyncio.sleep(0, result={"target": "aftersales"}))

    await cli.cmd_module(argparse.Namespace(action="status", target="all", **args_common))
    await cli.cmd_module(argparse.Namespace(action="status", target="presales", **args_common))
    with pytest.raises(SystemExit):
        await cli.cmd_module(argparse.Namespace(action="start", target="operations", background=True, mode="once", **args_common))
    await cli.cmd_module(argparse.Namespace(action="start", target="presales", background=True, mode="daemon", **args_common))
    await cli.cmd_module(argparse.Namespace(action="start", target="presales", background=False, mode="daemon", **args_common))
    await cli.cmd_module(argparse.Namespace(action="start", target="operations", background=False, mode="daemon", **args_common))
    await cli.cmd_module(argparse.Namespace(action="start", target="aftersales", background=False, mode="daemon", **args_common))
    await cli.cmd_module(argparse.Namespace(action="stop", target="all", background=False, mode="daemon", **args_common))
    await cli.cmd_module(argparse.Namespace(action="restart", target="all", background=False, mode="daemon", **args_common))
    await cli.cmd_module(argparse.Namespace(action="recover", target="all", background=False, mode="daemon", **args_common))
    await cli.cmd_module(argparse.Namespace(action="logs", target="all", background=False, mode="daemon", **args_common))
    await cli.cmd_module(argparse.Namespace(action="unknown", target="all", background=False, mode="daemon", **args_common))

    assert any("Unknown workflow stage" in str(x.get("error", "")) for x in out if isinstance(x, dict))
    assert any(x.get("action") == "logs" for x in out if isinstance(x, dict))


@pytest.mark.asyncio
async def test_ws_messagepack_branches_and_preflight_cookie_merge(ws_enabled, monkeypatch):
    # cover additional MessagePack branches
    assert MessagePackDecoder(bytes([0xC0])).decode() is None
    assert MessagePackDecoder(bytes([0xC2])).decode() is False
    assert MessagePackDecoder(bytes([0xC3])).decode() is True
    assert MessagePackDecoder(bytes([0xCC, 0x05])).decode() == 5
    assert MessagePackDecoder(bytes([0xD0, 0xFF])).decode() == -1

    t = _ws_transport()

    class Ck:
        def __init__(self, n, v):
            self.name = n
            self.value = v

    class CM:
        async def __aenter__(self):
            class C:
                def __init__(self):
                    self.cookies = SimpleNamespace(jar=[Ck("cookie2", "b"), Ck("newk", "newv")])

                async def post(self, *_a, **_k):
                    class R:
                        def json(self):
                            return {"content": {"success": True}}

                    return R()

            return C()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr("src.modules.messages.ws_live.httpx.AsyncClient", lambda **_k: CM())
    ok = await t._preflight_has_login()
    assert ok is True
    assert t.cookies.get("newk") == "newv"


@pytest.mark.asyncio
async def test_ws_fetch_token_success_and_run_timeout_recv_exception(ws_enabled, monkeypatch):
    t = _ws_transport({"heartbeat_interval_seconds": 1, "heartbeat_timeout_seconds": 0, "reconnect_delay_seconds": 0.01})

    async def preflight_ok():
        return True

    t._preflight_has_login = preflight_ok

    class CM:
        async def __aenter__(self):
            class C:
                async def post(self, *_a, **_k):
                    class R:
                        def json(self):
                            return {"ret": ["SUCCESS::调用成功"], "data": {"accessToken": "token-ok"}}

                    return R()

            return C()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr("src.modules.messages.ws_live.httpx.AsyncClient", lambda **_k: CM())
    tok = await t._fetch_token()
    assert tok == "token-ok"

    calls = {"n": 0}

    class WS:
        async def recv(self):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("recv broken")
            await asyncio.sleep(0)
            return json.dumps({"code": 200, "headers": {"mid": "m"}})

        async def send(self, _x):
            return None

        async def close(self):
            return None

    async def connect(*_a, **_k):
        return WS()

    monkeypatch.setattr("src.modules.messages.ws_live.websockets.connect", connect)

    async def fake_sleep(_s):
        t._stop_event.set()
        return None

    async def noop():
        return None

    async def noop_p(_p):
        return None

    monkeypatch.setattr("src.modules.messages.ws_live.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(t, "_send_reg", noop)
    monkeypatch.setattr(t, "_ack_packet", noop_p)
    monkeypatch.setattr(t, "_handle_sync", noop_p)

    await t._run()
    assert t._last_disconnect_reason != ""


@pytest.mark.asyncio
async def test_ws_auth_hold_false_wait_path(ws_enabled, monkeypatch):
    t = _ws_transport({"auth_hold_until_cookie_update": False, "auth_failure_backoff_seconds": 0.01, "reconnect_delay_seconds": 0.01})

    async def connect(*_a, **_k):
        raise BrowserError("HTTP 401 forbidden")

    monkeypatch.setattr("src.modules.messages.ws_live.websockets.connect", connect)

    seen = {"wait": 0}

    async def wait_update(_timeout):
        seen["wait"] += 1
        t._stop_event.set()
        return True

    monkeypatch.setattr(t, "_wait_for_cookie_update", wait_update)
    await t._run()
    assert seen["wait"] == 1


def test_cli_main_unknown_and_keyboardinterrupt(monkeypatch):
    class P0:
        def parse_args(self):
            return argparse.Namespace(command="unknown")

        def print_help(self):
            return None

    monkeypatch.setattr("src.cli.build_parser", lambda: P0())
    with pytest.raises(SystemExit):
        cli.main()

    class P1:
        def parse_args(self):
            return argparse.Namespace(command="publish")

        def print_help(self):
            return None

    async def interrupted(_args):
        raise KeyboardInterrupt

    monkeypatch.setattr("src.cli.build_parser", lambda: P1())
    monkeypatch.setattr("src.cli.cmd_publish", interrupted)
    cli.main()

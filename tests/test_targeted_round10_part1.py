from __future__ import annotations

import argparse
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src import cli
from src.core import browser_client as bc
from src.core.error_handler import BrowserError
from src.modules.messages import ws_live


@pytest.mark.asyncio
async def test_cli_sla_benchmark_and_orders_missing(monkeypatch):
    class MsgSvc:
        reply_target_seconds = 2.5

        def __init__(self, controller=None):
            self.calls = 0

        async def process_session(self, session=None, dry_run=True, actor=""):
            self.calls += 1
            i = self.calls
            return {
                "session_id": session["session_id"],
                "latency_seconds": 0.001 * i,
                "within_target": i % 2 == 1,
                "is_quote": True,
                "quote_success": i % 2 == 0,
                "quote_fallback": i % 3 == 0,
                "quote_missing_fields": i % 5 == 0,
            }

    monkeypatch.setattr("src.modules.messages.service.MessagesService", MsgSvc)

    r1 = await cli._run_messages_sla_benchmark(
        count=3, concurrency=1, quote_ratio=1.0, quote_only=True, seed=1, slowest=2, warmup=1
    )
    assert r1["summary"]["samples"] == 3
    assert len(r1["slowest_samples"]) == 2

    r2 = await cli._run_messages_sla_benchmark(
        count=2, concurrency=4, quote_ratio=0.0, quote_only=False, seed=2, slowest=1, warmup=0
    )
    assert r2["config"]["concurrency"] == 4

    out = []
    monkeypatch.setattr("src.cli._json_out", lambda d: out.append(d))
    for act in ["after-sales", "takeover", "resume", "trace"]:
        await cli.cmd_orders(argparse.Namespace(action=act, db_path=None, order_id=None, issue_type=None, dry_run=False))
    assert all(item["error"] == "Specify --order-id" for item in out)


@pytest.mark.asyncio
async def test_cli_module_start_ops_and_aftersales(monkeypatch):
    class C:
        disconnected = False

        async def disconnect(self):
            self.disconnected = True

    class MsgSvc:
        def __init__(self, controller=None):
            self.closed = False

        async def close(self):
            self.closed = True

    class Worker:
        def __init__(self, message_service=None, config=None):
            self.config = config

        async def run_once(self, dry_run=False):
            return {"run": "once", "dry_run": dry_run}

        async def run_forever(self, dry_run=False, max_loops=None):
            return {"run": "daemon", "dry_run": dry_run, "max_loops": max_loops}

    client = C()
    monkeypatch.setattr("src.cli._messages_requires_browser_runtime", lambda: True)
    monkeypatch.setattr("src.core.browser_client.create_browser_client", AsyncMock(return_value=client))
    monkeypatch.setattr("src.modules.messages.service.MessagesService", MsgSvc)
    monkeypatch.setattr("src.modules.messages.workflow.WorkflowWorker", Worker)

    a = argparse.Namespace(mode="once", workflow_db="w", interval=1, limit=2, claim_limit=1, dry_run=False, max_loops=1)
    got = await cli._start_presales_module(a)
    assert got["target"] == "presales"

    class TaskType:
        POLISH = "polish"
        METRICS = "metrics"

    class Task:
        def __init__(self, task_type):
            self.task_type = task_type
            self.task_id = f"id-{task_type}"
            self.name = task_type

    class Scheduler:
        def __init__(self):
            self.started = False

        def list_tasks(self, enabled_only=False):
            return [Task(TaskType.POLISH), Task(TaskType.METRICS)]

        def create_polish_task(self, cron_expression="", max_items=0):
            return Task(TaskType.POLISH)

        def create_metrics_task(self, cron_expression=""):
            return Task(TaskType.METRICS)

        async def execute_task(self, task):
            return {"success": task.task_type == TaskType.POLISH}

        async def start(self):
            self.started = True

        async def stop(self):
            self.started = False

        def get_scheduler_status(self):
            return {"running": self.started}

    monkeypatch.setattr("src.modules.accounts.scheduler.TaskType", TaskType)
    monkeypatch.setattr("src.modules.accounts.scheduler.Scheduler", Scheduler)
    monkeypatch.setattr("src.core.config.get_config", lambda: SimpleNamespace(get_section=lambda *_a, **_k: {"polish": {}, "metrics": {}}))

    b = argparse.Namespace(
        init_default_tasks=True,
        skip_polish=False,
        skip_metrics=False,
        polish_cron=None,
        metrics_cron=None,
        polish_max_items=1,
        mode="once",
        max_loops=1,
        interval=0,
    )
    r_once = await cli._start_operations_module(b)
    assert r_once["executed_tasks"] == 2

    b.mode = "daemon"
    r_daemon = await cli._start_operations_module(b)
    assert r_daemon["loops"] == 1

    class OrderSvc:
        def __init__(self, db_path=None):
            pass

        def list_orders(self, **_k):
            return [
                {"order_id": "o1", "session_id": "", "manual_takeover": True},
                {"order_id": "o2", "session_id": "s2", "manual_takeover": False},
            ]

        def generate_after_sales_reply(self, issue_type="delay"):
            return f"reply-{issue_type}"

        def record_after_sales_followup(self, **_k):
            return None

        def get_summary(self):
            return {"sum": 1}

    class MsgReply:
        async def reply_to_session(self, sid, text):
            return sid == "s2" and bool(text)

        async def close(self):
            return None

    monkeypatch.setattr("src.modules.orders.service.OrderFulfillmentService", OrderSvc)
    cargs = argparse.Namespace(orders_db="x", limit=5, include_manual=True, issue_type="delay", dry_run=False)
    rr = await cli._run_aftersales_once(cargs, message_service=MsgReply())
    reasons = {d["reason"] for d in rr["details"]}
    assert "missing_session_id" in reasons and "sent" in reasons

    monkeypatch.setattr("src.modules.messages.service.MessagesService", lambda controller=None: MsgReply())
    monkeypatch.setattr("src.cli._run_aftersales_once", AsyncMock(return_value={"total_cases": 1, "success_cases": 1, "failed_cases": 0}))

    dargs = argparse.Namespace(mode="once", dry_run=True, max_loops=1, interval=0, orders_db="x")
    once = await cli._start_aftersales_module(dargs)
    assert once["mode"] == "once"

    dargs.mode = "daemon"
    da = await cli._start_aftersales_module(dargs)
    assert da["loops"] == 1


def base64_json(obj):
    import base64

    return base64.b64encode(json.dumps(obj).encode("utf-8")).decode("utf-8")


@pytest.mark.asyncio
async def test_ws_live_run_preflight_and_fetch_retry(monkeypatch):
    class WSModule:
        connect = None

    monkeypatch.setattr("src.modules.messages.ws_live.websockets", WSModule())
    t = ws_live.GoofishWsTransport(
        cookie_text="unb=10001; _m_h5_tk=tk_1; cookie2=c2",
        config={"token_max_attempts": 2, "heartbeat_interval_seconds": 1, "heartbeat_timeout_seconds": 1, "auth_hold_until_cookie_update": False},
    )

    class Ck:
        def __init__(self, name, value):
            self.name = name
            self.value = value

    class Ctx1:
        async def __aenter__(self):
            class Cli:
                cookies = SimpleNamespace(jar=[Ck("_m_h5_tk", "newtk_1")])

                async def post(self, *_a, **_k):
                    class R:
                        def json(self):
                            return {"content": {"success": True}}

                    return R()

            return Cli()

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr("src.modules.messages.ws_live.httpx.AsyncClient", lambda **_k: Ctx1())
    assert await t._preflight_has_login() is True
    assert t.cookies.get("_m_h5_tk") == "newtk_1"

    calls = {"n": 0}

    class Ctx2:
        async def __aenter__(self):
            class Cli:
                async def post(self, *_a, **_k):
                    calls["n"] += 1
                    class R:
                        def json(self_inner):
                            if calls["n"] == 1:
                                return {"ret": ["FAIL_SYS_TEMP::x"]}
                            return {"ret": ["SUCCESS::调用成功"], "data": {"accessToken": "AT"}}

                    return R()

            return Cli()

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr("src.modules.messages.ws_live.httpx.AsyncClient", lambda **_k: Ctx2())
    monkeypatch.setattr(t, "_preflight_has_login", AsyncMock(return_value=True))
    monkeypatch.setattr("src.modules.messages.ws_live.asyncio.sleep", AsyncMock())
    token = await t._fetch_token()
    assert token == "AT"

    sent = []

    class W:
        def __init__(self):
            self.step = 0

        async def recv(self):
            self.step += 1
            if self.step == 1:
                payload = base64_json({"1": {"2": "c1@goofish", "10": {"reminderContent": "hi", "senderUserId": "u2"}}})
                return json.dumps({"code": 200, "headers": {"mid": "m1", "sid": "s"}, "body": {"syncPushPackage": {"data": [{"data": payload}]}}})
            t._stop_event.set()
            raise asyncio.TimeoutError

        async def send(self, x):
            sent.append(json.loads(x))

        async def close(self):
            return None

    async def connect(*_a, **_k):
        return W()

    monkeypatch.setattr("src.modules.messages.ws_live.websockets.connect", connect)
    monkeypatch.setattr(t, "_send_reg", AsyncMock())
    await t._run()
    assert any(item.get("lwp") == "/!" for item in sent)
    assert any(item.get("code") == 200 for item in sent)


@pytest.mark.asyncio
async def test_browser_client_remaining_branches(monkeypatch):
    monkeypatch.setenv("OPENCLAW_GATEWAY_HOST", "h")
    monkeypatch.setenv("OPENCLAW_GATEWAY_PORT", "123")
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "tk")
    monkeypatch.setenv("OPENCLAW_BROWSER_PROFILE", "pf")
    c = bc.BrowserClient()
    assert c._headers()["Authorization"].startswith("Bearer")

    c._focus_tab = AsyncMock()
    c.get_snapshot = AsyncMock(return_value="abc")
    assert await c.wait_for_selector("p", "noquote", timeout=1) is False

    class Resp:
        def __init__(self, code):
            self.status_code = code

    class CtxOk:
        async def __aenter__(self):
            class Cli:
                async def get(self, *_a, **_k):
                    return Resp(401)

            return Cli()

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr("src.core.browser_client.httpx.AsyncClient", lambda **_k: CtxOk())
    assert await bc._probe_gateway_available({}) is True

    class CtxErr:
        async def __aenter__(self):
            raise RuntimeError("x")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr("src.core.browser_client.httpx.AsyncClient", lambda **_k: CtxErr())
    assert await bc._probe_gateway_available({}) is False

    class B:
        async def connect(self):
            return False

    monkeypatch.setattr("src.core.browser_client.BrowserClient", lambda cfg=None: B())
    with pytest.raises(BrowserError):
        await bc._create_gateway_client({})

    class Lite:
        def __init__(self, cfg):
            pass

        async def connect(self):
            return False

    import types

    mod = types.ModuleType("src.core.playwright_client")
    mod.PlaywrightBrowserClient = Lite
    monkeypatch.setitem(__import__("sys").modules, "src.core.playwright_client", mod)
    with pytest.raises(BrowserError):
        await bc._create_lite_client({})

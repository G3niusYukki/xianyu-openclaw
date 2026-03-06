from __future__ import annotations

import argparse
import io
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src import cli
from src.core import browser_client as bc
from src.core import startup_checks as sc
from src.core.error_handler import BrowserError
from src.core.service_container import LazyService, ServiceContainer, get_container, inject_service


def _module_args(**kwargs):
    base = dict(
        action="check",
        target="presales",
        skip_gateway=False,
        strict=False,
        background=False,
        mode="daemon",
        stop_timeout=1.0,
        tail_lines=5,
        workflow_db="wf.db",
        window_minutes=10,
        orders_db="orders.db",
        limit=5,
        max_loops=1,
        interval=0,
        init_default_tasks=False,
        skip_polish=False,
        skip_metrics=False,
        polish_cron="",
        metrics_cron="",
        polish_max_items=0,
        claim_limit=1,
        dry_run=False,
        issue_type="delay",
        include_manual=False,
    )
    base.update(kwargs)
    return argparse.Namespace(**base)


def test_cli_helpers_summary_and_process_alive_extra(monkeypatch, tmp_path):
    stream = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stream)
    cli._json_out({"ok": True})
    assert '"ok": true' in stream.getvalue().lower()

    doctor_report = {
        "checks": [
            {"name": "Python版本", "passed": True},
            {"name": "数据库", "passed": True},
            {"name": "配置文件", "passed": True},
            {"name": "闲鱼Cookie", "passed": True},
            {"name": "Legacy Browser Gateway", "passed": False},
            {"name": "Lite 浏览器驱动", "passed": False},
        ]
    }
    monkeypatch.setattr("src.core.startup_checks.resolve_runtime_mode", lambda: "pro")
    monkeypatch.setattr("src.cli._messages_transport_mode", lambda: "dom")
    pro_summary = cli._module_check_summary("operations", doctor_report)
    assert any(item.get("name") == "Legacy Browser Gateway" for item in pro_summary["blockers"])

    monkeypatch.setattr("src.core.startup_checks.resolve_runtime_mode", lambda: "lite")
    lite_summary = cli._module_check_summary("operations", doctor_report)
    assert any(item.get("name") == "Lite 浏览器驱动" for item in lite_summary["blockers"])

    monkeypatch.setattr(cli, "_MODULE_RUNTIME_DIR", tmp_path)
    assert cli._read_module_state("missing") == {}

    assert cli._process_alive(0) is False
    monkeypatch.setattr(cli.os, "kill", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert cli._process_alive(42) is False


@pytest.mark.asyncio
async def test_cli_windows_start_stop_cleanup_and_automation(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "_MODULE_RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(cli.os, "name", "nt", raising=False)
    monkeypatch.setattr(cli.subprocess, "CREATE_NEW_PROCESS_GROUP", 999, raising=False)

    popen_args = {}

    class Proc:
        pid = 1234

    def fake_popen(cmd, **kwargs):
        popen_args["cmd"] = cmd
        popen_args["kwargs"] = kwargs
        return Proc()

    monkeypatch.setattr(cli, "_read_module_state", lambda _t: {})
    monkeypatch.setattr(cli.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(cli, "_write_module_state", lambda *_a, **_k: None)
    started = cli._start_background_module("presales", _module_args())
    assert started["started"] is True
    assert popen_args["kwargs"]["creationflags"] == 999

    monkeypatch.setattr(cli, "_read_module_state", lambda _t: {"pid": 11})
    monkeypatch.setattr(cli, "_process_alive", lambda _p: True)
    monkeypatch.setattr(cli.os, "kill", lambda *_a, **_k: (_ for _ in ()).throw(OSError("sig failed")))
    sig_failed = cli._stop_background_module("presales")
    assert "signal_failed" in sig_failed["reason"]

    kill_calls = []
    monkeypatch.setattr(cli.os, "kill", lambda pid, sig: kill_calls.append((pid, sig)))
    monkeypatch.setattr(cli, "_process_alive", lambda _p: True)

    times = iter([0.0, 2.0])
    monkeypatch.setattr(cli.time, "time", lambda: next(times, 2.0))
    monkeypatch.setattr(cli.time, "sleep", lambda *_a, **_k: None)
    forced = cli._stop_background_module("presales", timeout_seconds=0.1)
    assert forced["forced"] is True
    assert kill_calls

    monkeypatch.setattr(cli, "_read_module_state", lambda _t: {"pid": 77, "log_file": "x.log", "started_at": "t"})
    monkeypatch.setattr(cli, "_process_alive", lambda _p: True)
    status = cli._module_process_status("presales")
    assert status["alive"] is True and status["pid"] == 77

    for ext in (".json", ".pid", ".lock"):
        (tmp_path / f"x{ext}").write_text("1", encoding="utf-8")

    original_unlink = Path.unlink

    def flaky_unlink(self, *args, **kwargs):
        if self.suffix == ".pid":
            raise OSError("blocked")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", flaky_unlink)
    cleared = cli._clear_module_runtime_state("x")
    assert len(cleared["removed"]) == 2

    class FakeSetup:
        def __init__(self, config_path):
            self.config_path = config_path

        def status(self):
            return {"status": "ok"}

        def apply(self, **kwargs):
            return kwargs

        def get_feishu_webhook(self):
            return "https://example/webhook"

    class FakeNotifier:
        def __init__(self, webhook_url):
            self.webhook_url = webhook_url

        async def send_text(self, _text):
            return False

    outs = []
    monkeypatch.setattr("src.modules.messages.setup.AutomationSetupService", FakeSetup)
    monkeypatch.setattr("src.modules.messages.notifications.FeishuNotifier", FakeNotifier)
    monkeypatch.setattr("src.cli._json_out", lambda d: outs.append(d))

    with pytest.raises(SystemExit):
        await cli.cmd_automation(
            argparse.Namespace(action="test-feishu", config_path="x", feishu_webhook="", message="msg")
        )

    await cli.cmd_automation(argparse.Namespace(action="mystery", config_path="x"))
    assert any("Unknown automation action" in str(item.get("error", "")) for item in outs if isinstance(item, dict))


@pytest.mark.asyncio
async def test_cli_module_growth_operations_and_aftersales_extra(monkeypatch):
    outputs = []
    monkeypatch.setattr("src.cli._json_out", lambda d: outputs.append(d))

    monkeypatch.setattr("src.core.doctor.run_doctor", lambda **_k: {"checks": []})
    monkeypatch.setattr("src.cli._module_check_summary", lambda **_k: {"ready": False, "blockers": []})
    with pytest.raises(SystemExit):
        await cli.cmd_module(_module_args(action="check", strict=True, target="presales"))

    with pytest.raises(SystemExit):
        await cli.cmd_module(_module_args(action="start", target="all", background=True, mode="once"))

    monkeypatch.setattr("src.cli._stop_background_module", lambda **_k: {"stopped": True})
    monkeypatch.setattr("src.cli._start_background_module", lambda **_k: {"started": True})
    await cli.cmd_module(_module_args(action="restart", target="presales"))
    assert any(item.get("target") == "presales" for item in outputs if isinstance(item, dict))

    monkeypatch.setattr("src.cli._module_logs", lambda **_k: {"target": "presales", "lines": ["x"]})
    await cli.cmd_module(_module_args(action="logs", target="presales", tail_lines=1))
    assert any(item.get("lines") == ["x"] for item in outputs if isinstance(item, dict))

    class Growth:
        def __init__(self, db_path=None):
            self.db_path = db_path

    monkeypatch.setattr("src.modules.growth.service.GrowthService", Growth)
    await cli.cmd_growth(
        argparse.Namespace(
            action="compare",
            db_path="",
            experiment_id="",
            from_stage="",
            to_stage="",
            strategy_type="",
            version="",
            active=False,
            baseline=False,
            subject_id="",
            variants="",
            stage="",
            variant="",
            days=0,
            bucket="",
        )
    )
    assert any(item.get("error") == "Specify --experiment-id" for item in outputs if isinstance(item, dict))

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

    from src.modules.accounts import scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module, "TaskType", TaskType)
    monkeypatch.setattr(scheduler_module, "Scheduler", Scheduler)
    monkeypatch.setattr("src.core.config.get_config", lambda: SimpleNamespace(get_section=lambda *_a, **_k: {}))

    no_init = cli._init_default_operation_tasks(_module_args(init_default_tasks=False))
    assert no_init["created"] == []

    init_args = _module_args(
        init_default_tasks=True,
        skip_polish=False,
        skip_metrics=False,
        polish_cron="",
        metrics_cron="",
        polish_max_items=3,
    )
    initialized = cli._init_default_operation_tasks(init_args)
    assert isinstance(initialized["created"], list)

    once_args = _module_args(
        mode="once",
        init_default_tasks=True,
        skip_polish=True,
        skip_metrics=True,
    )
    once = await cli._start_operations_module(once_args)
    assert once["executed_tasks"] == 0

    sleep_calls = []

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    monkeypatch.setattr("src.cli.asyncio.sleep", fake_sleep)
    daemon_args = _module_args(mode="daemon", max_loops=2, interval=0, init_default_tasks=True)
    daemon = await cli._start_operations_module(daemon_args)
    assert daemon["loops"] == 2
    assert sleep_calls

    class OrderService:
        def __init__(self, db_path=None):
            self.db_path = db_path

        def list_orders(self, **_k):
            return [{"order_id": "o1", "session_id": "s1", "manual_takeover": False}]

        def generate_after_sales_reply(self, issue_type="delay"):
            return f"reply-{issue_type}"

        def record_after_sales_followup(self, **_k):
            return None

        def get_summary(self):
            return {"ok": True}

    monkeypatch.setattr("src.modules.orders.service.OrderFulfillmentService", OrderService)

    dry_run_batch = await cli._run_aftersales_once(
        argparse.Namespace(orders_db="x", limit=2, include_manual=False, issue_type="delay", dry_run=True),
        message_service=None,
    )
    assert dry_run_batch["details"][0]["reason"] == "dry_run"

    no_sender_batch = await cli._run_aftersales_once(
        argparse.Namespace(orders_db="x", limit=2, include_manual=False, issue_type="delay", dry_run=False),
        message_service=None,
    )
    assert no_sender_batch["details"][0]["reason"] == "message_service_unavailable"

    class Client:
        def __init__(self):
            self.disconnected = False

        async def disconnect(self):
            self.disconnected = True

    class MsgService:
        def __init__(self, controller=None):
            self.controller = controller
            self.closed = False

        async def close(self):
            self.closed = True

    async def run_once_stub(args, message_service=None):
        return {"total_cases": 1, "success_cases": 1, "failed_cases": 0}

    monkeypatch.setattr("src.cli._messages_requires_browser_runtime", lambda: True)
    monkeypatch.setattr("src.core.browser_client.create_browser_client", AsyncMock(return_value=Client()))
    monkeypatch.setattr("src.modules.messages.service.MessagesService", MsgService)
    monkeypatch.setattr("src.cli._run_aftersales_once", AsyncMock(side_effect=run_once_stub))

    once_real = await cli._start_aftersales_module(
        argparse.Namespace(mode="once", dry_run=False, max_loops=1, interval=0, orders_db="x")
    )
    assert once_real["mode"] == "once"

    sleep_calls.clear()
    daemon_real = await cli._start_aftersales_module(
        argparse.Namespace(mode="daemon", dry_run=False, max_loops=2, interval=0, orders_db="x")
    )
    assert daemon_real["loops"] == 2

    class Worker:
        def __init__(self, message_service=None, config=None):
            self.message_service = message_service
            self.config = config

        async def run_forever(self, dry_run=False, max_loops=0):
            return {"dry_run": dry_run, "max_loops": max_loops}

        async def run_once(self, dry_run=False):
            return {"dry_run": dry_run}

    monkeypatch.setattr("src.modules.messages.workflow.WorkflowWorker", Worker)
    presales = await cli._start_presales_module(
        argparse.Namespace(
            mode="daemon",
            workflow_db="wf.db",
            interval=1,
            limit=2,
            claim_limit=1,
            dry_run=True,
            max_loops=1,
        )
    )
    assert presales["target"] == "presales"


def test_startup_checks_and_service_container_extra(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCLAW_RUNTIME", "pro")
    assert sc.resolve_runtime_mode() == "pro"

    monkeypatch.delenv("OPENCLAW_RUNTIME", raising=False)
    monkeypatch.setattr("src.core.config.get_config", lambda: SimpleNamespace(get=lambda *_a, **_k: "lite"))
    assert sc.resolve_runtime_mode() == "lite"

    monkeypatch.setenv("OPENCLAW_RUNTIME", "invalid")
    monkeypatch.setattr("src.core.config.get_config", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert sc.resolve_runtime_mode() == "auto"

    fake_httpx = types.SimpleNamespace()

    class ConnectError(RuntimeError):
        pass

    fake_httpx.ConnectError = ConnectError
    fake_httpx.get = lambda *_a, **_k: SimpleNamespace(status_code=200)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
    assert sc.check_gateway_reachable().passed is True

    fake_httpx.get = lambda *_a, **_k: SimpleNamespace(status_code=503)
    assert sc.check_gateway_reachable().passed is False

    def _raise_connect(*_a, **_k):
        raise ConnectError("no")

    fake_httpx.get = _raise_connect
    assert sc.check_gateway_reachable().passed is False

    fake_httpx.get = lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("bad"))
    assert sc.check_gateway_reachable().passed is False

    db_path = tmp_path / "db" / "agent.db"
    monkeypatch.setattr("src.core.config.get_config", lambda: SimpleNamespace(database={"path": str(db_path)}))
    assert sc.check_database_writable().passed is True

    monkeypatch.setattr(sc.sqlite3, "connect", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("db down")))
    assert sc.check_database_writable().passed is False

    monkeypatch.setattr(sc.os, "access", lambda p, mode: not str(p).endswith("logs"))
    assert sc.check_data_directories().passed is False

    monkeypatch.setenv("OPENAI_API_KEY", "x" * 20)
    assert sc.check_ai_config().passed is True
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    assert sc.check_ai_config().passed is False

    monkeypatch.setenv("XIANYU_COOKIE_1", "x" * 30)
    assert sc.check_cookies_configured().passed is True
    monkeypatch.setenv("XIANYU_COOKIE_1", "")
    assert sc.check_cookies_configured().passed is False

    monkeypatch.setenv("XIANYU_COOKIE_1", "")
    assert sc.check_cookie_expiration().passed is False
    monkeypatch.setenv("XIANYU_COOKIE_1", "token=1")
    assert sc.check_cookie_expiration().passed is False
    monkeypatch.setenv("XIANYU_COOKIE_1", "unb=1;cookie2=x")
    assert sc.check_cookie_expiration().passed is True

    monkeypatch.setitem(sys.modules, "playwright", object())
    assert sc.check_lite_browser_dependency().passed is True

    original_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "playwright":
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    assert sc.check_lite_browser_dependency().passed is False

    monkeypatch.setattr(sc, "resolve_runtime_mode", lambda: "pro")
    monkeypatch.setattr(sc, "check_runtime_mode", lambda: sc.StartupCheckResult("浏览器运行时", True, "pro", False))
    monkeypatch.setattr(sc, "check_python_version", lambda: sc.StartupCheckResult("Python版本", True, "ok", True))
    monkeypatch.setattr(sc, "check_data_directories", lambda: sc.StartupCheckResult("数据目录", True, "ok", True))
    monkeypatch.setattr(sc, "check_database_writable", lambda: sc.StartupCheckResult("数据库", True, "ok", True))
    monkeypatch.setattr(sc, "check_ai_config", lambda: sc.StartupCheckResult("AI服务", True, "ok", False))
    monkeypatch.setattr(sc, "check_cookies_configured", lambda: sc.StartupCheckResult("闲鱼Cookie", True, "ok", True))
    monkeypatch.setattr(sc, "check_cookie_expiration", lambda: sc.StartupCheckResult("Cookie有效性", True, "ok", False))
    monkeypatch.setattr(sc, "check_gateway_reachable", lambda: sc.StartupCheckResult("Legacy Browser Gateway", False, "down", True))
    monkeypatch.setattr(sc, "check_lite_browser_dependency", lambda: sc.StartupCheckResult("Lite 浏览器驱动", True, "ok", True))

    skip_browser = sc.run_all_checks(skip_browser=True)
    assert all(item.name != "Legacy Browser Gateway" for item in skip_browser)

    pro_checks = sc.run_all_checks(skip_browser=False)
    assert any(item.name == "Legacy Browser Gateway" for item in pro_checks)

    monkeypatch.setattr(sc, "resolve_runtime_mode", lambda: "lite")
    lite_checks = sc.run_all_checks(skip_browser=False)
    assert any(item.name == "Lite 浏览器驱动" for item in lite_checks)

    monkeypatch.setattr(sc, "resolve_runtime_mode", lambda: "auto")
    monkeypatch.setattr(sc, "check_gateway_reachable", lambda: sc.StartupCheckResult("Legacy Browser Gateway", False, "down", True))
    auto_checks = sc.run_all_checks(skip_browser=False)
    assert any(item.name == "Lite 浏览器驱动" for item in auto_checks)

    assert sc.print_startup_report([sc.StartupCheckResult("A", True, "ok", True)]) is True
    assert sc.print_startup_report([sc.StartupCheckResult("B", False, "bad", True)]) is False

    class Svc:
        def __init__(self):
            self.n = 1

    container = ServiceContainer()
    container.clear()

    with pytest.raises(ValueError):
        container.register(Svc)

    container.register(Svc, factory=Svc, singleton=False)
    assert container.get(Svc) is not container.get(Svc)

    inst = Svc()
    container.set(Svc, inst)
    assert container.has(Svc) is True

    @container.inject(Svc)
    def _use(x):
        return x.n

    assert _use() == 1

    container.clear()

    @container.inject(Svc)
    def _need_service(x):
        return x

    with pytest.raises(ValueError):
        _need_service()

    lazy = LazyService(Svc, container)
    assert lazy() is None

    container.register(Svc, instance=Svc())

    @inject_service(Svc)
    def _global_use(service, value):
        return service.n + value

    assert _global_use(2) == 3

    container.clear()

    @inject_service(Svc)
    def _global_missing(service):
        return service

    with pytest.raises(ValueError):
        _global_missing()

    assert isinstance(get_container(), ServiceContainer)


@pytest.mark.asyncio
async def test_browser_client_remaining_branches(monkeypatch):
    c = bc.BrowserClient({"delay_min": 0.0, "delay_max": 0.0})
    assert c.config.gateway_base_url.startswith("http://")

    assert await c.is_connected() is False
    c.state = bc.BrowserState.CONNECTED
    c._client = SimpleNamespace(get=AsyncMock(side_effect=RuntimeError("x")))
    assert await c.is_connected() is False

    c.connect = AsyncMock(return_value=True)
    assert await c.ensure_connected() is True

    c.ensure_connected = AsyncMock(return_value=False)
    with pytest.raises(BrowserError):
        await c.new_page()

    c._client = SimpleNamespace(post=AsyncMock(return_value=SimpleNamespace(status_code=200, json=lambda: {"ok": 1}, text="")))
    assert await c._act("x") == {"ok": 1}

    c._focus_tab = AsyncMock()
    c._client.post = AsyncMock(return_value=SimpleNamespace(status_code=200))
    sleep_calls = []

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    monkeypatch.setattr("src.core.browser_client.asyncio.sleep", fake_sleep)
    assert await c.navigate("p", "https://example.com", wait_load=True) is True
    assert sleep_calls

    c._client.get = AsyncMock(side_effect=RuntimeError("snap"))
    assert await c.get_snapshot("p") is None

    c.find_elements = AsyncMock(return_value=[])
    assert await c.find_element("p", "css=.x") is None

    c._client.post = AsyncMock(return_value=SimpleNamespace(status_code=200, json=lambda: {}, is_success=True))
    c.click = AsyncMock(return_value=True)
    assert await c.upload_file("p", "#sel", "/tmp/a.jpg") is True
    assert await c.upload_files("p", "#sel", ["/tmp/a.jpg", "/tmp/b.jpg"]) is True

    c._client.get = AsyncMock(side_effect=RuntimeError("cookies"))
    assert await c.get_cookies() == []

    c._client.post = AsyncMock(return_value=SimpleNamespace(status_code=200, json=lambda: {}))
    await c.set_cookies_for_domain("bad name\t1\nok\t2\nkv=3")
    assert c._client.post.await_count == 1

    c._client.get = AsyncMock(return_value=SimpleNamespace(status_code=500, json=lambda: []))
    assert await c._list_tabs() == []

    monkeypatch.setenv("OPENCLAW_RUNTIME", "invalid")
    monkeypatch.setattr("src.core.browser_client.load_dotenv", lambda **_k: None)
    assert bc._resolve_runtime({"runtime": "pro"}) == "pro"

    sentinel = object()
    original_create_lite = bc._create_lite_client
    monkeypatch.setattr("src.core.browser_client._resolve_runtime", lambda _cfg: "lite")
    monkeypatch.setattr("src.core.browser_client._create_lite_client", AsyncMock(return_value=sentinel))
    assert await bc.create_browser_client({}) is sentinel
    monkeypatch.setattr("src.core.browser_client._create_lite_client", original_create_lite)

    class GatewayClient:
        async def connect(self):
            return True

    monkeypatch.setattr("src.core.browser_client.BrowserClient", lambda _cfg=None: GatewayClient())
    assert isinstance(await bc._create_gateway_client({}), GatewayClient)

    class LiteClient:
        def __init__(self, _cfg):
            self.cfg = _cfg

        async def connect(self):
            return True

    fake_mod = types.ModuleType("src.core.playwright_client")
    fake_mod.PlaywrightBrowserClient = LiteClient
    monkeypatch.setitem(sys.modules, "src.core.playwright_client", fake_mod)
    assert isinstance(await bc._create_lite_client({"runtime": "lite"}), LiteClient)

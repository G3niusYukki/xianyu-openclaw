from __future__ import annotations

import argparse
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src import cli
from src.core.browser_client import BrowserClient
from src.core.error_handler import BrowserError
from src.modules.messages.ws_live import GoofishWsTransport, MessagePackDecoder


@pytest.fixture
def ws_enabled(monkeypatch):
    monkeypatch.setattr("src.modules.messages.ws_live.websockets", object())


def _ns(**kwargs):
    base = dict(
        max_loops=0,
        interval=0,
        limit=3,
        claim_limit=2,
        workflow_db="",
        dry_run=False,
        init_default_tasks=False,
        skip_polish=False,
        skip_metrics=False,
        polish_max_items=0,
        polish_cron="",
        metrics_cron="",
        issue_type="delay",
        orders_db="",
        include_manual=False,
    )
    base.update(kwargs)
    return argparse.Namespace(**base)


def test_cli_module_helpers_runtime_files_and_commands(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_MODULE_RUNTIME_DIR", tmp_path)

    p = cli._module_state_path("presales")
    l = cli._module_log_path("presales")
    assert p.parent == tmp_path
    assert l.parent == tmp_path

    args = _ns(max_loops=2, interval=9, workflow_db="wf.db", dry_run=True)
    cmd = cli._build_module_start_command("presales", args)
    assert "--claim-limit" in cmd and "--workflow-db" in cmd and "--dry-run" in cmd

    args2 = _ns(init_default_tasks=True, skip_polish=True, skip_metrics=True, polish_max_items=8, polish_cron="* * * * *", metrics_cron="0 * * * *")
    cmd2 = cli._build_module_start_command("operations", args2)
    assert "--init-default-tasks" in cmd2 and "--skip-polish" in cmd2 and "--metrics-cron" in cmd2

    args3 = _ns(orders_db="orders.db", include_manual=True, dry_run=True, issue_type="refund")
    cmd3 = cli._build_module_start_command("aftersales", args3)
    assert "--orders-db" in cmd3 and "--include-manual" in cmd3 and "--issue-type" in cmd3

    assert cli._resolve_workflow_state("follow-up") is not None
    assert cli._resolve_workflow_state("unknown") is None

    (tmp_path / "presales.json").write_text("{bad", encoding="utf-8")
    assert cli._read_module_state("presales") == {}
    cli._write_module_state("presales", {"pid": 1})
    assert cli._read_module_state("presales")["pid"] == 1


def test_cli_start_stop_logs_and_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_MODULE_RUNTIME_DIR", tmp_path)

    monkeypatch.setattr(cli, "_read_module_state", lambda _t: {"pid": 99})
    monkeypatch.setattr(cli, "_process_alive", lambda _p: True)
    already = cli._start_background_module("presales", _ns())
    assert already["reason"] == "already_running"

    class P:
        pid = 4321

    monkeypatch.setattr(cli, "_read_module_state", lambda _t: {})
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *a, **k: P())
    monkeypatch.setattr(cli, "_write_module_state", lambda *_a, **_k: None)
    started = cli._start_background_module("presales", _ns())
    assert started["started"] is True and started["pid"] == 4321

    assert cli._stop_background_module("x")["reason"] == "not_running"
    monkeypatch.setattr(cli, "_read_module_state", lambda _t: {"pid": 77})
    monkeypatch.setattr(cli, "_process_alive", lambda _p: False)
    assert cli._stop_background_module("x")["reason"] == "pid_not_alive"

    calls = {"n": 0}

    def _alive(_pid):
        calls["n"] += 1
        return calls["n"] < 99

    monkeypatch.setattr(cli, "_process_alive", _alive)
    monkeypatch.setattr(cli.os, "killpg", lambda *_a, **_k: None)
    monkeypatch.setattr(cli.time, "sleep", lambda *_a, **_k: None)
    stopped = cli._stop_background_module("x", timeout_seconds=0.01)
    assert stopped.get("forced") is True or stopped.get("stopped") is True

    assert cli._module_logs("x")["lines"] == []
    log = tmp_path / "x.log"
    log.write_text("a\nb\nc", encoding="utf-8")
    assert cli._module_logs("x", tail_lines=2)["lines"] == ["b", "c"]

    for ext in (".json", ".pid", ".lock"):
        (tmp_path / f"x{ext}").write_text("1", encoding="utf-8")
    cleared = cli._clear_module_runtime_state("x")
    assert len(cleared["removed"]) == 3


def test_ws_messagepack_more_tags():
    assert MessagePackDecoder(b"\xc4\x03abc").decode() == b"abc"
    assert MessagePackDecoder(b"\xc5\x00\x03abc").decode() == b"abc"
    assert MessagePackDecoder(b"\xc6\x00\x00\x00\x03abc").decode() == b"abc"
    assert MessagePackDecoder(b"\xda\x00\x03hey").decode() == "hey"
    assert MessagePackDecoder(b"\xdb\x00\x00\x00\x03hey").decode() == "hey"
    assert MessagePackDecoder(b"\xdc\x00\x02\x01\x02").decode() == [1, 2]
    assert MessagePackDecoder(b"\xdd\x00\x00\x00\x02\x01\x02").decode() == [1, 2]
    assert MessagePackDecoder(b"\xde\x00\x01\xa1a\x01").decode() == {"a": 1}
    assert MessagePackDecoder(b"\xdf\x00\x00\x00\x01\xa1a\x01").decode() == {"a": 1}


@pytest.mark.asyncio
async def test_ws_preflight_and_run_typeerror_fallback(ws_enabled, monkeypatch):
    t = GoofishWsTransport(cookie_text="unb=1; _m_h5_tk=tk_1", config={"heartbeat_interval_seconds": 0, "heartbeat_timeout_seconds": 0})

    class Cookie:
        def __init__(self, n, v):
            self.name = n
            self.value = v

    class Ctx:
        def __init__(self, payload):
            self.payload = payload
            self.cookies = SimpleNamespace(jar=[Cookie("newk", "newv")])

        async def __aenter__(self):
            class C:
                pass

            c = C()

            async def post(*_a, **_k):
                return SimpleNamespace(json=lambda: self.payload)

            c.post = post
            c.cookies = self.cookies
            return c

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr("src.modules.messages.ws_live.httpx.AsyncClient", lambda **_k: Ctx({"content": {"success": True}}))
    ok = await t._preflight_has_login()
    assert ok is True and "newk" in t.cookies

    monkeypatch.setattr("src.modules.messages.ws_live.httpx.AsyncClient", lambda **_k: Ctx({"content": {"success": False}}))
    assert await t._preflight_has_login() is False

    calls = {"n": 0}

    class WS:
        async def recv(self):
            await asyncio.sleep(0)
            return json.dumps({"code": 200, "headers": {"mid": "m"}})

        async def send(self, _x):
            return None

        async def close(self):
            return None

    async def fake_connect(*_a, **kwargs):
        calls["n"] += 1
        if "extra_headers" in kwargs:
            raise TypeError("unexpected argument extra_headers")
        return WS()

    monkeypatch.setattr("src.modules.messages.ws_live.websockets", SimpleNamespace(connect=fake_connect))
    monkeypatch.setattr(t, "_send_reg", AsyncMock(return_value=None))
    monkeypatch.setattr(t, "_handle_sync", AsyncMock(return_value=None))
    monkeypatch.setattr(t, "_ack_packet", AsyncMock(return_value=None))

    async def stop_sleep(_delay):
        t._stop_event.set()
        return None

    monkeypatch.setattr("src.modules.messages.ws_live.asyncio.sleep", stop_sleep)
    await t._run()
    assert calls["n"] >= 2


@pytest.mark.asyncio
async def test_browser_client_extra_branches(monkeypatch):
    c = BrowserClient({"delay_min": 0.0, "delay_max": 0.0})
    c._client = SimpleNamespace(get=AsyncMock(), post=AsyncMock(), delete=AsyncMock())
    c.ensure_connected = AsyncMock(return_value=True)
    c._focus_tab = AsyncMock(return_value=None)

    c._client.post.return_value = SimpleNamespace(status_code=200, json=lambda: {"id": "fallback"})
    assert await c.new_page() == "fallback"

    c._client.delete.side_effect = RuntimeError("x")
    assert await c.close_page("p") is False

    c._active_tab_id = "same"
    c._client.post.reset_mock()
    await c._focus_tab("same")
    c._client.post.assert_not_called()

    c._client.get.return_value = SimpleNamespace(status_code=500, text="", json=lambda: {})
    assert await c.get_snapshot("p") is None

    assert await c.find_elements("p", "css=.x") == []

    c.get_snapshot = AsyncMock(return_value="abc")
    assert await c.wait_for_selector("p", "css=.x", timeout=1) is False

    c._list_tabs = AsyncMock(return_value=[{"targetId": "p", "url": "https://x"}])
    assert await c.wait_for_url("p", "nomatch", timeout=1) is False

    c._client.post.return_value = SimpleNamespace(status_code=500, text="e", json=lambda: {})
    assert await c.execute_script("p", "1") is None

    c._client.post.side_effect = RuntimeError("e")
    assert await c.handle_dialog("p") is False


@pytest.mark.asyncio
async def test_browser_runtime_resolve_and_probe(monkeypatch):
    monkeypatch.delenv("OPENCLAW_RUNTIME", raising=False)
    monkeypatch.setattr("src.core.browser_client.load_dotenv", lambda **_k: None)

    class Cfg:
        def get(self, *_a, **_k):
            return "pro"

    monkeypatch.setattr("src.core.config.get_config", lambda: Cfg())
    from src.core.browser_client import _probe_gateway_available, _resolve_runtime

    assert _resolve_runtime({}) == "pro"

    class Ctx:
        async def __aenter__(self):
            class CC:
                async def get(self, *_a, **_k):
                    return SimpleNamespace(status_code=401)

            return CC()

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr("src.core.browser_client.httpx.AsyncClient", lambda **_k: Ctx())
    assert await _probe_gateway_available({}) is True

    class BadCtx:
        async def __aenter__(self):
            raise RuntimeError("x")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr("src.core.browser_client.httpx.AsyncClient", lambda **_k: BadCtx())
    assert await _probe_gateway_available({}) is False

    class Lite:
        def __init__(self, _cfg):
            self.connect = AsyncMock(return_value=False)

    monkeypatch.setattr("src.core.playwright_client.PlaywrightBrowserClient", Lite)
    with pytest.raises(BrowserError):
        await __import__("src.core.browser_client", fromlist=["_create_lite_client"])._create_lite_client({})

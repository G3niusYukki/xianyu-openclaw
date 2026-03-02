from __future__ import annotations

import argparse
import asyncio
import types

import pytest

from src import cli
from src.modules.quote.engine import AutoQuoteEngine
from src.modules.quote.models import QuoteRequest, QuoteResult


def _q(provider: str = "rule") -> QuoteResult:
    return QuoteResult(provider=provider, base_fee=10.0, surcharges={}, total_fee=10.0, explain={})


def test_cli_misc_missing_branches(monkeypatch):
    monkeypatch.setattr(cli.os, "kill", lambda *_a, **_k: None)
    assert cli._process_alive(123) is True

    monkeypatch.setattr(cli, "_read_module_state", lambda _t: {"pid": 66})
    monkeypatch.setattr(cli, "_process_alive", lambda _p: True)

    def _killpg(_pid, sig):
        if sig == cli.signal.SIGKILL:
            raise RuntimeError("boom")

    monkeypatch.setattr(cli.os, "killpg", _killpg)
    monkeypatch.setattr(cli.time, "sleep", lambda *_a, **_k: None)
    stopped = cli._stop_background_module("x", timeout_seconds=0.01)
    assert stopped.get("stopped") is False
    assert stopped.get("forced") is True

    assert cli._resolve_workflow_state(None) is None


@pytest.mark.asyncio
async def test_init_default_operation_tasks_and_dryrun_sleep(monkeypatch):
    class TaskType:
        POLISH = "POLISH"
        METRICS = "METRICS"

    class _Task:
        def __init__(self, task_id, task_type, name):
            self.task_id = task_id
            self.task_type = task_type
            self.name = name

    class _Scheduler:
        def list_tasks(self):
            return []

        def create_polish_task(self, cron_expression, max_items):
            assert cron_expression == "1 2 * * *"
            assert max_items == 66
            return _Task("p1", TaskType.POLISH, "polish")

        def create_metrics_task(self, cron_expression):
            assert cron_expression == "3 4 * * *"
            return _Task("m1", TaskType.METRICS, "metrics")

        def get_scheduler_status(self):
            return {"ok": True}

    import sys

    sys.modules["src.modules.accounts.scheduler"] = types.SimpleNamespace(Scheduler=_Scheduler, TaskType=TaskType)

    monkeypatch.setattr(
        "src.core.config.get_config",
        lambda: types.SimpleNamespace(
            get_section=lambda *_a, **_k: {
                "polish": {"cron": "1 2 * * *"},
                "metrics": {"cron": "3 4 * * *"},
            }
        ),
    )

    out = cli._init_default_operation_tasks(
        argparse.Namespace(
            init_default_tasks=True,
            skip_polish=False,
            skip_metrics=False,
            polish_cron="",
            metrics_cron="",
            polish_max_items=66,
        )
    )
    assert len(out["created"]) == 2

    calls = {"sleep": 0}

    async def fake_run_once(_args, message_service=None):
        return {"total_cases": 1, "success_cases": 1, "failed_cases": 0}

    async def fake_sleep(_delay):
        calls["sleep"] += 1
        return None

    monkeypatch.setattr(cli, "_run_aftersales_once", fake_run_once)
    monkeypatch.setattr(cli.asyncio, "sleep", fake_sleep)

    args = argparse.Namespace(mode="daemon", dry_run=True, max_loops=2, interval=0, orders_db="", once=False)
    result = await cli._start_aftersales_module(args)
    assert result["loops"] == 2
    assert calls["sleep"] >= 1


@pytest.mark.asyncio
async def test_cmd_module_check_single_target_return(monkeypatch):
    monkeypatch.setattr("src.core.doctor.run_doctor", lambda **_k: {"summary": {}, "next_steps": []})
    monkeypatch.setattr(cli, "_module_check_summary", lambda **_k: {"ready": False, "target": "presales"})
    payloads = []
    monkeypatch.setattr(cli, "_json_out", lambda x: payloads.append(x))

    await cli.cmd_module(argparse.Namespace(action="check", target="presales", skip_gateway=False, strict=False))
    assert payloads and payloads[-1]["target"] == "presales"


@pytest.mark.asyncio
async def test_quote_engine_remote_only_success_resets_circuit():
    e = AutoQuoteEngine({"mode": "remote_only", "retry_times": 1})
    e._remote_failures = 5
    e._circuit_open_until = 9999999999.0
    e._is_circuit_open = lambda: False

    async def remote_ok(_req, timeout_ms=0):
        return _q("remote")

    e.remote_provider.get_quote = remote_ok

    got = await e._quote_with_fallback(QuoteRequest("A", "B", 1.0))
    assert got.provider == "remote"
    assert e._remote_failures == 0
    assert e._circuit_open_until == 0.0


@pytest.mark.asyncio
async def test_quote_engine_api_parallel_api_done_with_exception_falls_back(monkeypatch):
    e = AutoQuoteEngine({"mode": "api_cost_plus_markup", "api_fallback_to_table_parallel": True, "api_prefer_max_wait_seconds": 0.01})

    async def api_fail_late(_req, timeout_ms=0):
        await asyncio.sleep(0.02)
        raise RuntimeError("api-late-fail")

    async def table_ok(_req, timeout_ms=0):
        await asyncio.sleep(0.03)
        return _q("table")

    e.api_cost_provider.get_quote = api_fail_late
    e.cost_table_provider.get_quote = table_ok

    async def no_done_wait(*_a, **_k):
        return set(), set()

    monkeypatch.setattr("src.modules.quote.engine.asyncio.wait", no_done_wait)

    got = await e._quote_api_cost_plus_markup(QuoteRequest("A", "B", 1.0))
    assert got.provider == "table"
    assert got.fallback_used is True
    assert got.explain.get("fallback_reason") in {"api_failed_after_wait", "api_failed_after_table_ready"}


@pytest.mark.asyncio
async def test_quote_engine_api_parallel_finally_cancels_pending_tasks(monkeypatch):
    e = AutoQuoteEngine({"mode": "api_cost_plus_markup", "api_fallback_to_table_parallel": True})

    never = asyncio.Event()

    async def api_never(_req, timeout_ms=0):
        await never.wait()
        return _q("api")

    async def table_never(_req, timeout_ms=0):
        await never.wait()
        return _q("table")

    e.api_cost_provider.get_quote = api_never
    e.cost_table_provider.get_quote = table_never

    async def boom_wait(*_a, **_k):
        raise RuntimeError("wait-broken")

    monkeypatch.setattr("src.modules.quote.engine.asyncio.wait", boom_wait)

    with pytest.raises(RuntimeError, match="wait-broken"):
        await e._quote_api_cost_plus_markup(QuoteRequest("A", "B", 1.0))

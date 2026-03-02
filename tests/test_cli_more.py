from __future__ import annotations

import argparse

import pytest

from src import cli


def test_pct_and_pick_message(monkeypatch):
    assert cli._pct([], 0.5) == 0
    assert cli._pct([1, 9, 3], 0.5) == 3

    class R:
        def random(self):
            return 0.1

        def choice(self, seq):
            return seq[0]

    r = R()
    assert cli._pick_bench_message(r, quote_ratio=1.0, quote_only=False)
    assert cli._pick_bench_message(r, quote_ratio=0.0, quote_only=True)


def test_messages_transport_mode_invalid(monkeypatch):
    class C:
        def get_section(self, *_args, **_kwargs):
            return {"transport": "invalid"}

    monkeypatch.setattr("src.core.config.get_config", lambda: C())
    assert cli._messages_transport_mode() == "dom"
    assert cli._messages_requires_browser_runtime() is True


@pytest.mark.asyncio
async def test_cmd_messages_unknown_action(monkeypatch):
    out = []
    monkeypatch.setattr("src.cli._json_out", lambda data: out.append(data))
    await cli.cmd_messages(argparse.Namespace(action="unknown"))
    assert "Unknown messages action" in out[-1]["error"]


def test_main_without_command(monkeypatch):
    parser = cli.build_parser()

    class P:
        def parse_args(self):
            return argparse.Namespace(command=None)

        def print_help(self):
            return None

    monkeypatch.setattr("src.cli.build_parser", lambda: P())
    with pytest.raises(SystemExit):
        cli.main()


def test_main_handler_exception(monkeypatch):
    class P:
        def parse_args(self):
            return argparse.Namespace(command="publish")

        def print_help(self):
            return None

    async def bad(_args):
        raise RuntimeError("boom")

    monkeypatch.setattr("src.cli.build_parser", lambda: P())
    monkeypatch.setattr("src.cli.cmd_publish", bad)
    called = []
    monkeypatch.setattr("src.cli._json_out", lambda data: called.append(data))
    with pytest.raises(SystemExit):
        cli.main()
    assert "boom" in called[-1]["error"]

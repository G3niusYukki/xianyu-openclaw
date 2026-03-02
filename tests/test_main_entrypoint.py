"""Tests for src.__main__ module entrypoint."""

import runpy


def test_main_module_invokes_cli_main(monkeypatch) -> None:
    """分支：import src.__main__ 时会调用从 src.cli 导入的 main。"""
    called = {"n": 0}

    def _fake_main():
        called["n"] += 1

    monkeypatch.setattr("src.cli.main", _fake_main)
    runpy.run_module("src.__main__", run_name="__main__")

    assert called["n"] == 1

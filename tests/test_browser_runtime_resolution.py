"""浏览器运行时解析测试。"""

import os

from src.core.browser_client import _resolve_runtime


def test_resolve_runtime_prefers_env_variable(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENCLAW_RUNTIME", "lite")
    assert _resolve_runtime(None) == "lite"


def test_resolve_runtime_loads_dotenv_when_env_not_exported(monkeypatch) -> None:
    monkeypatch.delenv("OPENCLAW_RUNTIME", raising=False)

    def _fake_load_dotenv(override: bool = False) -> bool:
        os.environ["OPENCLAW_RUNTIME"] = "pro"
        return True

    monkeypatch.setattr("src.core.browser_client.load_dotenv", _fake_load_dotenv)
    assert _resolve_runtime(None) == "pro"

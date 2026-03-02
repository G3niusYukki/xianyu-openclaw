import types
from unittest.mock import Mock

import httpx
import pytest

import src.dashboard_server as ds
from src.core import crypto
from src.core.error_handler import (
    handle_controller_errors,
    handle_operation_errors,
    handle_errors,
    log_execution_time,
    safe_execute,
)


def test_dashboard_extract_json_payload_and_module_console_branches(monkeypatch, tmp_path):
    assert ds._extract_json_payload("") is None
    assert ds._extract_json_payload("prefix {\"ok\": 1} suffix") == {"ok": 1}
    assert ds._extract_json_payload("xx [1,2,3] yy") == [1, 2, 3]
    assert ds._extract_json_payload("not-json") is None

    console = ds.ModuleConsole(project_root=tmp_path)

    def raises(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(ds.subprocess, "run", raises)
    err = console._run_module_cli("status", "all")
    assert "error" in err and "execution failed" in err["error"].lower()

    class Proc:
        def __init__(self, returncode, stdout, stderr):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    monkeypatch.setattr(ds.subprocess, "run", lambda *a, **k: Proc(2, "[]", "bad"))
    bad = console._run_module_cli("status", "all")
    assert bad["_cli_code"] == 2
    assert bad["error"]

    monkeypatch.setattr(ds.subprocess, "run", lambda *a, **k: Proc(0, "[1,2]", ""))
    ok_list = console._run_module_cli("status", "all")
    assert ok_list == {"items": [1, 2]}

    monkeypatch.setattr(ds.subprocess, "run", lambda *a, **k: Proc(0, "plain", ""))
    ok_plain = console._run_module_cli("status", "all")
    assert ok_plain["ok"] is True


def test_module_console_logs_and_control_argument_branches(tmp_path):
    console = ds.ModuleConsole(project_root=tmp_path)
    calls = []

    def fake_run(action, target, extra_args=None, timeout_seconds=120):
        calls.append((action, target, list(extra_args or []), timeout_seconds))
        return {"ok": True}

    console._run_module_cli = fake_run  # type: ignore[method-assign]

    assert console.logs("unknown", tail_lines=999) == {"ok": True}
    assert calls[-1][1] == "all"
    assert calls[-1][2] == ["--tail-lines", "500"]

    assert console.control("noop", "all")["error"].startswith("Unsupported module action")
    assert console.control("start", "bad")["error"].startswith("Unsupported module target")

    assert console.control("stop", "presales") == {"ok": True}
    assert calls[-1][0] == "stop"
    assert "--stop-timeout" in calls[-1][2]


@pytest.mark.asyncio
async def test_error_handler_additional_raise_on_error_branches(monkeypatch):
    obj = Mock(logger=Mock())

    @handle_controller_errors(raise_on_error=True)
    async def timeout_fn(self):
        raise httpx.TimeoutException("t")

    with pytest.raises(httpx.TimeoutException):
        await timeout_fn(obj)

    request = httpx.Request("GET", "https://example.com")
    response = httpx.Response(500, request=request)

    @handle_controller_errors(raise_on_error=True)
    async def status_fn(self):
        raise httpx.HTTPStatusError("bad", request=request, response=response)

    with pytest.raises(httpx.HTTPStatusError):
        await status_fn(obj)

    @handle_operation_errors(raise_on_error=True)
    async def net_fn(self):
        raise ConnectionError("net")

    with pytest.raises(ConnectionError):
        await net_fn(obj)

    @safe_execute(raise_on_error=True)
    async def async_safe_fail():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        await async_safe_fail()

    fake_logger = Mock()
    monkeypatch.setattr("src.core.error_handler.get_logger", lambda: fake_logger)

    @log_execution_time()
    def ok_sync():
        return 1

    assert ok_sync() == 1
    fake_logger.debug.assert_called()

    @handle_errors(exceptions=(KeyError,), default_return="d")
    def value_error_fn():
        raise ValueError("skip")

    with pytest.raises(ValueError):
        value_error_fn()


def test_crypto_more_key_and_decrypt_branches(monkeypatch, tmp_path):
    key_file = tmp_path / ".enc_key"
    monkeypatch.setattr(crypto, "_KEY_FILE", str(key_file))
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)

    # key from existing file
    key_file.write_bytes(b"abc123\n")
    assert crypto._get_or_create_key() == b"abc123"

    # key generated from cryptography branch
    key_file.unlink()

    class DummyFernet:
        @staticmethod
        def generate_key():
            return b"k" * 44

    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "cryptography.fernet":
            return types.SimpleNamespace(Fernet=DummyFernet)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    generated = crypto._get_or_create_key()
    assert generated == b"k" * 44
    assert key_file.read_bytes() == b"k" * 44

    class BadDecryptFernet:
        def __init__(self, _k):
            pass

        def decrypt(self, _v):
            raise ValueError("bad-decrypt")

    def fake_import2(name, *args, **kwargs):
        if name == "cryptography.fernet":
            return types.SimpleNamespace(Fernet=BadDecryptFernet)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import2)
    assert crypto.decrypt_value("gAAAAA-token") == "gAAAAA-token"

    monkeypatch.setattr(builtins, "__import__", real_import)

    # helper branches
    monkeypatch.setattr(crypto, "encrypt_value", lambda v: f"enc:{v}")
    monkeypatch.setattr(crypto, "decrypt_value", lambda v: f"dec:{v}")
    assert crypto.ensure_encrypted("plain") == "enc:plain"
    assert crypto.ensure_encrypted("gAAAAAabc") == "gAAAAAabc"
    assert crypto.ensure_decrypted("gAAAAAabc") == "dec:gAAAAAabc"
    assert crypto.ensure_decrypted("plain") == "plain"

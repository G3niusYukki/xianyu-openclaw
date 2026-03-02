from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from src.core import crypto
from src.core.error_handler import handle_controller_errors, handle_operation_errors, log_execution_time
from src.modules.quote.excel_import import ExcelAdaptiveImporter


@pytest.mark.asyncio
async def test_error_handler_targeted_uncovered_branches():
    obj = type("Obj", (), {"logger": type("L", (), {"warning": lambda *a, **k: None, "error": lambda *a, **k: None, "debug": lambda *a, **k: None})()})()

    @handle_controller_errors(default_return="x", raise_on_error=True)
    async def raise_http_error(self):
        raise httpx.HTTPError("plain-http-error")

    with pytest.raises(httpx.HTTPError):
        await raise_http_error(obj)

    @handle_controller_errors(default_return="x", raise_on_error=True)
    async def raise_unexpected(self):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await raise_unexpected(obj)

    @handle_operation_errors(default_return=False, raise_on_error=False)
    async def async_connection(self):
        raise ConnectionError("net")

    assert await async_connection(obj) is False

    @handle_operation_errors(default_return=False, raise_on_error=False)
    async def async_timeout(self):
        raise httpx.TimeoutException("slow")

    assert await async_timeout(obj) is False

    @handle_operation_errors(default_return=False, raise_on_error=True)
    async def async_generic(self):
        raise ValueError("bad")

    with pytest.raises(ValueError):
        await async_generic(obj)

    @handle_operation_errors(default_return=False, raise_on_error=False)
    def sync_generic(self):
        raise ValueError("sync-bad")

    assert sync_generic(obj) is False


def test_log_execution_time_sync_error_branch():
    class Logger:
        def __init__(self):
            self.errors = 0

        def debug(self, *_a, **_k):
            return None

        def error(self, *_a, **_k):
            self.errors += 1

    logger = Logger()

    @log_execution_time(logger=logger)
    def fail_sync():
        raise RuntimeError("sync-fail")

    with pytest.raises(RuntimeError):
        fail_sync()
    assert logger.errors == 1


def test_crypto_get_or_create_key_importerror_fallback(monkeypatch, tmp_path: Path):
    key_file = tmp_path / ".encryption_key"
    monkeypatch.setattr(crypto, "_KEY_FILE", str(key_file))
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)

    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "cryptography.fernet":
            raise ImportError("no-crypto")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    key = crypto._get_or_create_key()
    assert isinstance(key, bytes)
    assert key_file.exists()
    assert len(key) == 44


def test_excel_import_targeted_branch_matrix(monkeypatch, tmp_path: Path):
    importer = ExcelAdaptiveImporter()
    monkeypatch.setattr(importer.geo, "normalize", lambda v: v)

    rows_by_sheet = {
        "empty-sheet": [],  # cover: not rows -> continue
        "bad-header": [["x"], ["y"]],  # cover: head_idx < 0 -> continue
        "ok": [
            ["快递公司", "始发地", "目的地", "首重", "续重", ""],
            ["圆通", "", "广州", "3", "1"],  # missing origin -> continue
            ["圆通", "杭州", "广州", "", "1"],  # missing first_cost -> continue
            ["圆通", "杭州", "广州", "3", "1"],  # valid row
        ],
    }
    monkeypatch.setattr(importer, "_load_rows", lambda _p: rows_by_sheet)

    fake_file = tmp_path / "dummy.xlsx"
    fake_file.write_text("x", encoding="utf-8")
    out = importer.import_file(fake_file)
    assert len(out.records) == 1
    assert out.records[0].courier == "圆通"

    mapped = importer._resolve_header_map(["", "  ", "首重(元)", "续重(元)", "目的地", "始发地"])
    assert mapped["first_cost"] == 2
    assert mapped["extra_cost"] == 3

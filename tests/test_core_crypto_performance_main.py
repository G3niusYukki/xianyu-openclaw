import asyncio
import importlib
import types

import pytest

import src.core.crypto as crypto
from src.core.performance import AsyncCache, FileCache, PerformanceMonitor, batch_process, cached, monitor_performance


@pytest.mark.asyncio
async def test_async_cache_and_decorators(tmp_path):
    c = AsyncCache(default_ttl=1)
    assert await c.get("x") is None
    await c.set("x", 1)
    assert await c.get("x") == 1
    assert await c.delete("x") is True
    assert await c.delete("x") is False

    await c.set("a", 1, ttl=-1)
    assert await c.cleanup_expired() == 1
    stats = await c.get_stats()
    assert stats["total_keys"] == 0

    calls = {"n": 0}

    @cached(c, ttl=3, key_prefix="p:")
    async def fn(v):
        calls["n"] += 1
        return v * 2

    assert await fn(3) == 6
    assert await fn(3) == 6
    assert calls["n"] == 1

    @batch_process(batch_size=2, delay=0)
    async def proc(items, s=1):
        return [x + s for x in items]

    assert await proc([1, 2, 3], 2) == [3, 4, 5]
    with pytest.raises(TypeError):
        await proc("abc")


@pytest.mark.asyncio
async def test_file_cache_and_monitor(tmp_path):
    fc = FileCache(str(tmp_path / "cache"))
    await fc.set("k", {"a": 1})
    assert await fc.get("k") == {"a": 1}
    assert await fc.delete("k") is True
    assert await fc.delete("k") is False
    await fc.set("k1", 1)
    await fc.set("k2", 2)
    assert await fc.clear() >= 2

    bad = fc._get_cache_path("bad")
    bad.write_text("not-json", encoding="utf-8")
    assert await fc.get("bad") is None

    m = PerformanceMonitor()
    await m.record("x", 0.1, True)
    await m.record("x", 0.2, False)
    stats = await m.get_stats("x")
    assert stats["count"] == 2
    assert stats["success_rate"] == 0.5
    assert await m.get_stats("none") == {}
    await m.clear()

    @monitor_performance(m)
    async def ok(v):
        return v

    @monitor_performance(m)
    async def fail():
        raise RuntimeError("x")

    assert await ok(1) == 1
    with pytest.raises(RuntimeError):
        await fail()
    assert (await m.get_stats("ok"))["count"] == 1
    assert (await m.get_stats("fail"))["count"] == 1


def test_crypto_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(crypto, "_KEY_FILE", str(tmp_path / ".k"))

    # derive and env-key path
    monkeypatch.setenv("ENCRYPTION_KEY", "pass")
    key = crypto._get_or_create_key()
    assert isinstance(key, bytes)

    # no cryptography fallback via fake import
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "cryptography.fernet":
            raise ImportError("nope")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    assert crypto.encrypt_value("abc") == "abc"
    assert crypto.decrypt_value("abc") == "abc"

    monkeypatch.setattr("builtins.__import__", real_import)

    # ensure helpers
    assert crypto.is_encrypted("gAAAAA123")
    assert not crypto.is_encrypted("plain")
    assert crypto.ensure_encrypted("") == ""
    assert crypto.ensure_decrypted("") == ""


def test_main_and_module_entry(monkeypatch):
    import src.main as m

    class L:
        def __init__(self):
            self.errors = []
            self.ok = False

        def info(self, *_):
            return None

        def success(self, *_):
            self.ok = True

        def error(self, x):
            self.errors.append(x)

    logger = L()

    class C:
        app = {"name": "n", "version": "v"}

    monkeypatch.setattr("src.main.get_config", lambda: C())
    monkeypatch.setattr("src.main.get_logger", lambda: logger)

    # force one import failure
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name.endswith("accounts.service"):
            raise ImportError("bad")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    asyncio.run(m.main())
    assert logger.errors

    monkeypatch.setattr("builtins.__import__", real_import)
    asyncio.run(m.main())

    hit = {"n": 0}

    def _fake_run(coro):
        hit["n"] += 1
        coro.close()

    monkeypatch.setattr("asyncio.run", _fake_run)
    m.run()
    assert hit["n"] == 1


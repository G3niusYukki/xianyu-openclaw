from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import yaml

from src.core.compliance import ComplianceGuard
from src.core.error_handler import BrowserError
from src.core.performance import AsyncCache, FileCache, batch_process
from src.modules.messages.service import MessagesService


class _Guard:
    def evaluate_content(self, text: str):
        return {"blocked": False, "text": text}


@pytest.fixture
def svc_cfg(monkeypatch, tmp_path):
    c = SimpleNamespace(
        browser={"delay": {"min": 0.0, "max": 0.0}},
        accounts=[{"enabled": True, "cookie": "acc_cookie=v"}],
    )

    def get_section(name, default=None):
        if name == "messages":
            return {"transport": "auto", "ws": {}, "quote": {"preferred_couriers": ["新快递"]}}
        if name == "quote":
            return {}
        if name == "content":
            return {"templates": {"path": str(tmp_path)}}
        return default or {}

    c.get_section = get_section
    monkeypatch.setattr("src.modules.messages.service.get_config", lambda: c)
    monkeypatch.setattr("src.modules.messages.service.get_compliance_guard", lambda: _Guard())


def _svc():
    return MessagesService(controller=None, config={})


def test_compliance_reload_exception_and_misc_branches(tmp_path):
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text("::bad::yaml::", encoding="utf-8")
    g = ComplianceGuard(str(rules_path))

    g.rules_path = tmp_path / "is_dir"
    g.rules_path.mkdir()
    g.reload()
    assert g._rules_mtime is None

    g._rules["content"]["banned_keywords"] = "not-list"
    assert g._keywords() == []
    g._rules["reload"] = {"auto_reload": True, "check_interval_seconds": 0}
    g.rules_path = tmp_path / "missing.yaml"
    g._auto_reload_if_needed()


@pytest.mark.asyncio
async def test_compliance_evaluate_batch_warn_branch(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "mode": "warn",
                "reload": {"auto_reload": False},
                "batch_operations": {"polish_cooldown_seconds": 9999},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    g = ComplianceGuard(str(path))
    assert (await g.evaluate_batch_polish_rate("k"))["allowed"] is True
    second = await g.evaluate_batch_polish_rate("k")
    assert second["warn"] is True and second["blocked"] is False


@pytest.mark.asyncio
async def test_performance_targeted_exception_and_noargs_branches(tmp_path, monkeypatch):
    c = AsyncCache(default_ttl=10)
    await c.set("k", 1, ttl=-1)
    assert await c.get("k") is None
    await c.set("a", 1)
    assert await c.clear() == 1

    fc = FileCache(str(tmp_path / "cache"))
    assert await fc.get("missing") is None

    class _BadOpen:
        async def __aenter__(self):
            raise RuntimeError("boom")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("src.core.performance.aiofiles.open", lambda *a, **k: _BadOpen())
    await fc.set("x", {"a": 1})

    p = fc._get_cache_path("x")
    p.write_text("1", encoding="utf-8")

    monkeypatch.setattr("pathlib.Path.unlink", lambda self: (_ for _ in ()).throw(RuntimeError("x")))
    assert await fc.delete("x") is False
    assert await fc.clear() == 0

    called = {"n": 0}

    @batch_process(batch_size=2, delay=0)
    async def fn(*args, **kwargs):
        called["n"] += 1
        return ["ok"]

    assert await fn() == ["ok"]
    assert called["n"] == 1


def test_messages_misc_local_branches(svc_cfg):
    s = _svc()
    s.transport_mode = "dom"
    assert s._should_use_ws_transport() is False

    assert s._extract_service_level("加急件") == "urgent"
    assert s._extract_service_level("次日达") == "express"
    assert s._extract_locations("由杭州发")[0].startswith("杭州")

    assert s._get_quote_context("") == {}
    s._update_quote_context("", origin="杭州")
    s._quote_context_memory["sid"] = {"origin": "杭州", "updated_at": 0}
    s._update_quote_context("sid", destination="  ")
    assert "destination" not in s._quote_context_memory["sid"]

    assert s._extract_single_location("") is None

    assert s._is_quote_followup_candidate("") is False
    assert s._is_quote_followup_candidate("10x20x30") is True
    assert s._is_quote_followup_candidate("杭州到上海") is True
    assert s._is_quote_followup_candidate("选顺丰") is True
    assert s._is_quote_followup_candidate("我去付款") is True

    assert s._detect_courier_choice("") is None
    assert s._detect_courier_choice("选新快递") == "新快递"
    assert s._is_checkout_followup("") is False

    assert s._find_quote_row_by_courier({"last_quote_rows": [{"courier": "顺丰"}]}, "") is None
    assert s._find_quote_row_by_courier({"last_quote_rows": [{"courier": "顺丰"}]}, "圆通") is None

    assert "可选渠道：顺丰" in s._build_available_couriers_hint({"last_quote_rows": [{"courier": "顺丰"}]})
    assert "请先按格式发送" in s._build_available_couriers_hint({"last_quote_rows": [{"courier": ""}]})

    req, missing = s._build_quote_request("你好")
    assert req is None and set(missing) == {"origin", "destination", "weight"}


@pytest.mark.asyncio
async def test_messages_ws_and_dom_branches(svc_cfg, monkeypatch):
    s = _svc()

    with pytest.raises(BrowserError):
        await s._get_unread_sessions_dom(limit=1)

    class Ctl:
        async def new_page(self):
            return "p1"

        async def navigate(self, *_):
            return None

        async def execute_script(self, *_):
            return {"bad": 1}

        async def close_page(self, *_):
            return None

    s.controller = Ctl()
    assert await s._get_unread_sessions_dom(limit=1) == []

    s.transport_mode = "ws"
    monkeypatch.setattr(s, "_resolve_ws_cookie", lambda: "cookie=v")
    monkeypatch.setattr(
        "src.modules.messages.ws_live.GoofishWsTransport",
        lambda **_k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    with pytest.raises(BrowserError):
        await s._ensure_ws_transport()


@pytest.mark.asyncio
async def test_messages_get_unread_and_reply_process_branches(svc_cfg, monkeypatch):
    s = _svc()

    class W:
        async def get_unread_sessions(self, limit=20):
            return []

        def is_ready(self):
            return False

        async def send_text(self, session_id: str, text: str):
            return False

    s.transport_mode = "ws"
    monkeypatch.setattr(s, "_ensure_ws_transport", AsyncMock(return_value=W()))
    assert await s.get_unread_sessions(limit=2) == []

    class W2(W):
        def is_ready(self):
            raise RuntimeError("x")

    monkeypatch.setattr(s, "_ensure_ws_transport", AsyncMock(return_value=W2()))
    assert await s.get_unread_sessions(limit=2) == []

    s.transport_mode = "auto"

    class _Ctl:
        async def new_page(self):
            return "p"

        async def navigate(self, *_):
            return None

        async def execute_script(self, *_):
            return []

        async def close_page(self, *_):
            return None

    s.controller = _Ctl()

    class W3(W):
        def is_ready(self):
            return True

    monkeypatch.setattr(s, "_ensure_ws_transport", AsyncMock(return_value=W3()))
    monkeypatch.setattr(s, "_get_unread_sessions_dom", AsyncMock(return_value=[{"session_id": "d1"}]))
    assert (await s.get_unread_sessions(limit=2))[0]["session_id"] == "d1"

    monkeypatch.setattr(s, "_ensure_ws_transport", AsyncMock(return_value=None))
    monkeypatch.setattr(s, "_get_unread_sessions_dom", AsyncMock(return_value=[{"session_id": "d2"}]))
    assert (await s.get_unread_sessions(limit=2))[0]["session_id"] == "d2"

    s._quote_context_memory["s1"] = {
        "courier_choice": "顺丰",
        "last_quote_rows": [{"courier": "圆通", "total_fee": 10}],
        "updated_at": 9999999999,
    }
    reply, meta = await s._generate_reply_with_quote("选顺丰", session_id="s1")
    assert "暂未匹配" in reply and meta["courier_locked"] is False

    s.controller = None
    monkeypatch.setattr(s, "_ensure_ws_transport", AsyncMock(return_value=W()))
    assert await s.reply_to_session("sid", "txt") is False

    s.compliance_center = SimpleNamespace(
        evaluate_before_send=lambda *a, **k: SimpleNamespace(blocked=False, reason="", policy_scope="")
    )
    monkeypatch.setattr(s, "_generate_reply_with_quote", AsyncMock(return_value=("ok", {"is_quote": False})))
    monkeypatch.setattr(s, "reply_to_session", AsyncMock(return_value=True))
    out = await s.process_session({"session_id": "sid", "last_message": "x"}, dry_run=False)
    assert out["sent"] is True

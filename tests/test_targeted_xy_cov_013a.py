from __future__ import annotations

import asyncio
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest

from src.core.error_handler import BrowserError
from src.modules.messages import ws_live
from src.modules.messages.ws_live import GoofishWsTransport, decode_sync_payload
from src.modules.quote.cost_table import CostRecord, CostTableRepository, normalize_courier_name


@pytest.fixture
def ws_enabled(monkeypatch):
    monkeypatch.setattr(ws_live, "websockets", object())


@pytest.mark.asyncio
async def test_ws_live_extra_guards_and_failure_paths(ws_enabled, monkeypatch):
    assert decode_sync_payload("!!!!") is None

    t = GoofishWsTransport(cookie_text="unb=1001; _m_h5_tk=tk_x; cookie2=c")
    t._ws = None
    with pytest.raises(BrowserError, match="WebSocket not connected"):
        await t._send_reg()

    class W:
        @staticmethod
        async def connect(*_a, **_k):
            raise TypeError("unexpected kw")

    monkeypatch.setattr(ws_live, "websockets", W())
    monkeypatch.setattr(t, "_maybe_reload_cookie", lambda *a, **k: False)

    async def _no_sleep(_sec):
        t._stop_event.set()

    monkeypatch.setattr(ws_live.asyncio, "sleep", _no_sleep)
    await t._run()
    assert "unexpected kw" in t._last_disconnect_reason


@pytest.mark.asyncio
async def test_ws_live_fetch_token_preflight_and_retry_branches(ws_enabled, monkeypatch):
    t = GoofishWsTransport(cookie_text="unb=1001; _m_h5_tk=tk_x; cookie2=c", config={"token_max_attempts": 2})

    async def bad_preflight():
        raise RuntimeError("preflight exploded")

    class Resp:
        @staticmethod
        def json():
            return {"ret": ["SUCCESS::调用成功"], "data": {}}

    class CM:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *_a, **_k):
            return Resp()

    sleeps: list[float] = []

    async def fake_sleep(sec):
        sleeps.append(sec)

    monkeypatch.setattr(t, "_preflight_has_login", bad_preflight)
    monkeypatch.setattr(ws_live.httpx, "AsyncClient", lambda **_k: CM())
    monkeypatch.setattr(ws_live.asyncio, "sleep", fake_sleep)

    with pytest.raises(BrowserError, match="accessToken missing"):
        await t._fetch_token()
    assert sleeps == [2.0]


@pytest.mark.asyncio
async def test_ws_live_wait_stop_and_queue_exception_paths(ws_enabled):
    t = GoofishWsTransport(cookie_text="unb=1001; _m_h5_tk=tk_x; cookie2=c")

    t._stop_event.set()
    assert await t._wait_for_cookie_update_forever() is False

    ev = asyncio.Event()
    ev.set()
    assert await t._wait_event_with_timeout(ev, 0.01) is True

    class BadQueue:
        def empty(self):
            return False

        def get_nowait(self):
            raise RuntimeError("boom")

    t._queue = BadQueue()  # type: ignore[assignment]
    t._ready.set()

    async def fake_start():
        return None

    t.start = fake_start  # type: ignore[assignment]
    out = await t.get_unread_sessions(limit=3)
    assert out == []


@pytest.mark.asyncio
async def test_ws_live_preflight_cookie_json_error_and_close_error(ws_enabled, monkeypatch):
    t = GoofishWsTransport(cookie_text="unb=1001; _m_h5_tk=tk_x; cookie2=c")

    class RespBadJson:
        @staticmethod
        def json():
            raise ValueError("bad json")

    class CM1:
        def __init__(self):
            self.cookies = SimpleNamespace(jar=[])

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *_a, **_k):
            return RespBadJson()

    monkeypatch.setattr(ws_live.httpx, "AsyncClient", lambda **_k: CM1())
    assert await t._preflight_has_login() is False

    class BadWs:
        async def close(self):
            raise RuntimeError("close failed")

    t._ws = BadWs()

    class DummyTask:
        def cancel(self):
            return None

        def done(self):
            return False

        def __await__(self):
            async def _inner():
                return None

            return _inner().__await__()

    t._run_task = DummyTask()  # type: ignore[assignment]
    await t.stop()
    assert t._ws is None
    assert t._run_task is None


def test_cost_table_targeted_helpers_and_branches(tmp_path):
    repo = CostTableRepository(table_dir=tmp_path, include_patterns=["*.csv"])

    assert normalize_courier_name("圆通") == "圆通"

    repo_missing = CostTableRepository(table_dir=tmp_path / "missing")
    assert repo_missing._collect_files() == []

    good = CostRecord("圆通", "杭州", "上海", 5.0, 1.0)
    bad = CostRecord("", "杭州", "上海", 1.0, 1.0)
    repo._rebuild_indexes([good, bad])
    assert repo._index_route[("杭州", "上海")] == [good]

    assert repo._origin_similarity("杭州", "杭州") == 4
    assert repo._origin_similarity("杭州", "杭") == 3
    assert repo._origin_similarity("ab12", "ab34") == 1
    assert repo._origin_similarity("广州", "北京") == 0

    class _FakeMatch:
        @staticmethod
        def group(_idx):
            return "x"

    import src.modules.quote.cost_table as ct

    from unittest.mock import patch

    with patch.object(ct.re, "search", return_value=_FakeMatch()):
        assert repo._to_float("will-hit-value-error") is None


def test_cost_table_rows_header_and_cell_paths(tmp_path):
    repo = CostTableRepository(table_dir=tmp_path)

    hm = repo._resolve_header_map(["", " 快递公司 ", " 首重1KG ", "续重每kg", "发货地", "收件地"])
    assert hm["courier"] == 1
    assert hm["first_cost"] == 2
    assert hm["extra_cost"] == 3

    rows = [
        ["快递公司", "发件地", "收件地", "首重", "续重", "抛比"],
        ["圆通", "杭州", "上海", "6", "1", "6000"],
        ["", "杭州", "上海", "6", "1", "6000"],
        ["圆通", "杭州", "上海", "", "1", "6000"],
    ]
    records = repo._rows_to_records(rows, source_file="a.csv", source_sheet="csv")
    assert len(records) == 1
    assert records[0].courier == "圆通"
    assert records[0].throw_ratio == 6000.0

    cell_s_no_text = ET.fromstring('<c xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" t="s"><v/></c>')
    assert repo._read_cell_value(cell_s_no_text, ["a"]) == ""

    cell_s_bad_idx = ET.fromstring('<c xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" t="s"><v>9</v></c>')
    assert repo._read_cell_value(cell_s_bad_idx, ["a"]) == ""

    cell_plain = ET.fromstring('<c xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><v>12.5</v></c>')
    assert repo._read_cell_value(cell_plain, []) == "12.5"

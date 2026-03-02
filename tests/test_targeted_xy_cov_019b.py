from __future__ import annotations

import asyncio
import base64
import io
import zipfile
from types import SimpleNamespace

import pytest

import src.modules.messages.ws_live as ws_live
from src.core.error_handler import BrowserError
from src.dashboard_server import DashboardHandler
from src.modules.messages.ws_live import GoofishWsTransport, MessagePackDecoder, decode_sync_payload
from src.modules.quote.cost_table import CostRecord, CostTableRepository, normalize_courier_name


@pytest.fixture
def ws_enabled(monkeypatch):
    monkeypatch.setattr(ws_live, "websockets", object())


def test_ws_messagepack_numeric_and_array_branches():
    assert MessagePackDecoder(bytes([0xD1, 0xFF, 0xFE])).decode() == -2
    assert MessagePackDecoder(bytes([0xD2, 0x00, 0x00, 0x00, 0x2A])).decode() == 42
    assert MessagePackDecoder(bytes([0xD3, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x2A])).decode() == 42
    assert MessagePackDecoder(bytes([0xCB, 0x3F, 0xF8, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])).decode() == 1.5
    assert MessagePackDecoder(bytes([0xCD, 0x01, 0x00])).decode() == 256
    assert MessagePackDecoder(bytes([0xCE, 0x00, 0x00, 0x01, 0x00])).decode() == 256
    assert MessagePackDecoder(bytes([0x92, 0x01, 0x02])).decode() == [1, 2]
    assert MessagePackDecoder(bytes([0xD9, 0x03, 0x61, 0x62, 0x63])).decode() == "abc"
    assert MessagePackDecoder(bytes([0xE0])).decode() == -32


def test_ws_decode_sync_payload_msgpack_fail_returns_none():
    bad = base64.b64encode(bytes([0xC1])).decode()
    assert decode_sync_payload(bad) is None


@pytest.mark.asyncio
async def test_ws_wait_forever_cookie_reload_success(ws_enabled):
    t = GoofishWsTransport(cookie_text="unb=1001; _m_h5_tk=tk_x; cookie2=c")
    t._maybe_reload_cookie = lambda **_k: True  # type: ignore[assignment]
    assert await t._wait_for_cookie_update_forever() is True


@pytest.mark.asyncio
async def test_ws_push_event_queue_full_get_nowait_error(ws_enabled):
    t = GoofishWsTransport(cookie_text="unb=1001; _m_h5_tk=tk_x; cookie2=c")

    class Q:
        def __init__(self):
            self.items = []

        def full(self):
            return True

        def get_nowait(self):
            raise RuntimeError("drop failed")

        async def put(self, x):
            self.items.append(x)

    q = Q()
    t._queue = q  # type: ignore[assignment]

    await t._push_event(
        {
            "chat_id": "c1",
            "sender_user_id": "u2",
            "sender_name": "买家A",
            "text": "你好",
            "create_time": 10**13,
        }
    )
    assert len(q.items) == 1
    assert q.items[0]["session_id"] == "c1"
    assert t._queue_event.is_set() is True


@pytest.mark.asyncio
async def test_ws_preflight_ignores_empty_cookie_jar_entries(ws_enabled, monkeypatch):
    t = GoofishWsTransport(cookie_text="unb=1001; _m_h5_tk=tk_x; cookie2=c")

    class Resp:
        @staticmethod
        def json():
            return {"content": {"success": True}}

    class CM:
        def __init__(self):
            self.cookies = SimpleNamespace(
                jar=[
                    SimpleNamespace(name="", value="x"),
                    SimpleNamespace(name="k1", value=""),
                    SimpleNamespace(name="k2", value="v2"),
                ]
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *_a, **_k):
            return Resp()

    monkeypatch.setattr(ws_live.httpx, "AsyncClient", lambda **_k: CM())
    ok = await t._preflight_has_login()
    assert ok is True
    assert t.cookies.get("k2") == "v2"
    assert "k1" not in t.cookies


def test_cost_table_find_candidates_and_rank_edges(tmp_path, monkeypatch):
    repo = CostTableRepository(table_dir=tmp_path)
    rec = CostRecord("圆通", "杭州", "上海", 5.0, 1.0)

    monkeypatch.setattr(repo, "_reload_if_needed", lambda: None)
    repo._records = [rec]
    assert repo.find_candidates(origin="", destination="上海") == []

    repo._records = [rec]
    repo._index_route = {}
    repo._index_courier_route = {}
    monkeypatch.setattr("src.modules.quote.cost_table.contains_match", lambda *_a, **_k: True)
    fuzzy = repo.find_candidates(origin="杭州", destination="上海")
    assert len(fuzzy) == 1
    assert fuzzy[0].courier == "圆通"

    rec2 = CostRecord("圆通", "浙江", "上海", 6.0, 1.0)
    repo._records = [rec2]
    repo._index_destination = {"上海": [rec2]}
    monkeypatch.setattr("src.modules.quote.cost_table.contains_match", lambda *_a, **_k: False)

    calls = {"n": 0}

    def fake_rank(records, origin_norm):
        calls["n"] += 1
        return [] if calls["n"] == 1 else records

    monkeypatch.setattr(repo, "_rank_by_origin_similarity", fake_rank)
    got = repo.find_candidates(origin="杭州", destination="上海")
    assert got == [rec2]

    repo._index_destination = {}
    assert repo.find_candidates(origin="杭州", destination="深圳") == []


def test_cost_table_misc_uncovered_paths(tmp_path, monkeypatch):
    repo = CostTableRepository(table_dir=tmp_path)

    assert normalize_courier_name("圆通") == "圆通"
    assert repo._rank_by_origin_similarity([], "杭州") == []

    unknown = [CostRecord("圆通", "X", "上海", 1, 1)]
    assert repo._rank_by_origin_similarity(unknown, "杭州") == []

    monkeypatch.setattr(repo, "_read_text_file", lambda _p: "")
    assert repo._load_csv(tmp_path / "x.csv") == []

    assert repo._rows_to_records([], source_file="a", source_sheet="b") == []
    assert repo._to_float(3) == 3.0

    z = tmp_path / "mini.xlsx"
    with zipfile.ZipFile(z, "w") as arc:
        arc.writestr("dummy.txt", "ok")

    monkeypatch.setattr(repo, "_read_shared_strings", lambda _a: [])
    monkeypatch.setattr(repo, "_read_sheet_paths", lambda _a: [("S", "xl/worksheets/missing.xml")])
    assert repo._iter_xlsx_rows(z) == {}

    wb = (
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheets><sheet name="A" r:id="rId1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
        "</sheets></workbook>"
    )
    rel = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="" Target="/xl/worksheets/sheet1.xml"/>'
        '<Relationship Id="rId1" Target="/xl/worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    repo2 = CostTableRepository(table_dir=tmp_path)
    with zipfile.ZipFile(z, "w") as arc:
        arc.writestr("xl/workbook.xml", wb)
        arc.writestr("xl/_rels/workbook.xml.rels", rel)
    with zipfile.ZipFile(z) as arc:
        paths = repo2._read_sheet_paths(arc)
    assert paths == [("A", "xl/worksheets/sheet1.xml")]

    xml = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData><row><c r='1'><v>v</v></c></row></sheetData></worksheet>"
    )
    with zipfile.ZipFile(z, "w") as arc:
        arc.writestr("xl/worksheets/sheet1.xml", xml)
    with zipfile.ZipFile(z) as arc:
        assert repo2._read_sheet_rows(arc, "xl/worksheets/sheet1.xml", []) == []


def test_dashboard_read_multipart_parse_error_and_disposition_skip(monkeypatch):
    h = DashboardHandler.__new__(DashboardHandler)
    body = b"abcdef"
    h.headers = {"Content-Type": "multipart/form-data; boundary=----x", "Content-Length": str(len(body))}
    h.rfile = io.BytesIO(body)

    import email.parser

    def boom(self, _raw):
        raise ValueError("bad mime")

    monkeypatch.setattr(email.parser.BytesParser, "parsebytes", boom)
    assert h._read_multipart_files() == []

    class Part:
        def is_multipart(self):
            return False

        def get_content_disposition(self):
            return "inline"

        def get_filename(self):
            return "x.txt"

        def get_payload(self, decode=True):
            return b"x"

    class Msg:
        def walk(self):
            return [Part()]

    class ParserOK:
        def __init__(self, policy=None):
            pass

        def parsebytes(self, _raw):
            return Msg()

    h.rfile = io.BytesIO(body)
    monkeypatch.setattr(email.parser, "BytesParser", ParserOK)
    assert h._read_multipart_files() == []


def test_ws_constructor_and_run_raise_when_websockets_missing(monkeypatch):
    monkeypatch.setattr(ws_live, "websockets", None)
    with pytest.raises(BrowserError, match="requires `websockets`"):
        GoofishWsTransport(cookie_text="unb=1")

    t = object.__new__(GoofishWsTransport)
    monkeypatch.setattr(ws_live, "websockets", None)
    with pytest.raises(BrowserError, match="requires `websockets`"):
        asyncio.run(t._run())

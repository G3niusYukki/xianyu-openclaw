from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.lite.ws_client import LiteWsClient
from src.modules.messages.service import MessagesService
from src.modules.quote.excel_import import ExcelAdaptiveImporter


@pytest.fixture
def msg_service(monkeypatch, tmp_path: Path):
    cfg = SimpleNamespace(browser={"delay": {"min": 0.0, "max": 0.0}}, accounts=[])

    def get_section(name, default=None):
        if name == "messages":
            return {"transport": "auto", "ws": {}, "cookie": ""}
        if name == "quote":
            return {}
        if name == "content":
            return {"templates": {"path": str(tmp_path)}}
        return default or {}

    cfg.get_section = get_section
    monkeypatch.setattr("src.modules.messages.service.get_config", lambda: cfg)

    class Guard:
        def evaluate_content(self, text):
            return {"blocked": False}

    monkeypatch.setattr("src.modules.messages.service.get_compliance_guard", lambda: Guard())
    return MessagesService(controller=None, config={})


def test_excel_import_edge_branches(tmp_path: Path):
    importer = ExcelAdaptiveImporter()

    with pytest.raises(FileNotFoundError):
        importer.import_file(tmp_path / "not-exists.csv")

    csv_path = tmp_path / "报价.csv"
    csv_path.write_text("目的地,首重,续重\n广州,3,2\n", encoding="utf-8")
    rows = importer._load_rows(csv_path)
    assert "csv" in rows

    mapped, idx = importer._locate_header([["x"], ["y"]])
    assert mapped == {}
    assert idx == -1

    assert importer._detect_courier([], "圆通", "x.xlsx", {}, 0) == "圆通"
    assert importer._detect_courier([], "sheet1", "韵达报价.xlsx", {}, 0) == "韵达"
    assert importer._detect_courier([], "sheet2", "unknown.xlsx", {}, 0) == ""

    assert importer._cell(["a"], None) == ""
    assert importer._cell(["a"], 2) == ""
    assert importer._to_float("abc") is None


@pytest.mark.asyncio
async def test_ws_client_ack_extract_handle_and_stop_branches(monkeypatch):
    async def token_provider():
        return "tk"

    c = LiteWsClient(ws_url="wss://x", cookie="k=v", device_id="d", my_user_id="me", token_provider=token_provider)

    class WS:
        def __init__(self):
            self.sent = []

        async def send(self, text):
            self.sent.append(text)

        async def close(self):
            raise RuntimeError("close boom")

    c._ws = WS()

    await c._ack_packet({"headers": {}})
    await c._ack_packet({"headers": "bad"})
    assert c._ws.sent == []

    await c._ack_packet({"headers": {"mid": "1", "sid": "s", "app-key": "a", "ua": "u", "dt": "d"}})
    assert c._ws.sent and '"code": 200' in c._ws.sent[-1]

    assert c._extract_event({"1": {"10": {}}}) is None
    assert c._extract_event({"1": {"10": "bad"}}) is None

    await c._handle_sync({"body": {"syncPushPackage": {"data": "bad"}}})
    monkeypatch.setattr("src.lite.ws_client.decrypt_payload", lambda _x: None)
    await c._handle_sync({"body": {"syncPushPackage": {"data": ["x", {}, {"data": "abc"}]}}})

    await c.stop()


@pytest.mark.asyncio
async def test_ws_client_run_forever_reconnect_timeout_and_finally_close_exception(monkeypatch):
    async def token_provider():
        return "tk"

    c = LiteWsClient(
        ws_url="wss://x",
        cookie="k=v",
        device_id="d",
        my_user_id="me",
        token_provider=token_provider,
        heartbeat_interval=0,
        heartbeat_timeout=0,
        reconnect_base_delay=0,
        reconnect_max_delay=0,
    )

    class FakeWS:
        async def send(self, _text):
            return None

        async def recv(self):
            await asyncio.sleep(0)
            return "{}"

        async def close(self):
            raise RuntimeError("close fail")

    async def connect(*_a, **_k):
        return FakeWS()

    async def fake_register():
        return None

    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)
        c._stop.set()

    monkeypatch.setattr("src.lite.ws_client.websockets.connect", connect)
    monkeypatch.setattr(c, "_register", fake_register)
    monkeypatch.setattr("src.lite.ws_client.asyncio.sleep", fake_sleep)

    await c.run_forever()
    assert sleeps


def test_messages_service_ws_and_courier_hint_branches(msg_service: MessagesService, monkeypatch):
    assert "按格式发送" in msg_service._build_available_couriers_hint({})
    assert "按格式发送" in msg_service._build_available_couriers_hint({"last_quote_rows": [{"courier": ""}]})

    msg_service.courier_lock_template = "{not_exists}"
    text, matched = msg_service._build_courier_lock_reply({"courier_choice": "圆通"})
    assert "已为你锁定" in text
    assert matched is False

    cfg = SimpleNamespace(browser={"delay": {"min": 0, "max": 0}}, accounts=[])
    cfg.get_section = lambda name, default=None: {"content": {"templates": "bad"}}.get(name, default or {})
    monkeypatch.setattr("src.modules.messages.service.get_config", lambda: cfg)
    p = msg_service._resolve_reply_templates_path()
    assert p.name == "reply_templates.json"


@pytest.mark.asyncio
async def test_messages_service_ensure_ws_transport_cookie_and_import_fail(msg_service: MessagesService, monkeypatch):
    msg_service.transport_mode = "ws"
    msg_service.config["cookie"] = ""
    monkeypatch.setattr("src.modules.messages.service.os.getenv", lambda *_a, **_k: "")
    with pytest.raises(Exception):
        await msg_service._ensure_ws_transport()

    msg_service.transport_mode = "auto"
    msg_service._ws_unavailable_reason = ""
    out = await msg_service._ensure_ws_transport()
    assert out is None

    msg_service.config["cookie"] = "k=v"
    msg_service._ws_unavailable_reason = ""

    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "src.modules.messages.ws_live":
            raise RuntimeError("boom")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    out2 = await msg_service._ensure_ws_transport()
    assert out2 is None

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from src.core import browser_client as bc
from src.core.error_handler import BrowserError


class _Resp:
    def __init__(self, status_code=200, payload=None, text="", content=b"", is_success=True):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.content = content
        self.is_success = is_success

    def json(self):
        return self._payload


class _Client:
    def __init__(self):
        self.get = AsyncMock(return_value=_Resp(200, {}))
        self.post = AsyncMock(return_value=_Resp(200, {}))
        self.delete = AsyncMock(return_value=_Resp(200, {}))
        self.aclose = AsyncMock()


@pytest.mark.asyncio
async def test_connect_httpx_connect_error(monkeypatch):
    class AC:
        def __init__(self, **_kwargs):
            pass

        async def get(self, *_a, **_k):
            raise bc.httpx.ConnectError("no gateway")

    monkeypatch.setattr("src.core.browser_client.httpx.AsyncClient", AC)
    c = bc.BrowserClient()
    assert await c.connect() is False
    assert c.state == bc.BrowserState.ERROR


@pytest.mark.asyncio
async def test_close_page_and_focus_and_act_error_paths():
    c = bc.BrowserClient({"delay_min": 0.0, "delay_max": 0.0})
    c._client = _Client()
    c._tabs = {"t1": "t1"}
    c._active_tab_id = "t1"

    assert await c.close_page("t1") is True
    assert c._active_tab_id is None

    c._client.delete.side_effect = RuntimeError("x")
    assert await c.close_page("x") is False

    c._client.post.return_value = _Resp(200, {}, is_success=False)
    await c._focus_tab("p1")
    assert c._active_tab_id is None

    c._client.post.return_value = _Resp(500, {}, text="boom")
    with pytest.raises(BrowserError):
        await c._act("click", selector="#a")


@pytest.mark.asyncio
async def test_upload_and_execute_and_screenshot_failures(tmp_path):
    c = bc.BrowserClient({"delay_min": 0.0, "delay_max": 0.0})
    c._client = _Client()
    c._focus_tab = AsyncMock()
    c.click = AsyncMock(return_value=True)

    assert await c.upload_file("p", "#i", "") is False

    c._client.post.side_effect = RuntimeError("upload")
    assert await c.upload_file("p", "#i", "a.jpg") is False
    c._client.post.side_effect = None

    assert await c.upload_files("p", "#i", []) is True
    c._client.post.side_effect = RuntimeError("upload2")
    assert await c.upload_files("p", "#i", ["a", "b"]) is False
    c._client.post.side_effect = None

    c._client.post.return_value = _Resp(500)
    assert await c.execute_script("p", "1+1") is None
    c._client.post.side_effect = RuntimeError("script")
    assert await c.execute_script("p", "1+1") is None
    c._client.post.side_effect = None

    c._client.post.return_value = _Resp(500)
    assert await c.take_screenshot("p", str(tmp_path / "x.png")) is False
    c._client.post.side_effect = RuntimeError("shot")
    assert await c.take_screenshot("p", str(tmp_path / "x2.png")) is False


@pytest.mark.asyncio
async def test_misc_helpers_and_runtime_resolution_fallback(monkeypatch):
    c = bc.BrowserClient({"delay_min": 0.0, "delay_max": 0.0})
    c._client = _Client()

    c.navigate = AsyncMock(return_value=True)
    assert await c.reload("p") is True

    c._act = AsyncMock(side_effect=RuntimeError("x"))
    assert await c.go_back("p") is False
    assert await c.go_forward("p") is False

    c.get_snapshot = AsyncMock(return_value="<html>ok</html>")
    assert await c.get_page_source("p") == "<html>ok</html>"

    c._client.post.side_effect = RuntimeError("dialog")
    assert await c.handle_dialog("p") is False

    c._client.get.return_value = _Resp(500)
    assert await c._list_tabs() == []
    c._client.get.side_effect = RuntimeError("tabs")
    assert await c._list_tabs() == []

    monkeypatch.delenv("OPENCLAW_RUNTIME", raising=False)
    monkeypatch.setattr("src.core.browser_client.load_dotenv", lambda **_k: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr("src.core.config.get_config", lambda: (_ for _ in ()).throw(RuntimeError("cfg")))
    assert bc._resolve_runtime(None) == "auto"


@pytest.mark.asyncio
async def test_create_browser_client_auto_paths(monkeypatch):
    sentinel_gateway = object()
    sentinel_lite = object()

    monkeypatch.setattr("src.core.browser_client._resolve_runtime", lambda _cfg: "auto")
    monkeypatch.setattr("src.core.browser_client._probe_gateway_available", AsyncMock(return_value=True))

    async def boom(_cfg):
        raise RuntimeError("gw down")

    monkeypatch.setattr("src.core.browser_client._create_gateway_client", boom)
    monkeypatch.setattr("src.core.browser_client._create_lite_client", AsyncMock(return_value=sentinel_lite))

    got = await bc.create_browser_client({})
    assert got is sentinel_lite

    monkeypatch.setattr("src.core.browser_client._probe_gateway_available", AsyncMock(return_value=False))
    got2 = await bc.create_browser_client({})
    assert got2 is sentinel_lite

    monkeypatch.setattr("src.core.browser_client._resolve_runtime", lambda _cfg: "pro")
    monkeypatch.setattr("src.core.browser_client._create_gateway_client", AsyncMock(return_value=sentinel_gateway))
    assert await bc.create_browser_client({}) is sentinel_gateway


@pytest.mark.asyncio
async def test_create_lite_client_import_error(monkeypatch):
    orig_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "src.core.playwright_client":
            raise ImportError("missing")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    with pytest.raises(BrowserError):
        await bc._create_lite_client({})

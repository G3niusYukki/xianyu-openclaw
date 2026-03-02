from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from src.core.browser_client import BrowserClient, BrowserState, _create_gateway_client, _create_lite_client
from src.core.error_handler import BrowserError


class _Resp:
    def __init__(self, status_code=200, payload=None, text="", content=b"", is_success=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.content = content
        self.is_success = (200 <= status_code < 300) if is_success is None else is_success

    def json(self):
        return self._payload


class _Client:
    def __init__(self):
        self.get = AsyncMock(return_value=_Resp(200, {}))
        self.post = AsyncMock(return_value=_Resp(200, {}))
        self.delete = AsyncMock(return_value=_Resp(200, {}))
        self.aclose = AsyncMock()


@pytest.mark.asyncio
async def test_gateway_config_and_headers(monkeypatch):
    monkeypatch.setenv("OPENCLAW_GATEWAY_HOST", "h")
    monkeypatch.setenv("OPENCLAW_GATEWAY_PORT", "18800")
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "tok")
    monkeypatch.setenv("OPENCLAW_BROWSER_PROFILE", "p")
    c = BrowserClient({"timeout": 9, "delay_min": 0.0, "delay_max": 0.0})
    assert c.config.browser_port == 18802
    assert c._headers()["Authorization"] == "Bearer tok"
    assert c._profile_params() == {"profile": "p"}
    assert c.random_delay() == 0.0


@pytest.mark.asyncio
async def test_connect_paths_disconnect_and_is_connected(monkeypatch):
    c = BrowserClient({"delay_min": 0.0, "delay_max": 0.0})
    fake = _Client()
    monkeypatch.setattr("src.core.browser_client.httpx.AsyncClient", lambda **_: fake)

    fake.get.return_value = _Resp(200)
    assert await c.connect() is True
    assert c.state == BrowserState.CONNECTED

    assert await c.is_connected() is True
    fake.get.return_value = _Resp(500)
    assert await c.is_connected() is False

    c._tabs = {"a": "a"}
    c.close_page = AsyncMock(return_value=True)
    await c.disconnect()
    c.close_page.assert_awaited_once_with("a")


@pytest.mark.asyncio
async def test_connect_503_start_and_error(monkeypatch):
    c = BrowserClient()
    fake = _Client()
    monkeypatch.setattr("src.core.browser_client.httpx.AsyncClient", lambda **_: fake)
    monkeypatch.setattr("src.core.browser_client.asyncio.sleep", AsyncMock())

    fake.get.return_value = _Resp(503)
    fake.post.return_value = _Resp(200)
    assert await c.connect() is True

    c2 = BrowserClient()
    fake2 = _Client()
    fake2.get.return_value = _Resp(418)
    monkeypatch.setattr("src.core.browser_client.httpx.AsyncClient", lambda **_: fake2)
    assert await c2.connect() is False


@pytest.mark.asyncio
async def test_tab_navigation_and_actions():
    c = BrowserClient({"retry_times": 2, "delay_min": 0.0, "delay_max": 0.0})
    c._client = _Client()
    c.state = BrowserState.CONNECTED
    c._client.post.return_value = _Resp(200, {"targetId": "t1"})

    assert await c.new_page() == "t1"

    c._client.post.return_value = _Resp(200, {})
    await c._focus_tab("t1")
    assert c._active_tab_id == "t1"

    assert await c.navigate("t1", "https://a", wait_load=False) is True
    c._client.post.side_effect = RuntimeError("x")
    assert await c.navigate("t1", "https://a", wait_load=False) is False
    c._client.post.side_effect = None

    c._act = AsyncMock(return_value={})
    assert await c.click("t1", "#x", retry=False) is True
    c._act = AsyncMock(side_effect=RuntimeError("x"))
    assert await c.click("t1", "#x", retry=False) is False


@pytest.mark.asyncio
async def test_snapshot_wait_script_and_cookies(tmp_path):
    c = BrowserClient({"delay_min": 0.0, "delay_max": 0.0})
    c._client = _Client()
    c._focus_tab = AsyncMock()

    c._client.get.return_value = _Resp(200, text="Hello Name")
    assert await c.get_snapshot("p") == "Hello Name"
    assert await c.find_elements("p", "text='name'")

    c.get_snapshot = AsyncMock(side_effect=["text name", None])
    assert await c.wait_for_selector("p", "text='name'", timeout=10) is True
    assert await c.wait_for_selector("p", "text='name'", timeout=10) is False

    c._list_tabs = AsyncMock(side_effect=[[{"targetId": "p", "url": "https://ok"}]])
    assert await c.wait_for_url("p", "ok", timeout=10) is True

    c._client.post.return_value = _Resp(200, {"result": True})
    assert await c.execute_script("p", "1+1") is True

    shot = tmp_path / "a" / "x.png"
    c._client.post.return_value = _Resp(200, content=b"img")
    assert await c.take_screenshot("p", str(shot)) is True
    assert shot.exists()

    c._client.get.return_value = _Resp(200, payload=[{"name": "a"}])
    assert await c.get_cookies() == [{"name": "a"}]
    assert await c.add_cookie("p", {"name": "a"}) is True
    assert await c.delete_cookies() is True


@pytest.mark.asyncio
async def test_set_cookies_and_factory_helpers(monkeypatch):
    c = BrowserClient()
    c._client = _Client()
    await c.set_cookies_for_domain("a=1; bad;\n__x=2", domain=".x")
    assert c._client.post.await_count == 1

    c2 = BrowserClient()
    c2._client = _Client()
    await c2.set_cookies_for_domain("!!!!", domain=".x")
    assert c2._client.post.await_count == 0

    b = BrowserClient()
    b.connect = AsyncMock(return_value=False)
    monkeypatch.setattr("src.core.browser_client.BrowserClient", lambda cfg=None: b)
    with pytest.raises(BrowserError):
        await _create_gateway_client({})

    class Lite:
        def __init__(self, _cfg):
            self.connect = AsyncMock(return_value=False)

    monkeypatch.setattr("src.core.playwright_client.PlaywrightBrowserClient", Lite)
    with pytest.raises(BrowserError):
        await _create_lite_client({})


@pytest.mark.asyncio
async def test_set_cookies_skips_invalid_name_and_list_tabs_success_json() -> None:
    c = BrowserClient()
    c._client = _Client()
    await c.set_cookies_for_domain("=bad; good=1")
    # only valid cookie should be posted
    posted = c._client.post.await_args.kwargs["json"]["cookies"]
    assert len(posted) == 1 and posted[0]["name"] == "good"

    c._client.get.return_value = _Resp(200, payload=[{"targetId": "t1"}])
    tabs = await c._list_tabs()
    assert tabs == [{"targetId": "t1"}]

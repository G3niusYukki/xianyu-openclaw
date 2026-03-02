from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.core.error_handler import BrowserError
from src.core.playwright_client import PlaywrightBrowserClient


class DummyLocatorFirst:
    def __init__(self, text="txt", value="val", raise_on=None):
        self._text = text
        self._value = value
        self._raise_on = raise_on or set()

    async def inner_text(self):
        if "inner_text" in self._raise_on:
            raise RuntimeError("inner_text_err")
        return self._text

    async def input_value(self):
        if "input_value" in self._raise_on:
            raise RuntimeError("input_value_err")
        return self._value

    async def scroll_into_view_if_needed(self):
        if "scroll" in self._raise_on:
            raise RuntimeError("scroll_err")


class DummyLocator:
    def __init__(self, count=0, first=None, count_err=False):
        self._count = count
        self.first = first or DummyLocatorFirst()
        self._count_err = count_err

    async def count(self):
        if self._count_err:
            raise RuntimeError("count_err")
        return self._count


class DummyPage:
    def __init__(self):
        self.url = "https://old"
        self.raise_on = set()
        self.last_goto = None
        self.last_click = None
        self.last_fill = None
        self.last_type = None
        self.last_wait_selector = None
        self.last_wait_url = None
        self.last_input_files = None
        self.last_eval = None
        self.last_screenshot = None
        self.closed = False
        self._locator = DummyLocator(count=2)

    def locator(self, _selector):
        return self._locator

    async def goto(self, target, wait_until, timeout):
        if "goto" in self.raise_on:
            raise RuntimeError("goto_err")
        self.last_goto = (target, wait_until, timeout)

    async def click(self, selector, timeout):
        if "click" in self.raise_on:
            raise RuntimeError("click_err")
        self.last_click = (selector, timeout)

    async def fill(self, selector, text):
        if "fill" in self.raise_on:
            raise RuntimeError("fill_err")
        self.last_fill = (selector, text)

    async def type(self, selector, text, delay):
        if "type" in self.raise_on:
            raise RuntimeError("type_err")
        self.last_type = (selector, text, delay)

    async def wait_for_selector(self, selector, timeout, state):
        if "wait_selector" in self.raise_on:
            raise RuntimeError("wait_selector_err")
        self.last_wait_selector = (selector, timeout, state)

    async def wait_for_url(self, pattern, timeout):
        if "wait_url" in self.raise_on:
            raise RuntimeError("wait_url_err")
        self.last_wait_url = (pattern, timeout)

    async def set_input_files(self, selector, files):
        if "input_files" in self.raise_on:
            raise RuntimeError("input_files_err")
        self.last_input_files = (selector, files)

    async def evaluate(self, script):
        if "eval" in self.raise_on:
            raise RuntimeError("eval_err")
        self.last_eval = script
        if "true;" in script:
            return True
        return "EVAL_OK"

    async def screenshot(self, path, full_page):
        if "screenshot" in self.raise_on:
            raise RuntimeError("shot_err")
        self.last_screenshot = (path, full_page)

    async def close(self):
        if "close" in self.raise_on:
            raise RuntimeError("close_err")
        self.closed = True


@pytest.fixture
def patch_cfg(monkeypatch):
    cfg = SimpleNamespace(
        browser={
            "headless": False,
            "delay": {"min": 0.1, "max": 0.2},
            "viewport": {"width": 800, "height": 600},
            "user_agent": "UA",
        },
        accounts=[{"enabled": False, "cookie": ""}, {"enabled": True, "cookie": "acc_cookie=v"}],
    )
    monkeypatch.setattr("src.core.config.get_config", lambda: cfg)


@pytest.mark.asyncio
async def test_connect_no_playwright(monkeypatch, patch_cfg):
    monkeypatch.setattr("src.core.playwright_client.async_playwright", None)
    c = PlaywrightBrowserClient()
    assert await c.connect() is False


@pytest.mark.asyncio
async def test_connect_success_and_disconnect(monkeypatch, patch_cfg):
    c = PlaywrightBrowserClient({"headless": True, "timeout": 9, "delay_min": 0.0, "delay_max": 0.0})
    context = AsyncMock()
    browser = AsyncMock()
    browser.new_context = AsyncMock(return_value=context)
    chromium = SimpleNamespace(launch=AsyncMock(return_value=browser))
    pw_obj = SimpleNamespace(chromium=chromium, stop=AsyncMock())
    starter = AsyncMock(return_value=pw_obj)
    monkeypatch.setattr("src.core.playwright_client.async_playwright", lambda: SimpleNamespace(start=starter))
    monkeypatch.setenv("PLAYWRIGHT_EXECUTABLE_PATH", "/tmp/chrome")
    c.set_cookies_for_domain = AsyncMock()

    assert await c.connect() is True
    chromium.launch.assert_awaited_once_with(headless=True, executable_path="/tmp/chrome")
    browser.new_context.assert_awaited_once_with(viewport={"width": 800, "height": 600}, user_agent="UA")
    c.set_cookies_for_domain.assert_awaited_once()

    p = DummyPage()
    c._pages["p"] = p
    assert await c.close_page("p") is True
    assert p.closed is True
    await c.disconnect()
    context.close.assert_awaited()
    browser.close.assert_awaited()
    pw_obj.stop.assert_awaited()


@pytest.mark.asyncio
async def test_connect_failure_calls_disconnect(monkeypatch, patch_cfg):
    c = PlaywrightBrowserClient()
    broken_pw = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(side_effect=RuntimeError("boom"))))
    monkeypatch.setattr(
        "src.core.playwright_client.async_playwright",
        lambda: SimpleNamespace(start=AsyncMock(return_value=broken_pw)),
    )
    c.disconnect = AsyncMock()
    assert await c.connect() is False
    c.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_connection_helpers_and_page_lifecycle(monkeypatch, patch_cfg):
    c = PlaywrightBrowserClient()
    assert await c.is_connected() is False
    c.connect = AsyncMock(return_value=True)
    assert await c.ensure_connected() is True
    c._context = SimpleNamespace(new_page=AsyncMock(return_value=DummyPage()))
    page_id = await c.new_page()
    assert page_id.startswith("pw_")
    assert await c.ensure_connected() is True

    with pytest.raises(BrowserError):
        c._get_page("missing")

    assert await c.close_page("none") is False
    bad = DummyPage()
    bad.raise_on.add("close")
    c._pages["bad"] = bad
    assert await c.close_page("bad") is False


@pytest.mark.asyncio
async def test_page_actions_and_failures(monkeypatch, patch_cfg, tmp_path):
    c = PlaywrightBrowserClient({"timeout": 1, "delay_min": 0.0, "delay_max": 0.0})
    p = DummyPage()
    c._pages["p"] = p

    assert await c.navigate("p", "https://new", wait_load=False) is True
    assert p.last_goto[0] == "https://new"
    assert await c.navigate("p", "", wait_load=False) is True
    assert p.last_goto[0] == "https://old"
    p.raise_on.add("goto")
    assert await c.navigate("p", "x", wait_load=False) is False
    p.raise_on.discard("goto")

    assert await c.click("p", "#a", retry=False) is True
    p.raise_on.add("click")
    assert await c.click("p", "#a", retry=False) is False

    p.raise_on.discard("click")
    assert await c.type_text("p", "#i", "abc", clear=True) is True
    assert await c.type_text("p", "#i", "abc", clear=False) is True
    p.raise_on.add("fill")
    assert await c.type_text("p", "#i", "abc", clear=True) is False
    p.raise_on.discard("fill")

    p._locator = DummyLocator(count=3)
    assert await c.find_elements("p", ".x") == [
        {"selector": ".x", "index": 0},
        {"selector": ".x", "index": 1},
        {"selector": ".x", "index": 2},
    ]
    assert await c.find_element("p", ".x") == {"selector": ".x", "index": 0}
    p._locator = DummyLocator(count=0)
    assert await c.find_element("p", ".x") is None
    p._locator = DummyLocator(count_err=True)
    assert await c.find_elements("p", ".x") == []

    p._locator = DummyLocator(first=DummyLocatorFirst(text="T", value="V"))
    assert await c.get_text("p", ".x") == "T"
    assert await c.get_value("p", ".x") == "V"
    p._locator = DummyLocator(first=DummyLocatorFirst(raise_on={"inner_text", "input_value"}))
    assert await c.get_text("p", ".x") is None
    assert await c.get_value("p", ".x") is None

    assert await c.wait_for_selector("p", ".x", visible=True) is True
    assert await c.wait_for_selector("p", ".x", visible=False) is True
    p.raise_on.add("wait_selector")
    assert await c.wait_for_selector("p", ".x") is False
    p.raise_on.discard("wait_selector")

    assert await c.wait_for_url("p", "foo", timeout=1) is True
    p.raise_on.add("wait_url")
    assert await c.wait_for_url("p", "foo", timeout=1) is False
    p.raise_on.discard("wait_url")

    assert await c.upload_file("p", "#f", str(tmp_path / "a.txt")) is True
    assert await c.upload_files("p", "#f", ["", " "]) is False
    p.raise_on.add("input_files")
    assert await c.upload_files("p", "#f", [str(tmp_path / "b.txt")]) is False
    p.raise_on.discard("input_files")

    p._locator = DummyLocator(first=DummyLocatorFirst())
    assert await c.scroll_to_element("p", ".x") is True
    p._locator = DummyLocator(first=DummyLocatorFirst(raise_on={"scroll"}))
    assert await c.scroll_to_element("p", ".x") is False

    assert await c.execute_script("p", "1+1") == "EVAL_OK"
    p.raise_on.add("eval")
    assert await c.execute_script("p", "1+1") is None
    p.raise_on.discard("eval")

    assert await c.scroll_to_top("p") is True
    assert await c.scroll_to_bottom("p") is True
    assert await c.scroll_by("p", 1, 2) is True

    out = tmp_path / "shots" / "a.png"
    assert await c.take_screenshot("p", str(out)) is True
    p.raise_on.add("screenshot")
    assert await c.take_screenshot("p", str(out)) is False


@pytest.mark.asyncio
async def test_cookie_helpers_and_set_cookie_parsing(monkeypatch, patch_cfg):
    c = PlaywrightBrowserClient()

    assert await c.get_cookies() == []
    assert await c.add_cookie("", {"a": 1}) is False
    assert await c.delete_cookies() is False
    await c.set_cookies_for_domain("a=b")

    ctx = AsyncMock()
    c._context = ctx
    ctx.cookies = AsyncMock(return_value=[{"name": "k"}])
    assert await c.get_cookies() == [{"name": "k"}]
    ctx.cookies = AsyncMock(side_effect=RuntimeError("cookies_err"))
    assert await c.get_cookies() == []

    assert await c.add_cookie("", {"name": "n"}) is True
    ctx.add_cookies = AsyncMock(side_effect=RuntimeError("add_err"))
    assert await c.add_cookie("", {"name": "n"}) is False

    ctx.clear_cookies = AsyncMock(return_value=None)
    assert await c.delete_cookies() is True
    ctx.clear_cookies = AsyncMock(side_effect=RuntimeError("clear_err"))
    assert await c.delete_cookies() is False

    c.logger = Mock()
    c._context = AsyncMock()
    await c.set_cookies_for_domain("invalid line\n@bad=v")
    c.logger.warning.assert_called()

    c._context = AsyncMock()
    c._context.add_cookies = AsyncMock(return_value=None)
    await c.set_cookies_for_domain("a=1; b=2\nname\tvalue")
    assert c._context.add_cookies.await_count == 1

    seq = [RuntimeError("bulk_fail"), None, RuntimeError("single_fail")]

    async def add_cookies_side_effect(cookies):
        result = seq.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    c._context = AsyncMock()
    c._context.add_cookies.side_effect = add_cookies_side_effect
    c.logger = Mock()
    await c.set_cookies_for_domain("c=3; d=4")
    assert c.logger.warning.call_count >= 1

    c._context = AsyncMock()
    c._context.add_cookies = AsyncMock(side_effect=RuntimeError("always_fail"))
    with pytest.raises(RuntimeError):
        await c.set_cookies_for_domain("x=1")


def test_random_delay_and_init_cookie_env(monkeypatch, patch_cfg):
    monkeypatch.setenv("XIANYU_COOKIE_1", "env_cookie=v")
    c = PlaywrightBrowserClient({"delay_min": 1.5, "delay_max": 1.5})
    assert c.random_delay() == 1.5
    assert c._cookies_seed == "env_cookie=v"

@pytest.mark.asyncio
async def test_extra_uncovered_branches(monkeypatch, patch_cfg):
    monkeypatch.delenv("XIANYU_COOKIE_1", raising=False)
    c = PlaywrightBrowserClient()
    assert c._cookies_seed == "acc_cookie=v"

    # connect short-circuit when context already exists
    c._context = object()
    assert await c.connect() is True

    # new_page raise when ensure_connected fails / context absent
    c2 = PlaywrightBrowserClient()
    c2.ensure_connected = AsyncMock(return_value=False)
    with pytest.raises(BrowserError):
        await c2.new_page()

    # navigate wait_load=True path
    c3 = PlaywrightBrowserClient({"delay_min": 0, "delay_max": 0})
    p = DummyPage()
    c3._pages["p"] = p
    assert await c3.navigate("p", "https://ok", wait_load=True) is True

    # disconnect loop close_page branch
    c4 = PlaywrightBrowserClient()
    c4._pages = {"a": DummyPage()}
    c4.close_page = AsyncMock(return_value=True)
    await c4.disconnect()
    c4.close_page.assert_awaited_once_with("a")

    # cookie tab format invalid name path (line 339 continue)
    c.logger = Mock()
    c._context = AsyncMock()
    await c.set_cookies_for_domain("@bad\t1")
    c.logger.warning.assert_called()

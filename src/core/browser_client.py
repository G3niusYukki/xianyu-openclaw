"""
OpenClaw Gateway Browser Client

通过 HTTP 调用 OpenClaw Gateway 的 Browser Control API 实现浏览器自动化。
替代旧的 Playwright 直接调用方式，使浏览器引擎由 OpenClaw 统一管理和升级。

Gateway Browser Control API 端口 = gateway_port + 2（默认 18791）
文档: https://docs.openclaw.ai/tools/browser
"""

import asyncio
import os
import random
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import httpx

from src.core.error_handler import BrowserError
from src.core.logger import get_logger


class BrowserState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class GatewayConfig:
    host: str = "127.0.0.1"
    gateway_port: int = 18789
    token: str = ""
    profile: str = "openclaw"
    timeout: int = 30
    retry_times: int = 3
    delay_min: float = 1.0
    delay_max: float = 3.0

    @property
    def browser_port(self) -> int:
        return self.gateway_port + 2

    @property
    def browser_base_url(self) -> str:
        return f"http://{self.host}:{self.browser_port}"

    @property
    def gateway_base_url(self) -> str:
        return f"http://{self.host}:{self.gateway_port}"


class BrowserClient:
    """
    OpenClaw Gateway 浏览器客户端

    通过 HTTP 调用 Gateway 的 Browser Control API 操作浏览器。
    保持与旧 OpenClawController 近似的方法签名，降低服务层改动量。
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = GatewayConfig()
        self._apply_env()
        if config:
            self._apply_config(config)

        self.logger = get_logger()
        self.state = BrowserState.DISCONNECTED
        self._client: httpx.AsyncClient | None = None
        self._tabs: dict[str, str] = {}
        self._active_tab_id: str | None = None

    def _apply_env(self) -> None:
        if v := os.environ.get("OPENCLAW_GATEWAY_HOST"):
            self.config.host = v
        if v := os.environ.get("OPENCLAW_GATEWAY_PORT"):
            self.config.gateway_port = int(v)
        if v := os.environ.get("OPENCLAW_GATEWAY_TOKEN"):
            self.config.token = v
        if v := os.environ.get("OPENCLAW_BROWSER_PROFILE"):
            self.config.profile = v

    def _apply_config(self, config: dict[str, Any]) -> None:
        for key in ("host", "gateway_port", "token", "profile", "timeout", "retry_times", "delay_min", "delay_max"):
            if key in config:
                setattr(self.config, key, config[key])

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.config.token:
            h["Authorization"] = f"Bearer {self.config.token}"
        return h

    def _profile_params(self) -> dict[str, str]:
        return {"profile": self.config.profile}

    def random_delay(self) -> float:
        return random.uniform(self.config.delay_min, self.config.delay_max)

    # ── lifecycle ──

    async def connect(self) -> bool:
        try:
            self.state = BrowserState.CONNECTING
            self.logger.info(f"Connecting to OpenClaw Gateway at {self.config.browser_base_url} ...")

            self._client = httpx.AsyncClient(
                base_url=self.config.browser_base_url,
                headers=self._headers(),
                timeout=self.config.timeout,
            )

            resp = await self._client.get("/", params=self._profile_params())
            if resp.status_code == 200:
                self.state = BrowserState.CONNECTED
                self.logger.info("Connected to OpenClaw browser")
                return True

            if resp.status_code == 503:
                self.logger.info("Browser not running, starting...")
                start_resp = await self._client.post("/start", params=self._profile_params())
                if start_resp.status_code == 200:
                    await asyncio.sleep(2)
                    self.state = BrowserState.CONNECTED
                    self.logger.info("OpenClaw browser started")
                    return True

            self.state = BrowserState.ERROR
            self.logger.error(f"Gateway responded with status {resp.status_code}")
            return False

        except httpx.ConnectError:
            self.state = BrowserState.ERROR
            self.logger.error(
                f"Cannot reach OpenClaw Gateway at {self.config.browser_base_url}. Is the Gateway running?"
            )
            return False
        except Exception as e:
            self.state = BrowserState.ERROR
            self.logger.error(f"Connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        for tab_id in list(self._tabs.keys()):
            await self.close_page(tab_id)
        if self._client:
            await self._client.aclose()
            self._client = None
        self.state = BrowserState.DISCONNECTED
        self._active_tab_id = None
        self.logger.info("Disconnected from OpenClaw browser")

    async def is_connected(self) -> bool:
        if self.state != BrowserState.CONNECTED or not self._client:
            return False
        try:
            resp = await self._client.get("/", params=self._profile_params())
            return resp.status_code == 200
        except Exception:
            return False

    async def ensure_connected(self) -> bool:
        if not await self.is_connected():
            return await self.connect()
        return True

    # ── tabs (map to old page_id concept) ──

    async def new_page(self) -> str:
        if not await self.ensure_connected():
            raise BrowserError("Not connected to OpenClaw Gateway")

        resp = await self._client.post(
            "/tabs/open",
            params=self._profile_params(),
            json={"url": "about:blank"},
        )
        data = resp.json()
        target_id = data.get("targetId", data.get("id", f"tab_{len(self._tabs)}"))
        self._tabs[target_id] = target_id
        self.logger.debug(f"Opened tab: {target_id}")
        return target_id

    async def close_page(self, page_id: str) -> bool:
        try:
            await self._client.delete(
                f"/tabs/{page_id}",
                params=self._profile_params(),
            )
            self._tabs.pop(page_id, None)
            if self._active_tab_id == page_id:
                self._active_tab_id = None
            return True
        except Exception:
            return False

    async def _focus_tab(self, page_id: str) -> None:
        if self._active_tab_id == page_id:
            return
        await self._client.post(
            "/tabs/focus",
            params={**self._profile_params(), "targetId": page_id},
        )
        self._active_tab_id = page_id

    # ── navigation ──

    async def navigate(self, page_id: str, url: str, wait_load: bool = True) -> bool:
        self.logger.info(f"Navigating to {url}")
        await self._focus_tab(page_id)

        for attempt in range(self.config.retry_times):
            try:
                resp = await self._client.post(
                    "/navigate",
                    params=self._profile_params(),
                    json={"url": url},
                )
                if resp.status_code == 200:
                    if wait_load:
                        await asyncio.sleep(self.random_delay())
                    return True
            except Exception as e:
                self.logger.warning(f"Navigate attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(2 * (attempt + 1))

        return False

    # ── actions via POST /act ──

    async def _act(self, action: str, **kwargs) -> dict[str, Any]:
        payload = {"action": action, **kwargs}
        resp = await self._client.post(
            "/act",
            params=self._profile_params(),
            json=payload,
        )
        if resp.status_code == 200:
            return resp.json()
        raise BrowserError(f"Act '{action}' failed (HTTP {resp.status_code}): {resp.text}")

    async def click(self, page_id: str, selector: str, timeout: int = 10000, retry: bool = True) -> bool:
        self.logger.debug(f"Clicking: {selector}")
        await self._focus_tab(page_id)

        attempts = self.config.retry_times if retry else 1
        for attempt in range(attempts):
            try:
                await self._act("click", selector=selector)
                await asyncio.sleep(self.random_delay())
                return True
            except Exception as e:
                self.logger.debug(f"Click attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(1)

        self.logger.warning(f"Failed to click: {selector}")
        return False

    async def type_text(self, page_id: str, selector: str, text: str, clear: bool = True) -> bool:
        self.logger.debug(f"Typing into {selector}: {text[:50]}...")
        await self._focus_tab(page_id)
        try:
            action = "fill" if clear else "type"
            await self._act(action, selector=selector, text=text)
            await asyncio.sleep(self.random_delay())
            return True
        except Exception as e:
            self.logger.warning(f"Type text error: {e}")
            return False

    async def double_click(self, page_id: str, selector: str) -> bool:
        await self._focus_tab(page_id)
        try:
            await self._act("dblclick", selector=selector)
            return True
        except Exception:
            return False

    async def select_option(self, page_id: str, selector: str, value: str) -> bool:
        await self._focus_tab(page_id)
        try:
            await self._act("select", selector=selector, value=value)
            return True
        except Exception:
            return False

    async def check(self, page_id: str, selector: str, checked: bool = True) -> bool:
        await self._focus_tab(page_id)
        try:
            action = "check" if checked else "uncheck"
            await self._act(action, selector=selector)
            return True
        except Exception:
            return False

    # ── element queries via snapshot ──

    async def get_snapshot(self, page_id: str) -> str | None:
        await self._focus_tab(page_id)
        try:
            resp = await self._client.get("/snapshot", params=self._profile_params())
            if resp.status_code == 200:
                return resp.text
            return None
        except Exception:
            return None

    async def find_elements(self, page_id: str, selector: str) -> list:
        """
        通过 snapshot 近似查找元素。
        返回一个列表（长度表示匹配数量），用于兼容旧接口。
        """
        snapshot = await self.get_snapshot(page_id)
        if not snapshot:
            return []
        count = snapshot.lower().count(selector.split("'")[-2].lower()) if "'" in selector else 0
        return [{"selector": selector, "index": i} for i in range(max(count, 0))]

    async def find_element(self, page_id: str, selector: str):
        elements = await self.find_elements(page_id, selector)
        return elements[0] if elements else None

    async def get_text(self, page_id: str, selector: str) -> str | None:
        await self._focus_tab(page_id)
        try:
            result = await self._act("getText", selector=selector)
            return result.get("text", "")
        except Exception:
            return None

    async def get_value(self, page_id: str, selector: str) -> str | None:
        await self._focus_tab(page_id)
        try:
            result = await self._act("getValue", selector=selector)
            return result.get("value", "")
        except Exception:
            return None

    async def wait_for_selector(self, page_id: str, selector: str, timeout: int = 10000, visible: bool = True) -> bool:
        self.logger.debug(f"Waiting for selector: {selector}")
        await self._focus_tab(page_id)
        deadline = time.time() + timeout / 1000
        while time.time() < deadline:
            snapshot = await self.get_snapshot(page_id)
            if snapshot and selector.split("'")[-2].lower() in snapshot.lower() if "'" in selector else False:
                return True
            await asyncio.sleep(1)
        self.logger.warning(f"Timeout waiting for: {selector}")
        return False

    async def wait_for_url(self, page_id: str, pattern: str, timeout: int = 30000) -> bool:
        deadline = time.time() + timeout / 1000
        while time.time() < deadline:
            tabs = await self._list_tabs()
            for tab in tabs:
                if tab.get("targetId") == page_id and pattern in tab.get("url", ""):
                    return True
            await asyncio.sleep(1)
        return False

    # ── file upload ──

    async def upload_file(self, page_id: str, selector: str, file_path: str) -> bool:
        self.logger.info(f"Uploading file: {file_path}")
        if not file_path:
            return False
        await self._focus_tab(page_id)
        try:
            await self._client.post(
                "/hooks/file-chooser",
                params=self._profile_params(),
                json={"files": [file_path]},
            )
            await self.click(page_id, selector, retry=False)
            await asyncio.sleep(self.random_delay() * 2)
            self.logger.info(f"Uploaded: {file_path}")
            return True
        except Exception as e:
            self.logger.error(f"Upload error: {e}")
            return False

    async def upload_files(self, page_id: str, selector: str, file_paths: list[str]) -> bool:
        if not file_paths:
            return True
        self.logger.info(f"Uploading {len(file_paths)} files")
        await self._focus_tab(page_id)
        try:
            await self._client.post(
                "/hooks/file-chooser",
                params=self._profile_params(),
                json={"files": file_paths},
            )
            await self.click(page_id, selector, retry=False)
            await asyncio.sleep(self.random_delay() * len(file_paths))
            return True
        except Exception as e:
            self.logger.error(f"Batch upload error: {e}")
            return False

    # ── scroll ──

    async def scroll_to_element(self, page_id: str, selector: str) -> bool:
        await self._focus_tab(page_id)
        try:
            await self._act("scrollIntoView", selector=selector)
            return True
        except Exception:
            return False

    async def scroll_to_top(self, page_id: str) -> bool:
        return await self.execute_script(page_id, "window.scrollTo(0, 0); true;") is True

    async def scroll_to_bottom(self, page_id: str) -> bool:
        return await self.execute_script(page_id, "window.scrollTo(0, document.body.scrollHeight); true;") is True

    async def scroll_by(self, page_id: str, x: int, y: int) -> bool:
        script = f"window.scrollBy({x}, {y}); true;"
        return await self.execute_script(page_id, script) is True

    # ── execute script ──

    async def execute_script(self, page_id: str, script: str) -> Any:
        await self._focus_tab(page_id)
        try:
            resp = await self._client.post(
                "/act",
                params=self._profile_params(),
                json={"action": "evaluate", "expression": script},
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("result", data)
            return None
        except Exception as e:
            self.logger.debug(f"Script execution error: {e}")
            return None

    # ── screenshot ──

    async def take_screenshot(self, page_id: str, path: str) -> bool:
        await self._focus_tab(page_id)
        try:
            resp = await self._client.post(
                "/screenshot",
                params=self._profile_params(),
                json={"fullPage": False},
            )
            if resp.status_code == 200:
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                Path(path).write_bytes(resp.content)
                return True
            return False
        except Exception as e:
            self.logger.error(f"Screenshot error: {e}")
            return False

    # ── cookies ──

    async def get_cookies(self, page_id: str = "") -> list[dict[str, str]]:
        try:
            resp = await self._client.get("/cookies", params=self._profile_params())
            if resp.status_code == 200:
                return resp.json()
            return []
        except Exception:
            return []

    async def add_cookie(self, page_id: str, cookie: dict[str, str]) -> bool:
        try:
            await self._client.post(
                "/cookies/set",
                params=self._profile_params(),
                json={"cookies": [cookie]},
            )
            return True
        except Exception:
            return False

    async def delete_cookies(self, page_id: str = "", name: str | None = None) -> bool:
        try:
            await self._client.post("/cookies/clear", params=self._profile_params())
            return True
        except Exception:
            return False

    async def set_cookies_for_domain(self, cookies_str: str, domain: str = ".goofish.com") -> None:
        cookies = []
        for item in cookies_str.split(";"):
            item = item.strip()
            if "=" in item:
                name, value = item.split("=", 1)
                cookies.append(
                    {
                        "name": name.strip(),
                        "value": value.strip(),
                        "domain": domain,
                        "path": "/",
                    }
                )
        if cookies:
            await self._client.post(
                "/cookies/set",
                params=self._profile_params(),
                json={"cookies": cookies},
            )
            self.logger.info(f"Set {len(cookies)} cookies for {domain}")

    # ── navigation helpers ──

    async def reload(self, page_id: str) -> bool:
        return await self.navigate(page_id, "", wait_load=True)

    async def go_back(self, page_id: str) -> bool:
        try:
            await self._act("goBack")
            return True
        except Exception:
            return False

    async def go_forward(self, page_id: str) -> bool:
        try:
            await self._act("goForward")
            return True
        except Exception:
            return False

    async def get_page_source(self, page_id: str) -> str | None:
        return await self.get_snapshot(page_id)

    async def handle_dialog(self, page_id: str, accept: bool = True, text: str = "") -> bool:
        try:
            await self._client.post(
                "/hooks/dialog",
                params=self._profile_params(),
                json={"accept": accept, "promptText": text},
            )
            return True
        except Exception:
            return False

    # ── internal helpers ──

    async def _list_tabs(self) -> list[dict[str, Any]]:
        try:
            resp = await self._client.get("/tabs", params=self._profile_params())
            if resp.status_code == 200:
                return resp.json()
            return []
        except Exception:
            return []


async def create_browser_client(config: dict[str, Any] | None = None) -> "BrowserClient":
    """创建并连接浏览器客户端"""
    client = BrowserClient(config)
    connected = await client.connect()
    if not connected:
        raise BrowserError("Failed to connect to OpenClaw Gateway. Is the Gateway running? Check: docker compose ps")
    return client

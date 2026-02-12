"""
OpenClaw浏览器控制器
OpenClaw Browser Controller

提供与OpenClaw实例的连接和浏览器操作能力
"""

import asyncio
import json
import time
import random
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum

import httpx
from src.core.config import get_config
from src.core.logger import get_logger
from src.core.error_handler import handle_controller_errors, handle_operation_errors


class BrowserState(Enum):
    """浏览器状态"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class BrowserConfig:
    """浏览器配置"""
    host: str = "localhost"
    port: int = 9222
    timeout: int = 30
    retry_times: int = 3
    headless: bool = True
    delay_min: float = 1.0
    delay_max: float = 3.0


class ElementInfo:
    """元素信息"""
    def __init__(self, object_id: str, node_type: str = "", tag_name: str = ""):
        self.object_id = object_id
        self.node_type = node_type
        self.tag_name = tag_name

    @classmethod
    def from_response(cls, response: Dict) -> Optional['ElementInfo']:
        if response and response.get('result'):
            return cls(
                object_id=response['result'].get('objectId', ''),
                node_type=response['result'].get('nodeName', ''),
                tag_name=response['result'].get('nodeName', '')
            )
        return None


class OpenClawController:
    """
    OpenClaw浏览器控制器

    负责与OpenClaw实例建立连接，提供浏览器操作API
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化控制器

        Args:
            config: 配置字典，不指定则从配置文件加载
        """
        self.config = BrowserConfig()
        if config:
            self._apply_config(config)
        else:
            cfg = get_config()
            openclaw_cfg = cfg.openclaw
            browser_cfg = cfg.browser
            self._apply_config({
                "host": openclaw_cfg.get("host", "localhost"),
                "port": openclaw_cfg.get("port", 9222),
                "timeout": openclaw_cfg.get("timeout", 30),
                "retry_times": openclaw_cfg.get("retry_times", 3),
                "headless": browser_cfg.get("headless", True),
                "delay_min": browser_cfg.get("delay", {}).get("min", 1.0),
                "delay_max": browser_cfg.get("delay", {}).get("max", 3.0),
            })

        self.logger = get_logger()
        self.state = BrowserState.DISCONNECTED
        self.client: Optional[httpx.AsyncClient] = None
        self._base_url: str = ""
        self.current_page_id: Optional[str] = None

    def _apply_config(self, config: Dict[str, Any]) -> None:
        """应用配置"""
        self.config.host = config.get("host", self.config.host)
        self.config.port = config.get("port", self.config.port)
        self.config.timeout = config.get("timeout", self.config.timeout)
        self.config.retry_times = config.get("retry_times", self.config.retry_times)
        self.config.headless = config.get("headless", self.config.headless)
        self.config.delay_min = config.get("delay_min", self.config.delay_min)
        self.config.delay_max = config.get("delay_max", self.config.delay_max)

    @property
    def base_url(self) -> str:
        """获取基础URL"""
        if not self._base_url:
            self._base_url = f"http://{self.config.host}:{self.config.port}"
        return self._base_url

    def random_delay(self) -> float:
        """生成随机延迟"""
        return random.uniform(self.config.delay_min, self.config.delay_max)

    async def connect(self) -> bool:
        """
        连接到OpenClaw实例

        Returns:
            是否连接成功
        """
        try:
            self.state = BrowserState.CONNECTING
            self.logger.info(f"Connecting to OpenClaw at {self.base_url}...")

            self.client = httpx.AsyncClient(
                timeout=self.config.timeout,
                follow_redirects=True
            )

            response = await self.client.get(f"{self.base_url}/json/version")
            if response.status_code == 200:
                version_info = response.json()
                self.state = BrowserState.CONNECTED
                self.logger.success(f"Connected to OpenClaw: {version_info.get('Browser', 'Unknown')}")
                return True
            else:
                self.state = BrowserState.ERROR
                self.logger.error(f"Failed to connect: {response.status_code}")
                return False

        except Exception as e:
            self.state = BrowserState.ERROR
            self.logger.error(f"Connection error: {e}")
            return False

    async def disconnect(self) -> None:
        """断开连接"""
        if self.current_page_id:
            await self.close_page(self.current_page_id)
        if self.client:
            await self.client.aclose()
            self.client = None
        self.state = BrowserState.DISCONNECTED
        self.logger.info("Disconnected from OpenClaw")

    @handle_controller_errors(default_return=False)
    async def is_connected(self) -> bool:
        """检查连接状态"""
        if self.state != BrowserState.CONNECTED:
            return False
        response = await self.client.get(f"{self.base_url}/json/version")
        return response.status_code == 200

    async def ensure_connected(self) -> bool:
        """确保已连接"""
        if not await self.is_connected():
            return await self.connect()
        return True

    async def new_page(self) -> str:
        """创建新页面"""
        if not await self.ensure_connected():
            raise ConnectionError("Not connected to OpenClaw")

        response = await self.client.post(f"{self.base_url}/json/prototype/Page")
        if response.status_code == 200:
            self.current_page_id = response.json().get("id")
            self.logger.debug(f"Created new page: {self.current_page_id}")
            return self.current_page_id
        else:
            raise Exception(f"Failed to create page: {response.text}")

    @handle_operation_errors(default_return=False)
    async def close_page(self, page_id: str) -> bool:
        """关闭页面"""
        response = await self.client.send(
            f"{self.base_url}/json/prototype/Page/{page_id}/close",
            method="DELETE"
        )
        if page_id == self.current_page_id:
            self.current_page_id = None
        return response.status_code == 200

    async def navigate(self, page_id: str, url: str, wait_load: bool = True) -> bool:
        """
        导航到URL

        Args:
            page_id: 页面ID
            url: 目标URL
            wait_load: 是否等待页面加载完成

        Returns:
            是否成功
        """
        self.logger.info(f"Navigating to {url}")

        for attempt in range(self.config.retry_times):
            try:
                response = await self.client.post(
                    f"{self.base_url}/json/prototype/Page/{page_id}/navigate",
                    json={"url": url}
                )

                if response.status_code == 200:
                    if wait_load:
                        await asyncio.sleep(self.random_delay())
                    self.logger.debug(f"Navigated to {url}")
                    return True
                else:
                    self.logger.warning(f"Navigate failed (attempt {attempt + 1})")

            except Exception as e:
                self.logger.warning(f"Navigate error (attempt {attempt + 1}): {e}")

            await asyncio.sleep(2 * (attempt + 1))

        return False

    async def find_element(self, page_id: str, selector: str) -> Optional[ElementInfo]:
        """
        查找单个元素

        Args:
            page_id: 页面ID
            selector: CSS选择器

        Returns:
            元素信息，未找到返回None
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/json/prototype/Page/{page_id}/querySelector",
                json={"selector": selector}
            )

            if response.status_code == 200:
                return ElementInfo.from_response(response.json())
            return None
        except Exception as e:
            self.logger.debug(f"Find element error: {e}")
            return None

    async def find_elements(self, page_id: str, selector: str) -> List[ElementInfo]:
        """
        查找多个元素

        Args:
            page_id: 页面ID
            selector: CSS选择器

        Returns:
            元素信息列表
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/json/prototype/Page/{page_id}/querySelectorAll",
                json={"selector": selector}
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("result") and result["result"].get("nodeIds"):
                    return [
                        ElementInfo(object_id=oid)
                        for oid in result["result"]["nodeIds"]
                    ]
            return []
        except Exception as e:
            self.logger.debug(f"Find elements error: {e}")
            return []

    async def click(self, page_id: str, selector: str,
                    timeout: int = 10, retry: bool = True) -> bool:
        """
        点击元素

        Args:
            page_id: 页面ID
            selector: CSS选择器
            timeout: 超时时间
            retry: 是否重试

        Returns:
            是否成功
        """
        self.logger.debug(f"Clicking: {selector}")

        for attempt in range(self.config.retry_times) if retry else [0]:
            element = await self.find_element(page_id, selector)
            if element:
                try:
                    response = await self.client.post(
                        f"{self.base_url}/json/prototype/Node/{element.object_id}/click",
                        json={}
                    )
                    if response.status_code == 200:
                        await asyncio.sleep(self.random_delay())
                        return True
                except Exception as e:
                    self.logger.debug(f"Click error: {e}")

            await asyncio.sleep(1)

        self.logger.warning(f"Failed to click: {selector}")
        return False

    @handle_operation_errors(default_return=False)
    async def double_click(self, page_id: str, selector: str) -> bool:
        """双击元素"""
        element = await self.find_element(page_id, selector)
        if element:
            response = await self.client.post(
                f"{self.base_url}/json/prototype/Node/{element.object_id}/click",
                json={"clickCount": 2}
            )
            return response.status_code == 200
        return False

    async def type_text(self, page_id: str, selector: str, text: str,
                        clear: bool = True) -> bool:
        """
        输入文本

        Args:
            page_id: 页面ID
            selector: CSS选择器
            text: 输入文本
            clear: 是否先清空

        Returns:
            是否成功
        """
        self.logger.debug(f"Typing into {selector}: {text[:50]}...")

        element = await self.find_element(page_id, selector)
        if not element:
            self.logger.warning(f"Element not found: {selector}")
            return False

        try:
            if clear:
                await self.client.post(
                    f"{self.base_url}/json/prototype/Node/{element.object_id}/setInputValue",
                    json={"text": ""}
                )
                await asyncio.sleep(0.2)

            response = await self.client.post(
                f"{self.base_url}/json/prototype/Node/{element.object_id}/setInputValue",
                json={"text": text}
            )

            if response.status_code == 200:
                await asyncio.sleep(self.random_delay())
                return True

        except Exception as e:
            self.logger.debug(f"Type text error: {e}")

        return False

    @handle_operation_errors(default_return=None)
    async def get_text(self, page_id: str, selector: str) -> Optional[str]:
        """获取元素文本"""
        element = await self.find_element(page_id, selector)
        if element:
            response = await self.client.post(
                f"{self.base_url}/json/prototype/Node/{element.object_id}/getProperties",
                json={"name": "textContent"}
            )
            if response.status_code == 200:
                return response.json().get("value", "")
        return None

    @handle_operation_errors(default_return=None)
    async def get_value(self, page_id: str, selector: str) -> Optional[str]:
        """获取输入框值"""
        element = await self.find_element(page_id, selector)
        if element:
            response = await self.client.post(
                f"{self.base_url}/json/prototype/Node/{element.object_id}/getProperties",
                json={"name": "value"}
            )
            if response.status_code == 200:
                return response.json().get("value", "")
        return None

    @handle_operation_errors(default_return=False)
    async def select_option(self, page_id: str, selector: str, value: str) -> bool:
        """选择下拉选项"""
        element = await self.find_element(page_id, selector)
        if element:
            response = await self.client.post(
                f"{self.base_url}/json/prototype/Node/{element.object_id}/select",
                json={"value": value}
            )
            return response.status_code == 200
        return False

    @handle_operation_errors(default_return=False)
    async def check(self, page_id: str, selector: str, checked: bool = True) -> bool:
        """勾选/取消勾选复选框"""
        element = await self.find_element(page_id, selector)
        if element:
            response = await self.client.post(
                f"{self.base_url}/json/prototype/Node/{element.object_id}/setProperty",
                json={"name": "checked", "value": str(checked).lower()}
            )
            return response.status_code == 200
        return False

    async def upload_file(self, page_id: str, selector: str, file_path: str) -> bool:
        """
        上传文件

        Args:
            page_id: 页面ID
            selector: 文件输入框选择器
            file_path: 文件路径

        Returns:
            是否成功
        """
        self.logger.info(f"Uploading file: {file_path}")

        if not file_path:
            return False

        element = await self.find_element(page_id, selector)
        if not element:
            self.logger.warning(f"Upload element not found: {selector}")
            return False

        try:
            response = await self.client.post(
                f"{self.base_url}/json/prototype/Node/{element.object_id}/setInputFiles",
                json={"files": [file_path]}
            )

            if response.status_code == 200:
                self.logger.success(f"Uploaded: {file_path}")
                await asyncio.sleep(self.random_delay() * 2)
                return True

        except Exception as e:
            self.logger.error(f"Upload error: {e}")

        return False

    async def upload_files(self, page_id: str, selector: str,
                          file_paths: List[str]) -> bool:
        """
        批量上传文件

        Args:
            page_id: 页面ID
            selector: 文件输入框选择器
            file_paths: 文件路径列表

        Returns:
            是否成功
        """
        if not file_paths:
            return True

        self.logger.info(f"Uploading {len(file_paths)} files")

        element = await self.find_element(page_id, selector)
        if not element:
            return False

        try:
            response = await self.client.post(
                f"{self.base_url}/json/prototype/Node/{element.object_id}/setInputFiles",
                json={"files": file_paths}
            )

            if response.status_code == 200:
                await asyncio.sleep(self.random_delay() * len(file_paths))
                return True

        except Exception as e:
            self.logger.error(f"Batch upload error: {e}")

        return False

    async def wait_for_selector(self, page_id: str, selector: str,
                                timeout: int = 10, visible: bool = True) -> bool:
        """
        等待元素出现

        Args:
            page_id: 页面ID
            selector: CSS选择器
            timeout: 超时时间（秒）
            visible: 是否等待可见

        Returns:
            是否找到元素
        """
        self.logger.debug(f"Waiting for selector: {selector}")

        start_time = time.time()
        while time.time() - start_time < timeout:
            element = await self.find_element(page_id, selector)
            if element:
                self.logger.debug(f"Found selector: {selector}")
                return True
            await asyncio.sleep(0.5)

        self.logger.warning(f"Timeout waiting for selector: {selector}")
        return False

    async def wait_for_url(self, page_id: str, pattern: str,
                          timeout: int = 30) -> bool:
        """
        等待URL变化

        Args:
            page_id: 页面ID
            pattern: URL匹配模式
            timeout: 超时时间

        Returns:
            是否匹配成功
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = await self.client.get(
                    f"{self.base_url}/json/prototype/Page/{page_id}/getURL"
                )
                if response.status_code == 200:
                    url = response.json().get("result", "")
                    if pattern in url:
                        return True
            except Exception as e:
                self.logger.debug(f"Error checking URL: {e}")
            await asyncio.sleep(0.5)
        return False

    async def scroll_to_element(self, page_id: str, selector: str) -> bool:
        """滚动到元素"""
        script = f"""
            const element = document.querySelector('{selector}');
            if (element) {{
                element.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                true;
            }} else {{
                false;
            }}
        """
        return await self.execute_script(page_id, script) is True

    async def scroll_to_top(self, page_id: str) -> bool:
        """滚动到顶部"""
        return await self.execute_script(page_id, "window.scrollTo(0, 0); true;") is True

    async def scroll_to_bottom(self, page_id: str) -> bool:
        """滚动到底部"""
        return await self.execute_script(page_id, "window.scrollTo(0, document.body.scrollHeight); true;") is True

    async def scroll_by(self, page_id: str, x: int, y: int) -> bool:
        """滚动页面"""
        script = f"window.scrollBy({x}, {y}); true;"
        return await self.execute_script(page_id, script) is True

    async def execute_script(self, page_id: str, script: str) -> Any:
        """
        执行JavaScript脚本

        Args:
            page_id: 页面ID
            script: JavaScript代码

        Returns:
            脚本执行结果
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/json/prototype/Page/{page_id}/evaluate",
                json={"expression": script}
            )

            if response.status_code == 200:
                return response.json().get("result")
            return None
        except Exception as e:
            self.logger.debug(f"Script execution error: {e}")
            return None

    async def take_screenshot(self, page_id: str, path: str) -> bool:
        """
        截图

        Args:
            page_id: 页面ID
            path: 保存路径

        Returns:
            是否成功
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/json/prototype/Page/{page_id}/screenshot",
                json={"path": path}
            )
            return response.status_code == 200
        except Exception as e:
            self.logger.error(f"Screenshot error: {e}")
            return False

    @handle_operation_errors(default_return=[])
    async def get_cookies(self, page_id: str) -> List[Dict[str, str]]:
        """获取页面Cookie"""
        response = await self.client.get(
            f"{self.base_url}/json/prototype/Page/{page_id}/getCookies"
        )
        if response.status_code == 200:
            return response.json().get("cookies", [])
        return []

    @handle_operation_errors(default_return=False)
    async def add_cookie(self, page_id: str, cookie: Dict[str, str]) -> bool:
        """添加Cookie"""
        response = await self.client.post(
            f"{self.base_url}/json/prototype/Page/{page_id}/addCookie",
            json={"cookie": cookie}
        )
        return response.status_code == 200

    @handle_operation_errors(default_return=False)
    async def delete_cookies(self, page_id: str, name: Optional[str] = None) -> bool:
        """删除Cookie"""
        url = f"{self.base_url}/json/prototype/Page/{page_id}/clearCookies"
        if name:
            url += f"?name={name}"
        response = await self.client.send(url, method="DELETE")
        return response.status_code == 200

    @handle_operation_errors(default_return=False)
    async def reload(self, page_id: str) -> bool:
        """刷新页面"""
        response = await self.client.post(
            f"{self.base_url}/json/prototype/Page/{page_id}/reload"
        )
        return response.status_code == 200

    @handle_operation_errors(default_return=False)
    async def go_back(self, page_id: str) -> bool:
        """返回上一页"""
        response = await self.client.post(
            f"{self.base_url}/json/prototype/Page/{page_id}/goBack"
        )
        return response.status_code == 200

    @handle_operation_errors(default_return=False)
    async def go_forward(self, page_id: str) -> bool:
        """前进一页"""
        response = await self.client.post(
            f"{self.base_url}/json/prototype/Page/{page_id}/goForward"
        )
        return response.status_code == 200

    @handle_operation_errors(default_return=None)
    async def get_page_source(self, page_id: str) -> Optional[str]:
        """获取页面源码"""
        response = await self.client.post(
            f"{self.base_url}/json/prototype/Page/{page_id}/getContent"
        )
        if response.status_code == 200:
            return response.json().get("result", "")
        return None

    @handle_operation_errors(default_return=False)
    async def handle_dialog(self, page_id: str, accept: bool = True,
                           text: str = "") -> bool:
        """
        处理对话框

        Args:
            page_id: 页面ID
            accept: 是否接受（True=确定，False=取消）
            text: 输入文本（prompt时使用）

        Returns:
            是否成功
        """
        response = await self.client.post(
            f"{self.base_url}/json/prototype/Page/{page_id}/handleDialog",
            json={"accept": accept, "promptText": text}
        )
        return response.status_code == 200


async def create_controller(config: Optional[Dict[str, Any]] = None) -> OpenClawController:
    """
    创建并连接控制器

    Args:
        config: 配置字典

    Returns:
        OpenClawController实例
    """
    controller = OpenClawController(config)
    connected = await controller.connect()
    if not connected:
        raise ConnectionError(f"Failed to connect to OpenClaw at {controller.base_url}")
    return controller

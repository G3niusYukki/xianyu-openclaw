"""
测试工具和fixtures
Test Utilities and Fixtures
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import Config
from src.core.logger import Logger


@pytest.fixture
def temp_dir():
    """创建临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_config_file(temp_dir):
    """创建临时配置文件"""
    config_file = temp_dir / "config.yaml"
    config_content = """
app:
  name: "xianyu-openclaw"
  version: "1.0.0"
  debug: true
  log_level: "DEBUG"

openclaw:
  host: "localhost"
  port: 9222
  timeout: 30
  retry_times: 3

ai:
  provider: "deepseek"
  api_key: "test_api_key"
  base_url: "https://api.test.com/v1"
  model: "deepseek-chat"
  temperature: 0.7
  max_tokens: 1000
  timeout: 30

database:
  type: "sqlite"
  path: ":memory:"
  max_connections: 5
  timeout: 30

accounts:
  - id: "test_account_1"
    name: "测试账号1"
    cookie: "test_cookie_1"
    priority: 1
    enabled: true
  - id: "test_account_2"
    name: "测试账号2"
    cookie: "test_cookie_2"
    priority: 2
    enabled: true

default_account: "test_account_1"

media:
  max_image_size: 5242880
  supported_formats: ["jpg", "jpeg", "png", "webp"]
  output_format: "jpeg"
  output_quality: 85
  max_width: 1500
  max_height: 1500

browser:
  headless: true
  viewport:
    width: 1280
    height: 800
  delay:
    min: 1.0
    max: 3.0
  upload_timeout: 60
"""
    config_file.write_text(config_content)
    return config_file


@pytest.fixture
def mock_controller():
    """Mock OpenClaw控制器"""
    controller = Mock()
    controller.connect = AsyncMock(return_value=True)
    controller.disconnect = AsyncMock(return_value=True)
    controller.is_connected = AsyncMock(return_value=True)
    controller.new_page = AsyncMock(return_value="page_test_id")
    controller.close_page = AsyncMock(return_value=True)
    controller.navigate = AsyncMock(return_value=True)
    controller.find_element = AsyncMock(return_value=Mock(object_id="element_id"))
    controller.find_elements = AsyncMock(return_value=[])
    controller.click = AsyncMock(return_value=True)
    controller.type_text = AsyncMock(return_value=True)
    controller.upload_files = AsyncMock(return_value=True)
    controller.upload_file = AsyncMock(return_value=True)
    controller.execute_script = AsyncMock(return_value=True)
    controller.take_screenshot = AsyncMock(return_value=True)
    controller.get_cookies = AsyncMock(return_value=[])
    controller.add_cookie = AsyncMock(return_value=True)
    controller.wait_for_selector = AsyncMock(return_value=True)
    controller.wait_for_url = AsyncMock(return_value=True)
    return controller


@pytest.fixture
def mock_http_client():
    """Mock HTTP客户端"""
    client = AsyncMock()
    response = AsyncMock()
    response.status_code = 200
    response.json.return_value = {"Browser": "Chrome"}
    response.text = "OK"
    client.get.return_value = response
    client.post.return_value = response
    client.send.return_value = response
    return client


@pytest.fixture
def mock_ai_client():
    """Mock AI客户端"""
    client = Mock()
    response = Mock()
    response.choices = [Mock()]
    response.choices[0].message.content = "Generated content"
    client.chat.completions.create.return_value = response
    return client


@pytest.fixture
def sample_listing_data():
    """示例商品数据"""
    return {
        "title": "iPhone 15 Pro Max 256GB",
        "description": "全新未拆封，原装正品",
        "price": 8999.0,
        "original_price": 9999.0,
        "category": "数码手机",
        "images": ["test_image1.jpg", "test_image2.jpg"],
        "tags": ["苹果", "iPhone", "全新"],
        "features": ["256GB", "原装", "国行"]
    }


@pytest.fixture
def sample_images(temp_dir):
    """创建示例图片文件"""
    images = []
    for i in range(3):
        image_path = temp_dir / f"test_image_{i}.jpg"
        image_path.write_bytes(b"fake image data")
        images.append(str(image_path))
    return images


@pytest.fixture
def sample_account_data():
    """示例账号数据"""
    return [
        {
            "id": "account_1",
            "name": "主账号",
            "cookie": "test_cookie_1_abcdefg",
            "priority": 1,
            "enabled": True
        },
        {
            "id": "account_2",
            "name": "副账号",
            "cookie": "test_cookie_2_abcdefg",
            "priority": 2,
            "enabled": True
        }
    ]


@pytest.fixture
def sample_metrics_data():
    """示例指标数据"""
    return [
        {
            "date": "2024-01-01",
            "views": 100,
            "wants": 10,
            "sales": 2,
            "inquiries": 15
        },
        {
            "date": "2024-01-02",
            "views": 120,
            "wants": 12,
            "sales": 3,
            "inquiries": 18
        },
        {
            "date": "2024-01-03",
            "views": 90,
            "wants": 8,
            "sales": 1,
            "inquiries": 12
        }
    ]


@pytest.fixture
def config(temp_config_file):
    """测试配置实例"""
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("OPENAI_API_KEY", "test_openai_key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test_deepseek_key")

    config = Config(str(temp_config_file))
    yield config

    monkeypatch.undo()


@pytest.fixture
def logger(temp_dir, config):
    """测试日志实例"""
    logger = Logger()
    yield logger


def create_mock_listing(**kwargs):
    """创建Mock商品对象"""
    from src.modules.listing.models import Listing

    defaults = {
        "title": "Test Product",
        "description": "Test Description",
        "price": 100.0,
        "category": "General",
        "images": []
    }
    defaults.update(kwargs)

    return Listing(**defaults)


def create_mock_publish_result(success=True, **kwargs):
    """创建Mock发布结果"""
    from src.modules.listing.models import PublishResult

    defaults = {
        "success": success,
        "product_id": "test_product_id" if success else None,
        "product_url": "https://test.url/product/test_product_id" if success else None,
        "error_message": None if success else "Test error"
    }
    defaults.update(kwargs)

    return PublishResult(**defaults)


class AsyncContextManager:
    """异步上下文管理器"""

    def __init__(self, return_value=None):
        self.return_value = return_value
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self.return_value

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.exited = True
        return False


def async_return(value):
    """创建返回值的协程"""
    f = asyncio.Future()
    f.set_result(value)
    return f


def async_raise(exc):
    """创建抛出异常的协程"""
    async def coro():
        raise exc

    return coro()


def skip_if_no_browser():
    """如果浏览器不可用则跳过测试"""
    return pytest.mark.skipif(
        not os.getenv("BROWSER_TEST", "false").lower() == "true",
        reason="Browser tests disabled (set BROWSER_TEST=true to enable)"
    )


def skip_if_no_ai():
    """如果AI服务不可用则跳过测试"""
    return pytest.mark.skipif(
        not os.getenv("AI_API_KEY"),
        reason="AI tests disabled (set AI_API_KEY to enable)"
    )

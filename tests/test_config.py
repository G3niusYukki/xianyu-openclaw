"""
配置模块单元测试
Config Module Unit Tests
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.core.config import Config
from src.core.config_models import (
    AccountConfig,
    AIConfig,
    BrowserConfig,
    ConfigModel,
    DatabaseConfig,
    MediaConfig,
    OpenClawConfig,
    Provider,
)


class TestConfig:
    """配置管理类测试"""

    def test_config_singleton(self):
        """测试单例模式"""
        config1 = Config()
        config2 = Config()
        assert config1 is config2

    def test_config_load_from_yaml(self, temp_config_file):
        """测试从YAML加载配置"""
        config = Config(str(temp_config_file))
        assert config.get("app.name") == "xianyu-openclaw"
        assert config.get("openclaw.port") == 9222

    def test_config_get_section(self, config):
        """测试获取配置段落"""
        app_config = config.get_section("app")
        assert app_config["name"] == "xianyu-openclaw"
        assert app_config["version"] == "1.0.0"

    def test_config_get_value(self, config):
        """测试获取配置值"""
        assert config.get("app.name") == "xianyu-openclaw"
        assert config.get("openclaw.port") == 9222
        assert config.get("nonexistent.key", "default") == "default"

    def test_config_reload(self, temp_config_file, temp_dir):
        """测试重新加载配置"""
        config = Config(str(temp_config_file))
        assert config.get("app.name") == "xianyu-openclaw"

        # 修改配置文件
        config_content = """
app:
  name: "updated_name"
  version: "1.0.0"
"""
        temp_config_file.write_text(config_content)

        config.reload()
        assert config.get("app.name") == "updated_name"

    def test_config_missing_file(self, temp_dir):
        """测试配置文件不存在"""
        config = Config(str(temp_dir / "nonexistent.yaml"))
        assert config.get("app.name") == "xianyu-openclaw"  # 使用默认值


class TestConfigModels:
    """配置模型测试"""

    def test_openclaw_config_defaults(self):
        """测试OpenClaw配置默认值"""
        config = OpenClawConfig()
        assert config.host == "localhost"
        assert config.port == 9222
        assert config.timeout == 30
        assert config.retry_times == 3

    def test_openclaw_config_validation(self):
        """测试OpenClaw配置验证"""
        # 有效配置
        config = OpenClawConfig(port=8080, timeout=60)
        assert config.port == 8080
        assert config.timeout == 60

        # 无效端口
        with pytest.raises(ValidationError):
            OpenClawConfig(port=70000)

        # 无效超时
        with pytest.raises(ValidationError):
            OpenClawConfig(timeout=0)

    def test_ai_config_provider_validation(self):
        """测试AI配置provider验证"""
        # 有效provider
        config = AIConfig(provider=Provider.DEEPSEEK)
        assert config.provider == Provider.DEEPSEEK

        # 无效provider
        with pytest.raises(ValidationError):
            AIConfig(provider="invalid")

    def test_ai_config_defaults(self):
        """测试AI配置默认值"""
        config = AIConfig()
        assert config.provider == Provider.DEEPSEEK
        assert config.model == "deepseek-chat"
        assert config.temperature == 0.7
        assert config.max_tokens == 1000
        assert config.timeout == 30

    def test_database_config_defaults(self):
        """测试数据库配置默认值"""
        config = DatabaseConfig()
        assert config.type == "sqlite"
        assert config.path == "data/agent.db"
        assert config.max_connections == 5

    def test_account_config_validation(self):
        """测试账号配置验证"""
        config = AccountConfig(
            id="test_account",
            name="测试账号",
            cookie="test_cookie",
            priority=5,
            enabled=True
        )
        assert config.id == "test_account"
        assert config.name == "测试账号"
        assert config.priority == 5

        # 无效priority
        with pytest.raises(ValidationError):
            AccountConfig(id="test", name="Test", cookie="test", priority=0)

    def test_browser_config_defaults(self):
        """测试浏览器配置默认值"""
        config = BrowserConfig()
        assert config.headless is True
        assert config.viewport["width"] == 1280
        assert config.viewport["height"] == 800
        assert config.delay["min"] == 1.0
        assert config.delay["max"] == 3.0

    def test_media_config_defaults(self):
        """测试媒体配置默认值"""
        config = MediaConfig()
        assert config.max_image_size == 5242880
        assert "jpg" in config.supported_formats
        assert config.output_format == "jpeg"
        assert config.output_quality == 85
        assert config.max_width == 1500
        assert config.max_height == 1500

    def test_config_model_full_validation(self):
        """测试完整配置模型验证"""
        config_data = {
            "app": {
                "name": "test_app",
                "version": "1.0.0",
                "debug": True,
                "log_level": "DEBUG"
            },
            "openclaw": {
                "host": "localhost",
                "port": 9222
            },
            "ai": {
                "provider": "deepseek",
                "model": "deepseek-chat"
            },
            "database": {
                "type": "sqlite",
                "path": ":memory:"
            },
            "accounts": [
                {
                    "id": "account_1",
                    "name": "测试账号",
                    "cookie": "test_cookie",
                    "priority": 1,
                    "enabled": True
                }
            ],
            "default_account": "account_1"
        }

        config = ConfigModel.from_dict(config_data)
        assert config.app.name == "test_app"
        assert config.openclaw.port == 9222
        assert config.ai.provider == Provider.DEEPSEEK
        assert len(config.accounts) == 1
        assert config.default_account == "account_1"

    def test_config_model_log_level_validation(self):
        """测试日志级别验证"""
        # 有效日志级别
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            config_data = {
                "app": {
                    "name": "test",
                    "version": "1.0.0",
                    "log_level": level
                }
            }
            config = ConfigModel.from_dict(config_data)
            assert config.app.log_level == level

        # 无效日志级别
        config_data = {
            "app": {
                "name": "test",
                "version": "1.0.0",
                "log_level": "INVALID"
            }
        }
        with pytest.raises(ValidationError):
            ConfigModel.from_dict(config_data)

    def test_config_model_default_account_validation(self):
        """测试默认账号验证"""
        # 默认账号存在于列表中
        config_data = {
            "accounts": [
                {"id": "account_1", "name": "账号1", "cookie": "test", "priority": 1, "enabled": True}
            ],
            "default_account": "account_1"
        }
        config = ConfigModel.from_dict(config_data)
        assert config.default_account == "account_1"

        # 当前实现不强制 default_account 必须存在于 accounts 列表中
        config_data = {
            "accounts": [
                {"id": "account_1", "name": "账号1", "cookie": "test", "priority": 1, "enabled": True}
            ],
            "default_account": "nonexistent_account"
        }
        config = ConfigModel.from_dict(config_data)
        assert config.default_account == "nonexistent_account"

    def test_config_model_to_dict(self):
        """测试配置转换为字典"""
        config = ConfigModel()
        config_dict = config.to_dict()
        assert "app" in config_dict
        assert "openclaw" in config_dict
        assert "ai" in config_dict
        assert "accounts" in config_dict


class TestEnvVariableResolution:
    """环境变量解析测试"""

    @pytest.fixture
    def config_file_with_env(self, temp_dir):
        """创建包含环境变量的配置文件"""
        config_file = temp_dir / "config_with_env.yaml"
        config_content = """
app:
  name: "test"
ai:
  api_key: "${TEST_API_KEY}"
  base_url: "${TEST_BASE_URL}"
"""
        config_file.write_text(config_content)
        return config_file

    def test_env_variable_resolution(self, config_file_with_env, monkeypatch):
        """测试环境变量解析"""
        monkeypatch.setenv("TEST_API_KEY", "resolved_key")
        monkeypatch.setenv("TEST_BASE_URL", "https://resolved.url")

        config = Config(str(config_file_with_env))
        assert config.get("ai.api_key") == "resolved_key"
        assert config.get("ai.base_url") == "https://resolved.url"

    def test_env_variable_missing(self, config_file_with_env, monkeypatch):
        """测试缺失环境变量"""
        monkeypatch.delenv("TEST_API_KEY", raising=False)
        monkeypatch.delenv("TEST_BASE_URL", raising=False)

        config = Config(str(config_file_with_env))
        assert config.get("ai.api_key") == "${TEST_API_KEY}"
        assert config.get("ai.base_url") == "${TEST_BASE_URL}"

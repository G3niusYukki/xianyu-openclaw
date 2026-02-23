"""
配置管理模块
Configuration Management Module

提供YAML配置加载、环境变量管理、配置验证等功能
"""

import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional
from functools import lru_cache

import yaml
from dotenv import load_dotenv
from pydantic import ValidationError

from src.core.config_models import ConfigModel
from src.core.logger import get_logger
from src.core.error_handler import ConfigError


class Config:
    """
    配置管理类

    负责加载和管理应用程序的配置，支持YAML配置文件和环境变量
    """

    _instance: Optional["Config"] = None
    _lock = threading.Lock()
    _config: Dict[str, Any] = {}
    _config_path: Optional[str] = None

    def __new__(cls, config_path: Optional[str] = None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_path: Optional[str] = None):
        default_path = self._find_config_file()
        if not hasattr(self, '_initialized') or not self._initialized:
            self.logger = get_logger()
            self._load_config(config_path)
            self._initialized = True
        elif config_path and config_path != self._config_path:
            self.reload(config_path)
        elif config_path is None and self._config_path != default_path:
            self.reload(default_path)

    def _load_config(self, config_path: Optional[str] = None) -> None:
        """
        加载配置文件
        
        Args:
            config_path: 配置文件路径，不指定则使用默认路径
        """
        if config_path is None:
            config_path = self._find_config_file()

        self._config_path = config_path

        if config_path and os.path.exists(config_path):
            self._load_yaml_config(config_path)
            self._load_env_file()
            self._resolve_env_variables()
            self._set_defaults()
        else:
            self._set_defaults()

    def _find_config_file(self) -> Optional[str]:
        """
        查找配置文件
        
        优先级: config/config.yaml > config/config.example.yaml
        """
        possible_paths = [
            "config/config.yaml",
            "config/config.example.yaml",
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None

    def _load_yaml_config(self, config_path: str) -> None:
        """
        加载YAML配置文件
        """
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f) or {}

            if config_data:
                try:
                    validated_config = ConfigModel.from_dict(config_data)
                    self._config = validated_config.to_dict()
                    self.logger.debug(f"Config validation passed: {config_path}")
                except ValidationError as e:
                    self.logger.error(f"Config validation failed: {e}")
                    raise ConfigError(f"Invalid configuration: {e}")

        except FileNotFoundError:
            self.logger.warning(f"Config file not found: {config_path}")
            self._config = {}
        except yaml.YAMLError as e:
            self.logger.error(f"Invalid YAML in config file: {e}")
            raise ConfigError(f"Invalid YAML: {e}")
        except Exception as e:
            self.logger.error(f"Failed to load config file: {e}")
            self._config = {}

    def _load_env_file(self) -> None:
        """
        加载.env环境变量文件
        """
        env_files = [
            ".env",
            "config/.env",
        ]
        for env_file in env_files:
            if os.path.exists(env_file):
                load_dotenv(env_file, override=True)
                break

    def _resolve_env_variables(self) -> None:
        """
        解析环境变量引用

        将配置中的 ${VAR_NAME} 替换为实际的环境变量值
        """
        self._config = self._resolve_dict(self._config)

    def _resolve_dict(self, obj: Any) -> Any:
        """
        递归解析字典中的环境变量引用
        """
        if isinstance(obj, dict):
            resolved = {}
            for key, value in obj.items():
                resolved[key] = self._resolve_dict(value)
            return resolved
        elif isinstance(obj, list):
            return [self._resolve_dict(item) for item in obj]
        elif isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            env_key = obj[2:-1]
            value = os.getenv(env_key)
            if value is None:
                self.logger.warning(f"Environment variable {env_key} not found, using placeholder")
                return obj
            return value
        return obj

    def _set_defaults(self) -> None:
        """
        设置默认配置值
        """
        defaults = {
            "app": {
                "name": "xianyu-openclaw",
                "version": "1.0.0",
                "debug": False,
                "log_level": "INFO",
                "data_dir": "data",
                "logs_dir": "logs",
            },
            "openclaw": {
                "host": "localhost",
                "port": 9222,
                "timeout": 30,
                "retry_times": 3,
            },
            "ai": {
                "provider": "deepseek",
                "temperature": 0.7,
                "max_tokens": 1000,
                "fallback_enabled": True,
            },
            "database": {
                "type": "sqlite",
                "path": "data/agent.db",
                "max_connections": 5,
                "timeout": 30,
            },
            "browser": {
                "headless": True,
                "viewport": {"width": 1280, "height": 800},
                "delay": {"min": 1, "max": 3},
                "upload_timeout": 60,
            },
        }

        for section, values in defaults.items():
            if section not in self._config:
                self._config[section] = values
            elif isinstance(values, dict):
                for key, value in values.items():
                    if key not in self._config[section]:
                        self._config[section][key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            key: 配置键，支持点号分隔的路径，如 "openclaw.host"
            default: 默认值
            
        Returns:
            配置值
        """
        keys = key.split(".")
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value

    def get_section(self, section: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        获取配置段落

        Args:
            section: 段落名称
            default: 默认值

        Returns:
            配置段落字典
        """
        return self._config.get(section, default or {})

    @property
    def app(self) -> Dict[str, Any]:
        """应用配置"""
        return self.get_section("app")

    @property
    def openclaw(self) -> Dict[str, Any]:
        """OpenClaw配置"""
        return self.get_section("openclaw")

    @property
    def ai(self) -> Dict[str, Any]:
        """AI服务配置"""
        return self.get_section("ai")

    @property
    def database(self) -> Dict[str, Any]:
        """数据库配置"""
        return self.get_section("database")

    @property
    def accounts(self) -> list:
        """账号配置"""
        return self.get_section("accounts", [])

    @property
    def media(self) -> Dict[str, Any]:
        """媒体处理配置"""
        return self.get_section("media", {})

    @property
    def content(self) -> Dict[str, Any]:
        """内容生成配置"""
        return self.get_section("content", {})

    @property
    def browser(self) -> Dict[str, Any]:
        """浏览器配置"""
        return self.get_section("browser", {})

    def reload(self, config_path: Optional[str] = None) -> None:
        """
        重新加载配置
        
        Args:
            config_path: 新的配置文件路径
        """
        self._config = {}
        self._load_config(config_path or self._config_path)


@lru_cache(maxsize=1)
def get_config(config_path: Optional[str] = None) -> Config:
    """
    获取配置单例

    Args:
        config_path: 配置文件路径

    Returns:
        Config实例
    """
    return Config(config_path)

"""
配置管理模块
Configuration Management Module

提供YAML配置加载、环境变量管理、配置验证等功能
"""

import os
import threading
from functools import lru_cache
from typing import Any, Optional

import yaml
from dotenv import load_dotenv
from pydantic import ValidationError

from src.core.config_models import ConfigModel
from src.core.error_handler import ConfigError
from src.core.logger import get_logger


class Config:
    """
    配置管理类

    负责加载和管理应用程序的配置，支持YAML配置文件和环境变量
    """

    _instance: Optional["Config"] = None
    _lock = threading.Lock()
    _config: dict[str, Any] = {}
    _config_path: str | None = None

    def __new__(cls, config_path: str | None = None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_path: str | None = None):
        default_path = self._find_config_file()
        if not hasattr(self, "_initialized") or not self._initialized:
            self.logger = get_logger()
            self._load_config(config_path)
            self._initialized = True
        elif config_path and config_path != self._config_path:
            self.reload(config_path)
        elif config_path is None and self._config_path != default_path:
            self.reload(default_path)

    def _load_config(self, config_path: str | None = None) -> None:
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

    def _find_config_file(self) -> str | None:
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
            with open(config_path, encoding="utf-8") as f:
                config_data = yaml.safe_load(f) or {}

            if config_data:
                try:
                    validated_config = ConfigModel.from_dict(config_data)
                    self._config = validated_config.to_dict()
                    self.logger.debug(f"Config validation passed: {config_path}")
                except ValidationError as e:
                    self.logger.error(f"Config validation failed: {e}")
                    raise ConfigError(f"Invalid configuration: {e}") from e

        except FileNotFoundError:
            self.logger.warning(f"Config file not found: {config_path}")
            self._config = {}
        except yaml.YAMLError as e:
            self.logger.error(f"Invalid YAML in config file: {e}")
            raise ConfigError(f"Invalid YAML: {e}") from e
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
                "usage_mode": "minimal",
                "max_calls_per_run": 20,
                "cache_enabled": True,
                "cache_path": "data/ai_response_cache.json",
                "cache_ttl_seconds": 86400,
                "cache_max_entries": 2000,
                "task_ai_enabled": {
                    "title": False,
                    "description": False,
                    "optimize_title": True,
                    "seo_keywords": True,
                },
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
            "messages": {
                "enabled": False,
                "max_replies_per_run": 10,
                "fast_first_reply_enabled": True,
                "first_reply_target_seconds": 3.0,
                "reuse_message_page": True,
                "first_reply_delay_seconds": [0.25, 0.8],
                "inter_reply_delay_seconds": [0.4, 1.2],
                "send_confirm_delay_seconds": [0.15, 0.35],
                "followup_quote_enabled": True,
                "followup_quote_delay_seconds": [0.6, 1.5],
                "read_no_reply_followup_enabled": False,
                "read_no_reply_limit_per_run": 20,
                "read_no_reply_min_elapsed_seconds": 300,
                "read_no_reply_min_interval_seconds": 1800,
                "read_no_reply_max_per_session": 1,
                "read_no_reply_templates": [],
                "read_no_reply_stop_keywords": [],
                "fulfillment_confirm_enabled": True,
                "order_intent_keywords": ["下单", "已下单", "拍下", "已拍", "拍了", "已拍下", "付款", "已付款", "付了"],
                "fulfillment_ack_template": "收到你的订单，我这边开始处理，结果会优先在闲鱼聊天内同步，请耐心等我一下。",
                "followup_state_path": "data/messages_followup_state.json",
                "followup_state_max_sessions": 5000,
                "workflow_state_enabled": True,
                "workflow_state_path": "data/message_workflow_state.json",
                "workflow_state_max_sessions": 5000,
                "worker_enabled": False,
                "worker_interval_seconds": 15.0,
                "worker_jitter_seconds": 1.5,
                "worker_backoff_seconds": 5.0,
                "worker_max_backoff_seconds": 120.0,
                "worker_state_path": "data/workflow_worker_state.json",
                "worker_sla_enabled": True,
                "worker_sla_path": "data/workflow_sla_metrics.json",
                "worker_sla_window_size": 500,
                "worker_alert_min_samples": 10,
                "worker_alert_failure_rate_threshold": 0.2,
                "worker_alert_first_reply_within_target_ratio_threshold": 0.7,
                "worker_alert_cycle_p95_seconds": 20.0,
                "reply_prefix": "",
                "default_reply": "您好，宝贝在的，感兴趣可以直接拍下。",
                "virtual_default_reply": "在的，这是虚拟商品，拍下后会尽快在聊天内给你处理结果。",
                "virtual_product_keywords": [],
                "intent_rules": [],
                "keyword_replies": {},
            },
            "quote": {
                "enabled": True,
                "mode": "rule_only",
                "origin_city": "杭州",
                "pricing_profile": "normal",
                "preferred_couriers": [],
                "cost_table_dir": "data/quote_costs",
                "cost_table_patterns": ["*.xlsx", "*.csv"],
                "markup_rules": {
                    "default": {
                        "normal_first_add": 0.5,
                        "member_first_add": 0.3,
                        "normal_extra_add": 0.5,
                        "member_extra_add": 0.3,
                    }
                },
                "cost_api_url": "",
                "cost_api_key": "",
                "cost_api_timeout_seconds": 3,
                "cost_api_headers": {},
                "api_fallback_to_table_parallel": True,
                "api_prefer_max_wait_seconds": 1.2,
                "currency": "CNY",
                "first_weight_kg": 1.0,
                "first_price": 8.0,
                "extra_per_kg": 2.5,
                "service_fee": 1.0,
                "urgency_fee": 4.0,
                "inter_city_extra": 2.0,
                "remote_extra": 6.0,
                "remote_keywords": ["新疆", "西藏", "青海", "甘肃", "内蒙古", "海南"],
                "eta_same_city_minutes": 90,
                "eta_inter_city_minutes": 360,
                "valid_minutes": 15,
                "remote_api_url": "",
                "remote_api_key": "",
                "timeout_seconds": 3,
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

    def get_section(self, section: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
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
    def app(self) -> dict[str, Any]:
        """应用配置"""
        return self.get_section("app")

    @property
    def openclaw(self) -> dict[str, Any]:
        """OpenClaw配置"""
        return self.get_section("openclaw")

    @property
    def ai(self) -> dict[str, Any]:
        """AI服务配置"""
        return self.get_section("ai")

    @property
    def database(self) -> dict[str, Any]:
        """数据库配置"""
        return self.get_section("database")

    @property
    def accounts(self) -> list:
        """账号配置"""
        return self.get_section("accounts", [])

    @property
    def media(self) -> dict[str, Any]:
        """媒体处理配置"""
        return self.get_section("media", {})

    @property
    def content(self) -> dict[str, Any]:
        """内容生成配置"""
        return self.get_section("content", {})

    @property
    def browser(self) -> dict[str, Any]:
        """浏览器配置"""
        return self.get_section("browser", {})

    @property
    def messages(self) -> dict[str, Any]:
        """消息自动回复配置"""
        return self.get_section("messages", {})

    @property
    def quote(self) -> dict[str, Any]:
        """自动报价配置"""
        return self.get_section("quote", {})

    def reload(self, config_path: str | None = None) -> None:
        """
        重新加载配置

        Args:
            config_path: 新的配置文件路径
        """
        self._config = {}
        self._load_config(config_path or self._config_path)


@lru_cache(maxsize=1)
def get_config(config_path: str | None = None) -> Config:
    """
    获取配置单例

    Args:
        config_path: 配置文件路径

    Returns:
        Config实例
    """
    return Config(config_path)

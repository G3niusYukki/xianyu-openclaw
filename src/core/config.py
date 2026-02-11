"""
配置管理模块
Configuration Management Module

提供YAML配置加载、环境变量管理、配置验证等功能
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional
from functools import lru_cache

import yaml
from dotenv import load_dotenv


class Config:
    """
    配置管理类
    
    负责加载和管理应用程序的配置，支持YAML配置文件和环境变量
    """

    _instance: Optional["Config"] = None
    _config: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._config:
            self._load_config()

    def _load_config(self, config_path: Optional[str] = None) -> None:
        """
        加载配置文件
        
        Args:
            config_path: 配置文件路径，不指定则使用默认路径
        """
        if config_path is None:
            config_path = self._find_config_file()

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
                self._config = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"[Config] Failed to load config file: {e}")
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
            return os.getenv(env_key, obj)
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

    def get_section(self, section: str) -> Dict[str, Any]:
        """
        获取配置段落
        
        Args:
            section: 段落名称
            
        Returns:
            配置段落字典
        """
        return self._config.get(section, {})

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
        self._load_config(config_path)


@lru_cache(maxsize=1)
def get_config() -> Config:
    """
    获取配置单例
    
    Returns:
        Config实例
    """
    return Config()

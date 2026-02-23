"""
核心模块
Core Module

提供配置管理、日志系统、浏览器控制等基础能力
"""

from .browser_client import BrowserClient
from .config import Config
from .logger import Logger

__all__ = ["BrowserClient", "Config", "Logger"]

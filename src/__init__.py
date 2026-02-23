"""
闲鱼自动化工具
Xianyu Automation Tool

基于 OpenClaw 框架的闲鱼自动化运营工具
"""

__version__ = "4.0.0"
__author__ = "Project Team"

from .core.config import Config
from .core.logger import Logger
from .core.browser_client import BrowserClient

__all__ = [
    "Config",
    "Logger",
    "BrowserClient",
    "__version__",
]

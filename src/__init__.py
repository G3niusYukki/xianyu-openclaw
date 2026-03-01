"""
闲鱼自动化工具
Xianyu Automation Tool

基于 OpenClaw 框架的闲鱼自动化运营工具
"""

__version__ = "5.2.0"
__author__ = "Project Team"

from .core.browser_client import BrowserClient
from .core.config import Config
from .core.logger import Logger

__all__ = [
    "BrowserClient",
    "Config",
    "Logger",
    "__version__",
]

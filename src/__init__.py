"""
闲鱼自动化工具
Xianyu Automation Tool

基于OpenClaw框架的闲鱼自动化运营工具
"""

__version__ = "1.0.0"
__author__ = "Project Team"

from .core.config import Config
from .core.logger import Logger
from .core.openclaw_controller import OpenClawController

__all__ = [
    "Config",
    "Logger",
    "OpenClawController",
    "__version__",
]

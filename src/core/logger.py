"""
日志模块
Logging Module

提供统一的日志记录功能，支持多级别日志、文件输出、彩色控制台输出
"""

import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional
from loguru import logger


class Logger:
    """
    日志管理类

    封装loguru，提供配置化的日志输出
    """

    _instance: Optional["Logger"] = None
    _lock = threading.Lock()
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized') or not self._initialized:
            self._setup_logger()
            Logger._initialized = True

    def _setup_logger(self) -> None:
        """
        设置日志输出
        """
        log_level = os.getenv("APP_LOG_LEVEL", "INFO")
        logs_dir = os.getenv("APP_LOGS_DIR", "logs")
        debug = os.getenv("APP_DEBUG", "false").lower() == "true"

        logs_dir = Path(logs_dir)
        logs_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = logs_dir / f"app_{timestamp}.log"

        logger.remove()

        console_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{message}</cyan>"
        )

        file_format = (
            "{time:YYYY-MM-DD HH:mm:ss} | "
            "{level: <8} | "
            "{message}"
        )

        logger.add(
            sys.stdout,
            format=console_format,
            level="DEBUG" if debug else log_level,
            colorize=True,
        )

        logger.add(
            str(log_file),
            format=file_format,
            level="DEBUG",
            rotation="10 MB",
            retention="7 days",
            compression="gz",
        )

    def info(self, message: str, **kwargs) -> None:
        """
        Info级别日志
        """
        logger.info(message, **kwargs)

    def debug(self, message: str, **kwargs) -> None:
        """
        Debug级别日志
        """
        logger.debug(message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        """
        Warning级别日志
        """
        logger.warning(message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        """
        Error级别日志
        """
        logger.error(message, **kwargs)

    def success(self, message: str, **kwargs) -> None:
        """
        Success级别日志（自定义）
        """
        logger.info(f"<green>{message}</green>", **kwargs)


def get_logger(*_args, **_kwargs) -> Logger:
    """
    获取日志单例
    
    Returns:
        Logger实例
    """
    return Logger()

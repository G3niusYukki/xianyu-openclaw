"""
统一异常处理模块
Unified Error Handling

提供异常装饰器和工具函数
"""

import asyncio
import functools
import traceback
from functools import wraps
from typing import Callable, Any, Dict, Optional, List
import httpx

from src.core.logger import get_logger


def handle_controller_errors(default_return: Any = None, 
                             raise_on_error: bool = False):
    """
    控制器操作异常处理装饰器

    Args:
        default_return: 发生异常时返回的默认值
        raise_on_error: 是否在异常时重新抛出
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(self, *args, **kwargs):
            try:
                return await func(self, *args, **kwargs)
            except (ConnectionError, httpx.ConnectError, httpx.NetworkError) as e:
                self.logger.warning(f"Network connection error in {func.__name__}: {e}")
                if raise_on_error:
                    raise
                return default_return
            except httpx.TimeoutException as e:
                self.logger.warning(f"Timeout in {func.__name__}: {e}")
                if raise_on_error:
                    raise
                return default_return
            except httpx.HTTPStatusError as e:
                self.logger.error(f"HTTP error in {func.__name__}: {e.response.status_code}")
                if raise_on_error:
                    raise
                return default_return
            except httpx.HTTPError as e:
                self.logger.error(f"HTTP request error in {func.__name__}: {e}")
                if raise_on_error:
                    raise
                return default_return
            except asyncio.CancelledError:
                self.logger.debug(f"Task cancelled in {func.__name__}")
                raise
            except Exception as e:
                self.logger.error(f"Unexpected error in {func.__name__}: {e}", exc_info=True)
                if raise_on_error:
                    raise
                return default_return

        return async_wrapper
    return decorator


def handle_operation_errors(default_return: Any = False,
                          raise_on_error: bool = False):
    """
    操作异常处理装饰器（用于返回bool的操作）

    Args:
        default_return: 发生异常时返回的默认值
        raise_on_error: 是否在异常时重新抛出
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(self, *args, **kwargs):
            try:
                return await func(self, *args, **kwargs)
            except (ConnectionError, httpx.ConnectError, httpx.NetworkError) as e:
                self.logger.debug(f"Network error in {func.__name__}: {e}")
                if raise_on_error:
                    raise
                return default_return
            except httpx.TimeoutException:
                self.logger.debug(f"Timeout in {func.__name__}")
                if raise_on_error:
                    raise
                return default_return
            except Exception as e:
                self.logger.debug(f"Error in {func.__name__}: {e}")
                if raise_on_error:
                    raise
                return default_return

        @wraps(func)
        def sync_wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                self.logger.debug(f"Error in {func.__name__}: {e}")
                if raise_on_error:
                    raise
                return default_return

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


def safe_execute(logger=None, default_return: Any = None,
                 raise_on_error: bool = False):
    """
    安全执行装饰器（用于可能失败的操作，静默失败）

    Args:
        logger: 日志记录器，不指定则使用全局logger
        default_return: 发生异常时返回的默认值
        raise_on_error: 是否在异常时重新抛出
    """
    if logger is None:
        logger = get_logger()

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.debug(f"Error in {func.__name__}: {e}")
                if raise_on_error:
                    raise
                return default_return

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.debug(f"Error in {func.__name__}: {e}")
                if raise_on_error:
                    raise
                return default_return

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    return decorator


def retry(max_attempts: int = 3, delay: float = 1.0,
         backoff_factor: float = 2.0,
         exceptions: tuple = (Exception,)):
    """
    重试装饰器

    Args:
        max_attempts: 最大尝试次数
        delay: 初始延迟时间（秒）
        backoff_factor: 退避因子
        exceptions: 需要重试的异常类型
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger = kwargs.pop("logger", None) or get_logger()

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts - 1:
                        logger.error(f"Final attempt failed for {func.__name__}: {e}")
                        raise

                    wait_time = delay * (backoff_factor ** attempt)
                    logger.warning(
                        f"Attempt {attempt + 1} failed for {func.__name__}: {e}. "
                        f"Retrying in {wait_time:.1f}s..."
                    )
                    await asyncio.sleep(wait_time)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger = kwargs.pop("logger", None) or get_logger()

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts - 1:
                        logger.error(f"Final attempt failed for {func.__name__}: {e}")
                        raise

                    wait_time = delay * (backoff_factor ** attempt)
                    logger.warning(
                        f"Attempt {attempt + 1} failed for {func.__name__}: {e}. "
                        f"Retrying in {wait_time:.1f}s..."
                    )
                    import time
                    time.sleep(wait_time)

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


def log_execution_time(logger=None):
    """
    记录执行时间装饰器

    Args:
        logger: 日志记录器
    """
    if logger is None:
        logger = get_logger()

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            import time
            start_time = time.time()

            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start_time
                logger.debug(f"{func.__name__} executed in {elapsed:.2f}s")
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(
                    f"{func.__name__} failed after {elapsed:.2f}s: {e}",
                    exc_info=True
                )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            import time
            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                logger.debug(f"{func.__name__} executed in {elapsed:.2f}s")
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(
                    f"{func.__name__} failed after {elapsed:.2f}s: {e}",
                    exc_info=True
                )
                raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    return decorator


class XianyuError(Exception):
    """基础异常类"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "type": self.__class__.__name__,
            "message": self.message,
            "details": self.details
        }


class ConfigError(XianyuError):
    """配置错误"""
    pass


class BrowserError(XianyuError):
    """浏览器操作错误"""
    pass


class AIError(XianyuError):
    """AI服务错误"""
    pass


class MediaError(XianyuError):
    """媒体处理错误"""
    pass


class AccountError(XianyuError):
    """账号错误"""
    pass


class DatabaseError(XianyuError):
    """数据库错误"""
    pass


def handle_errors(exceptions: Optional[tuple] = None,
                    default_return: Any = None,
                    logger=None,
                    raise_on_error: bool = False):
    """
    通用异常处理装饰器

    Args:
        exceptions: 需要捕获的异常类型
        default_return: 默认返回值
        logger: 日志记录器
        raise_on_error: 是否重新抛出异常
    """
    if exceptions is None:
        exceptions = (Exception,)

    if logger is None:
        logger = get_logger()

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except exceptions as e:
                logger.error(
                    f"Error in {func.__name__}: {e}",
                    exc_info=True
                )
                if raise_on_error:
                    raise
                return default_return

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                logger.error(
                    f"Error in {func.__name__}: {e}",
                    exc_info=True
                )
                if raise_on_error:
                    raise
                return default_return

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    return decorator

"""
性能优化工具
Performance Optimization Utilities

提供缓存、异步优化等性能优化功能
"""

import asyncio
import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any

import aiofiles


class AsyncCache:
    """
    异步缓存

    支持TTL过期和自动清理
    """

    def __init__(self, default_ttl: int = 300):
        """
        初始化缓存

        Args:
            default_ttl: 默认过期时间（秒）
        """
        self._cache: dict[str, tuple[Any, datetime]] = {}
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        """
        获取缓存值

        Args:
            key: 缓存键

        Returns:
            缓存值，不存在或已过期返回None
        """
        async with self._lock:
            if key in self._cache:
                value, expiry = self._cache[key]
                if datetime.now() < expiry:
                    return value
                else:
                    # 已过期，删除
                    del self._cache[key]
        return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """
        设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），不指定则使用默认值
        """
        ttl = ttl or self._default_ttl
        expiry = datetime.now() + timedelta(seconds=ttl)

        async with self._lock:
            self._cache[key] = (value, expiry)

    async def delete(self, key: str) -> bool:
        """
        删除缓存值

        Args:
            key: 缓存键

        Returns:
            是否成功删除
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
        return False

    async def clear(self) -> int:
        """
        清除所有缓存

        Returns:
            清除的缓存数量
        """
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
        return count

    async def cleanup_expired(self) -> int:
        """
        清理过期的缓存

        Returns:
            清理的数量
        """
        async with self._lock:
            now = datetime.now()
            expired_keys = [key for key, (_, expiry) in self._cache.items() if expiry < now]
            for key in expired_keys:
                del self._cache[key]
        return len(expired_keys)

    async def get_stats(self) -> dict[str, Any]:
        """
        获取缓存统计

        Returns:
            统计信息
        """
        async with self._lock:
            now = datetime.now()
            expired = sum(1 for _, expiry in self._cache.values() if expiry < now)
            valid = len(self._cache) - expired

            return {
                "total_keys": len(self._cache),
                "valid_keys": valid,
                "expired_keys": expired,
                "default_ttl": self._default_ttl,
            }


class FileCache:
    """
    文件缓存

    将数据缓存到文件中，支持持久化
    """

    def __init__(self, cache_dir: str = ".cache"):
        """
        初始化文件缓存

        Args:
            cache_dir: 缓存目录
        """
        from pathlib import Path

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, key: str) -> Path:
        """获取缓存文件路径"""
        # 使用MD5哈希作为文件名，避免特殊字符问题
        hash_key = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{hash_key}.cache"

    async def get(self, key: str) -> Any | None:
        """
        从文件获取缓存

        Args:
            key: 缓存键

        Returns:
            缓存值，不存在返回None
        """
        cache_path = self._get_cache_path(key)

        if not cache_path.exists():
            return None

        try:
            async with aiofiles.open(cache_path) as f:
                data = await f.read()
                return json.loads(data)
        except Exception:
            return None

    async def set(self, key: str, value: Any) -> None:
        """
        设置文件缓存

        Args:
            key: 缓存键
            value: 缓存值
        """
        cache_path = self._get_cache_path(key)

        try:
            async with aiofiles.open(cache_path, "w") as f:
                await f.write(json.dumps(value))
        except Exception:
            pass

    async def delete(self, key: str) -> bool:
        """
        删除文件缓存

        Args:
            key: 缓存键

        Returns:
            是否成功删除
        """
        cache_path = self._get_cache_path(key)

        if cache_path.exists():
            try:
                cache_path.unlink()
                return True
            except Exception:
                pass
        return False

    async def clear(self) -> int:
        """
        清除所有缓存文件

        Returns:
            清除的数量
        """
        count = 0
        try:
            for cache_file in self.cache_dir.glob("*.cache"):
                cache_file.unlink()
                count += 1
        except Exception:
            pass
        return count


def cached(cache: AsyncCache, ttl: int | None = None, key_prefix: str = ""):
    """
    异步缓存装饰器

    Args:
        cache: 缓存实例
        ttl: 过期时间
        key_prefix: 缓存键前缀

    Returns:
        装饰器函数
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{key_prefix}{func.__name__}:{args!s}:{kwargs!s}"

            # 尝试从缓存获取
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            # 执行函数
            result = await func(*args, **kwargs)

            # 缓存结果
            await cache.set(cache_key, result, ttl)

            return result

        return wrapper

    return decorator


def batch_process(batch_size: int = 10, delay: float = 0.1):
    """
    批量处理装饰器

    Args:
        batch_size: 批次大小
        delay: 批次间延迟

    Returns:
        装饰器函数
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 检查第一个参数是否是列表
            if not args:
                return await func(*args, **kwargs)

            items = args[0]
            if not isinstance(items, (list, tuple)):
                return await func(*args, **kwargs)

            # 分批处理
            results = []
            for i in range(0, len(items), batch_size):
                batch = items[i : i + batch_size]
                batch_result = await func(batch, *args[1:], **kwargs)
                results.extend(batch_result)

                # 延迟（非最后一批）
                if i + batch_size < len(items):
                    await asyncio.sleep(delay)

            return results

        return wrapper

    return decorator


class PerformanceMonitor:
    """
    性能监控器

    监控函数执行时间和性能指标
    """

    def __init__(self):
        self._metrics: dict[str, list] = {}
        self._lock = asyncio.Lock()

    async def record(self, name: str, duration: float, success: bool = True) -> None:
        """
        记录性能指标

        Args:
            name: 指标名称
            duration: 执行时间（秒）
            success: 是否成功
        """
        async with self._lock:
            if name not in self._metrics:
                self._metrics[name] = []

            self._metrics[name].append(
                {"duration": duration, "success": success, "timestamp": datetime.now().isoformat()}
            )

    async def get_stats(self, name: str) -> dict[str, Any]:
        """
        获取性能统计

        Args:
            name: 指标名称

        Returns:
            统计信息
        """
        async with self._lock:
            records = self._metrics.get(name, [])

            if not records:
                return {}

            durations = [r["duration"] for r in records]
            success_rate = sum(1 for r in records if r["success"]) / len(records)

            return {
                "count": len(records),
                "avg_duration": sum(durations) / len(durations),
                "min_duration": min(durations),
                "max_duration": max(durations),
                "success_rate": success_rate,
            }

    async def clear(self) -> None:
        """清除所有指标"""
        async with self._lock:
            self._metrics.clear()


def monitor_performance(monitor: PerformanceMonitor):
    """
    性能监控装饰器

    Args:
        monitor: 性能监控器实例

    Returns:
        装饰器函数
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            import time

            start_time = time.time()
            success = True

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                raise e
            finally:
                duration = time.time() - start_time
                await monitor.record(func.__name__, duration, success)

        return wrapper

    return decorator

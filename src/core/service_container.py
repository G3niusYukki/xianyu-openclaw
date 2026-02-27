"""
服务容器
Service Container

提供依赖注入和服务管理
"""

import threading
from collections.abc import Callable
from functools import wraps
from typing import Any, Optional, TypeVar

T = TypeVar("T")


class ServiceContainer:
    """
    服务容器

    管理服务的注册、创建和生命周期
    """

    _instance: Optional["ServiceContainer"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._services: dict[str, Any] = {}
            self._factories: dict[str, Callable[[], Any]] = {}
            self._singletons: set[str] = set()
            self._initialized = True

    def register(
        self,
        service_type: type[T],
        instance: T | None = None,
        factory: Callable[[], T] | None = None,
        singleton: bool = True,
    ) -> None:
        """
        注册服务

        Args:
            service_type: 服务类型（接口或具体类）
            instance: 服务实例
            factory: 工厂函数
            singleton: 是否单例
        """
        service_key = self._get_service_key(service_type)

        if instance is not None:
            self._services[service_key] = instance
        elif factory is not None:
            self._factories[service_key] = factory
        else:
            raise ValueError(f"Must provide either instance or factory for {service_type.__name__}")

        if singleton:
            self._singletons.add(service_key)

    def get(self, service_type: type[T]) -> T | None:
        """
        获取服务实例

        Args:
            service_type: 服务类型

        Returns:
            服务实例
        """
        service_key = self._get_service_key(service_type)

        if service_key in self._services:
            return self._services[service_key]

        if service_key in self._factories:
            factory = self._factories[service_key]
            instance = factory()

            if service_key in self._singletons:
                self._services[service_key] = instance

            return instance

        return None

    def set(self, service_type: type[T], instance: T) -> None:
        """
        设置服务实例

        Args:
            service_type: 服务类型
            instance: 服务实例
        """
        service_key = self._get_service_key(service_type)
        self._services[service_key] = instance

    def has(self, service_type: type[T]) -> bool:
        """
        检查服务是否存在

        Args:
            service_type: 服务类型

        Returns:
            是否存在
        """
        service_key = self._get_service_key(service_type)
        return service_key in self._services or service_key in self._factories

    def clear(self) -> None:
        """清除所有服务"""
        self._services.clear()
        self._factories.clear()
        self._singletons.clear()

    def _get_service_key(self, service_type: type) -> str:
        """获取服务键"""
        return service_type.__name__

    def inject(self, *service_types: type[T]):
        """
        依赖注入装饰器

        Args:
            *service_types: 需要注入的服务类型

        Returns:
            装饰器函数
        """

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                injected = []
                for st in service_types:
                    service = self.get(st)
                    if service is None:
                        raise ValueError(f"Service {st.__name__} not registered")
                    injected.append(service)

                return func(*args, *injected, **kwargs)

            return wrapper

        return decorator


class LazyService:
    """
    懒加载服务

    延迟服务实例化，直到首次使用
    """

    def __init__(self, service_type: type[T], container: ServiceContainer):
        self._service_type = service_type
        self._container = container
        self._instance: T | None = None

    def __call__(self) -> T:
        if self._instance is None:
            self._instance = self._container.get(self._service_type)
        return self._instance


def get_container() -> ServiceContainer:
    """
    获取服务容器单例

    Returns:
        ServiceContainer实例
    """
    return ServiceContainer()


def inject_service(service_type: type[T]):
    """
    依赖注入装饰器（简化版）

    Args:
        service_type: 需要注入的服务类型

    Returns:
        装饰器函数
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            container = get_container()
            service = container.get(service_type)
            if service is None:
                raise ValueError(f"Service {service_type.__name__} not registered")
            return func(service, *args, **kwargs)

        return wrapper

    return decorator

"""ServiceContainer 单元测试。"""

from src.core.service_container import ServiceContainer


class DummyService:
    pass


def test_register_and_get_singleton_factory() -> None:
    container = ServiceContainer()
    container.clear()

    container.register(DummyService, factory=DummyService, singleton=True)
    a = container.get(DummyService)
    b = container.get(DummyService)

    assert a is not None
    assert a is b


def test_clear_resets_singleton_registry() -> None:
    container = ServiceContainer()
    container.clear()

    container.register(DummyService, factory=DummyService, singleton=True)
    assert container.get(DummyService) is not None

    container.clear()
    assert container.get(DummyService) is None

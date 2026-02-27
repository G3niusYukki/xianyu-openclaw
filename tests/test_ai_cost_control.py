"""AI降本治理测试。"""

from types import SimpleNamespace

from src.modules.content.service import ContentService


class _DummyClient:
    def __init__(self, content: str = "AI生成标题"):
        self._content = content
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        _ = kwargs
        msg = SimpleNamespace(content=self._content)
        choice = SimpleNamespace(message=msg)
        return SimpleNamespace(choices=[choice])


def test_ai_usage_mode_minimal_disables_default_title_ai() -> None:
    service = ContentService(
        {
            "usage_mode": "minimal",
            "task_switches": {"title": False},
            "max_calls_per_run": 5,
            "cache_ttl_seconds": 60,
            "cache_max_entries": 10,
        }
    )
    service.client = _DummyClient()

    title = service.generate_title("iPhone", ["95新"], "数码手机")
    stats = service.get_ai_cost_stats()

    assert "iPhone" in title
    assert stats["ai_calls"] == 0


def test_ai_usage_mode_with_budget_and_cache_hits() -> None:
    service = ContentService(
        {
            "usage_mode": "minimal",
            "task_switches": {"title": True},
            "max_calls_per_run": 1,
            "cache_ttl_seconds": 60,
            "cache_max_entries": 10,
        }
    )
    service.client = _DummyClient(content="精选iPhone 95新")

    t1 = service.generate_title("iPhone", ["95新"], "数码手机")
    t2 = service.generate_title("iPhone", ["95新"], "数码手机")
    stats = service.get_ai_cost_stats()

    assert t1 == "精选iPhone 95新"
    assert t2 == t1
    assert stats["ai_calls"] == 1
    assert stats["cache_hits"] >= 1

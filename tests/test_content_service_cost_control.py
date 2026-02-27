"""内容服务的低 token 调用策略测试。"""

from pathlib import Path

from src.modules.content.service import ContentService


def test_content_service_minimal_mode_skips_ai_for_simple_title_and_description(tmp_path: Path) -> None:
    service = ContentService(
        config={
            "api_key": "test-key",
            "usage_mode": "minimal",
            "task_ai_enabled": {"title": False, "description": False},
            "cache_enabled": False,
            "cache_path": str(tmp_path / "ai_cache.json"),
        }
    )
    service.client = object()  # type: ignore[assignment]

    calls = {"count": 0}

    def fake_call_ai(*_args, **_kwargs):
        calls["count"] += 1
        return "AI结果"

    service._call_ai = fake_call_ai  # type: ignore[method-assign]

    title = service.generate_title("iPhone 13", ["128G"], "数码手机")
    description = service.generate_description("iPhone 13", "95新", "换新机", ["国行"], None)

    assert "iPhone 13" in title
    assert "闲置" in description
    assert calls["count"] == 0


def test_content_service_cache_reuses_ai_result(tmp_path: Path) -> None:
    cache_path = tmp_path / "ai_cache.json"
    service = ContentService(
        config={
            "api_key": "test-key",
            "usage_mode": "always",
            "cache_enabled": True,
            "cache_path": str(cache_path),
            "cache_ttl_seconds": 86400,
            "cache_max_entries": 200,
            "task_ai_enabled": {"optimize_title": True},
        }
    )
    service.client = object()  # type: ignore[assignment]

    calls = {"count": 0}

    def fake_call_ai_once(*_args, **_kwargs):
        calls["count"] += 1
        return "【优化】iPhone 13 128G 国行"

    service._call_ai_once = fake_call_ai_once  # type: ignore[method-assign]

    first = service.optimize_title("iPhone 13 128G", "数码手机")
    second = service.optimize_title("iPhone 13 128G", "数码手机")

    assert first == second
    assert calls["count"] == 1
    assert cache_path.exists()

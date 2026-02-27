"""合规护栏测试。"""

import asyncio

import yaml

from src.core.compliance import ComplianceGuard


def _write_rules(path, mode: str, min_interval: int = 30) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "mode": mode,
                "reload": {"auto_reload": True, "check_interval_seconds": 0},
                "publish": {"min_interval_seconds": min_interval},
                "batch_operations": {"polish_cooldown_seconds": 1},
                "content": {"case_sensitive": False, "banned_keywords": ["微信"]},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


def test_content_block_mode(temp_dir) -> None:
    rules_path = temp_dir / "rules.yaml"
    _write_rules(rules_path, mode="block")
    guard = ComplianceGuard(str(rules_path))

    result = guard.evaluate_content("支持微信联系", "其他正常")
    assert result["blocked"] is True
    assert result["allowed"] is False


def test_content_warn_mode(temp_dir) -> None:
    rules_path = temp_dir / "rules.yaml"
    _write_rules(rules_path, mode="warn")
    guard = ComplianceGuard(str(rules_path))

    result = guard.evaluate_content("支持微信联系", "其他正常")
    assert result["warn"] is True
    assert result["allowed"] is True
    assert result["blocked"] is False


def test_rules_auto_reload(temp_dir) -> None:
    rules_path = temp_dir / "rules.yaml"
    _write_rules(rules_path, mode="block")
    guard = ComplianceGuard(str(rules_path))

    blocked_result = guard.evaluate_content("微信", "")
    assert blocked_result["blocked"] is True

    _write_rules(rules_path, mode="warn")
    reloaded_result = guard.evaluate_content("微信", "")
    assert reloaded_result["warn"] is True


def test_publish_rate_warn_mode(temp_dir) -> None:
    rules_path = temp_dir / "rules.yaml"
    _write_rules(rules_path, mode="warn", min_interval=9999)
    guard = ComplianceGuard(str(rules_path))

    first = asyncio.run(guard.evaluate_publish_rate("publish:test"))
    second = asyncio.run(guard.evaluate_publish_rate("publish:test"))

    assert first["allowed"] is True
    assert second["allowed"] is True
    assert second["warn"] is True

"""setup_wizard 测试。"""

from src.setup_wizard import _build_env_content


def test_build_env_content_contains_selected_provider() -> None:
    content = _build_env_content(
        {
            "OPENAI_API_KEY": "sk-test",
            "AI_API_KEY": "sk-biz",
            "AI_PROVIDER": "deepseek",
            "AI_BASE_URL": "https://api.deepseek.com/v1",
            "AI_MODEL": "deepseek-chat",
            "OPENCLAW_GATEWAY_TOKEN": "token",
            "AUTH_PASSWORD": "pass",
            "AUTH_USERNAME": "admin",
            "XIANYU_COOKIE_1": "cookie_1",
        },
        gateway_key="OPENAI_API_KEY",
        content_key="AI_API_KEY",
    )

    assert "OPENAI_API_KEY=sk-test" in content
    assert "AI_PROVIDER=deepseek" in content
    assert "AI_API_KEY=sk-biz" in content
    assert "# 当前启用 Gateway Key: OPENAI_API_KEY" in content
    assert "# 当前启用 Business AI Key: AI_API_KEY" in content
    assert "XIANYU_COOKIE_1=cookie_1" in content

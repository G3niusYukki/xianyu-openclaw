"""setup_wizard 测试。"""

from src.setup_wizard import _build_env_content


def test_build_env_content_contains_selected_provider() -> None:
    content = _build_env_content(
        {
            "OPENAI_API_KEY": "sk-test",
            "OPENCLAW_GATEWAY_TOKEN": "token",
            "AUTH_PASSWORD": "pass",
            "AUTH_USERNAME": "admin",
            "XIANYU_COOKIE_1": "cookie_1",
        },
        provider_key="OPENAI_API_KEY",
    )

    assert "OPENAI_API_KEY=sk-test" in content
    assert "# 当前启用 AI Key: OPENAI_API_KEY" in content
    assert "XIANYU_COOKIE_1=cookie_1" in content

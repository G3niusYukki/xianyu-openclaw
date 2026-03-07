from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.modules.content.service import ContentService


@pytest.fixture
def svc():
    config = {
        "provider": "deepseek",
        "api_key": "test_key",
        "base_url": "https://test.api/v1",
        "model": "test-model",
        "temperature": 0.7,
        "max_tokens": 1000,
        "timeout": 30,
        "fallback_enabled": True,
        "usage_mode": "always",
        "max_calls_per_run": 100,
        "cache_ttl_seconds": 900,
        "cache_max_entries": 200,
        "task_switches": {},
    }
    with patch("src.modules.content.service.get_config") as mock_cfg, \
         patch("src.modules.content.service.get_compliance_guard") as mock_comp, \
         patch("src.modules.content.service.OpenAI") as mock_openai, \
         patch("src.modules.content.service.AsyncOpenAI"):
        mock_cfg.return_value.ai = config
        mock_comp.return_value = MagicMock()
        mock_comp.return_value.mode = "strict"
        mock_comp.return_value.evaluate_content.return_value = {
            "allowed": True,
            "blocked": False,
            "warn": False,
            "hits": [],
            "message": "ok",
        }
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        service = ContentService(config)
        service.client = mock_client
        yield service


class TestGenerateListingFromCategory:
    def test_ai_returns_valid_json(self, svc):
        valid_response = json.dumps({
            "title": "测试标题很长足够",
            "description": "这是一段测试描述文案",
            "features": ["卖点1", "卖点2"],
        })
        svc._call_ai = MagicMock(return_value=valid_response)
        result = svc.generate_listing_from_category("express", {"price": 10})
        assert result["title"] == "测试标题很长足够"
        assert result["description"] == "这是一段测试描述文案"
        assert len(result["features"]) == 2
        assert "compliance" in result

    def test_ai_returns_non_dict(self, svc):
        svc._call_ai = MagicMock(return_value='"just a string"')
        svc.generate_listing_content = MagicMock(return_value={
            "title": "fallback title",
            "description": "fallback desc",
            "compliance": {},
        })
        result = svc.generate_listing_from_category("recharge")
        assert result["title"] == "fallback title"

    def test_ai_returns_invalid_json(self, svc):
        svc._call_ai = MagicMock(return_value="not json at all {{{")
        svc.generate_listing_content = MagicMock(return_value={
            "title": "fallback",
            "description": "",
            "compliance": {},
        })
        result = svc.generate_listing_from_category("exchange")
        assert result["title"] == "fallback"

    def test_ai_returns_none(self, svc):
        svc._call_ai = MagicMock(return_value=None)
        svc.generate_listing_content = MagicMock(return_value={
            "title": "fb",
            "description": "fb desc",
            "compliance": {},
        })
        result = svc.generate_listing_from_category("game")
        assert result["title"] == "fb"

    def test_features_not_list(self, svc):
        valid_response = json.dumps({
            "title": "标题",
            "description": "描述",
            "features": "not a list",
        })
        svc._call_ai = MagicMock(return_value=valid_response)
        result = svc.generate_listing_from_category("account")
        assert result["features"] == []

    def test_custom_name_and_extra_info(self, svc):
        valid_response = json.dumps({
            "title": "custom title",
            "description": "desc",
            "features": [],
        })
        svc._call_ai = MagicMock(return_value=valid_response)
        result = svc.generate_listing_from_category(
            "movie_ticket",
            {"name": "Custom Name", "extra_info": "extra details"},
        )
        assert result["title"] == "custom title"

    def test_unknown_category_uses_category_as_name(self, svc):
        svc._call_ai = MagicMock(return_value=None)
        svc.generate_listing_content = MagicMock(return_value={
            "title": "unknown_cat",
            "description": "",
            "compliance": {},
        })
        result = svc.generate_listing_from_category("unknown_category")
        assert "title" in result


class TestSuggestTemplate:
    def test_valid_category(self, svc):
        assert svc.suggest_template("express") == "express"
        assert svc.suggest_template("game") == "game"

    def test_invalid_category(self, svc):
        assert svc.suggest_template("unknown") == "exchange"
        assert svc.suggest_template("") == "exchange"

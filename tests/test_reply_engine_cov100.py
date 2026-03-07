from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.modules.messages.reply_engine import (
    DEFAULT_INTENT_RULES,
    INTENT_LABELS,
    IntentRule,
    ReplyStrategyEngine,
)


def _make_engine(**kwargs):
    defaults = {
        "default_reply": "默认回复",
        "virtual_default_reply": "虚拟商品默认回复",
    }
    defaults.update(kwargs)
    return ReplyStrategyEngine(**defaults)


class TestIntentRule:
    def test_keyword_match(self):
        rule = IntentRule(name="test", reply="r", keywords=["hello"])
        assert rule.matches("hello world") is True
        assert rule.matches("bye") is False

    def test_pattern_match(self):
        rule = IntentRule(name="test", reply="r", patterns=[r"\d+ 分钟"])
        assert rule.matches("5 分钟内") is True
        assert rule.matches("no match") is False

    def test_no_match(self):
        rule = IntentRule(name="test", reply="r")
        assert rule.matches("anything") is False

    def test_empty_keyword_skipped(self):
        rule = IntentRule(name="test", reply="r", keywords=["", "hello"])
        assert rule.matches("hello") is True
        assert rule.matches("xyz") is False

    def test_empty_pattern_skipped(self):
        rule = IntentRule(name="test", reply="r", patterns=["", r"\d+"])
        assert rule.matches("123") is True


class TestReplyStrategyEngineInit:
    def test_default_rules_loaded(self):
        engine = _make_engine()
        assert len(engine.rules) > 0

    def test_custom_intent_rules(self):
        custom = [{"name": "greet", "reply": "Hi!", "keywords": ["hi"], "priority": 50}]
        engine = _make_engine(intent_rules=custom)
        assert any(r.name == "greet" for r in engine.rules)

    def test_legacy_keyword_rules(self):
        engine = _make_engine(keyword_replies={"价格": "100元"})
        assert any(r.name == "legacy_价格" for r in engine.rules)

    def test_empty_keyword_skipped(self):
        engine = _make_engine(keyword_replies={"": "ignored", "ok": ""})
        assert not any(r.name.startswith("legacy_") for r in engine.rules)

    def test_virtual_product_keywords_custom(self):
        engine = _make_engine(virtual_product_keywords=["自定义"])
        assert "自定义" in engine.virtual_product_keywords

    def test_reply_prefix(self):
        engine = _make_engine(reply_prefix="[AUTO] ")
        assert engine.reply_prefix == "[AUTO] "


class TestGetContentService:
    def test_lazy_init(self):
        engine = _make_engine()
        with patch("src.modules.content.service.ContentService", side_effect=Exception("no module")):
            result = engine._get_content_service()
            assert result is None

    def test_caches(self):
        engine = _make_engine()
        mock_svc = MagicMock()
        with patch("src.modules.content.service.ContentService", return_value=mock_svc):
            result1 = engine._get_content_service()
            result2 = engine._get_content_service()
            assert result1 is result2


class TestGetComplianceGuard:
    def test_lazy_init(self):
        engine = _make_engine()
        with patch("src.core.compliance.get_compliance_guard", side_effect=Exception("no module")):
            result = engine._get_compliance_guard()
            assert result is None

    def test_caches(self):
        engine = _make_engine()
        mock_guard = MagicMock()
        with patch("src.core.compliance.get_compliance_guard", return_value=mock_guard):
            r1 = engine._get_compliance_guard()
            r2 = engine._get_compliance_guard()
            assert r1 is r2


class TestClassifyIntent:
    def test_keyword_rule_match(self):
        engine = _make_engine()
        intent = engine.classify_intent("在吗？")
        assert intent == "availability"

    def test_virtual_context_fallback(self):
        engine = _make_engine()
        intent = engine.classify_intent("some message", item_title="卡密商品")
        assert intent == "availability"

    def test_unknown_without_ai(self):
        engine = _make_engine(ai_intent_enabled=False)
        intent = engine.classify_intent("随机无关消息")
        assert intent == "unknown"

    def test_ai_enabled_fallback(self):
        engine = _make_engine(ai_intent_enabled=True)
        with patch.object(engine, "_ai_classify_intent", return_value="chat"):
            intent = engine.classify_intent("随机无关消息", item_title="普通商品")
            assert intent == "chat"


class TestAiClassifyIntent:
    def test_no_service(self):
        engine = _make_engine()
        engine._content_service = None
        with patch.object(engine, "_get_content_service", return_value=None):
            result = engine._ai_classify_intent("msg")
            assert result == "unknown"

    def test_no_client(self):
        engine = _make_engine()
        mock_svc = MagicMock()
        mock_svc.client = None
        engine._content_service = mock_svc
        result = engine._ai_classify_intent("msg")
        assert result == "unknown"

    def test_valid_response(self):
        engine = _make_engine()
        mock_svc = MagicMock()
        mock_svc.client = True
        mock_svc._call_ai.return_value = " order "
        engine._content_service = mock_svc
        result = engine._ai_classify_intent("下单", "商品A")
        assert result == "order"

    def test_invalid_label(self):
        engine = _make_engine()
        mock_svc = MagicMock()
        mock_svc.client = True
        mock_svc._call_ai.return_value = "invalid_label"
        engine._content_service = mock_svc
        result = engine._ai_classify_intent("msg")
        assert result == "unknown"

    def test_empty_result(self):
        engine = _make_engine()
        mock_svc = MagicMock()
        mock_svc.client = True
        mock_svc._call_ai.return_value = ""
        engine._content_service = mock_svc
        result = engine._ai_classify_intent("msg")
        assert result == "unknown"

    def test_exception(self):
        engine = _make_engine()
        mock_svc = MagicMock()
        mock_svc.client = True
        mock_svc._call_ai.side_effect = Exception("API error")
        engine._content_service = mock_svc
        result = engine._ai_classify_intent("msg")
        assert result == "unknown"


class TestGenerateReply:
    def test_keyword_match(self):
        engine = _make_engine()
        reply = engine.generate_reply("在吗？")
        assert "在的" in reply

    def test_default_reply(self):
        engine = _make_engine(compliance_enabled=False)
        reply = engine.generate_reply("完全不匹配的消息")
        assert "默认回复" in reply

    def test_virtual_context_reply(self):
        engine = _make_engine(compliance_enabled=False)
        reply = engine.generate_reply("想咨询一下", item_title="卡密商品")
        assert "虚拟商品默认回复" in reply

    def test_with_item_title(self):
        engine = _make_engine(compliance_enabled=False)
        reply = engine.generate_reply("在吗？", item_title="测试商品")
        assert "测试商品" in reply

    def test_with_prefix(self):
        engine = _make_engine(reply_prefix="[BOT] ", compliance_enabled=False)
        reply = engine.generate_reply("在吗？")
        assert reply.startswith("[BOT] ")

    def test_compliance_blocks(self):
        engine = _make_engine(compliance_enabled=True)
        mock_guard = MagicMock()
        mock_guard.evaluate_content.return_value = {"blocked": True, "hits": ["bad"]}
        engine._compliance_guard = mock_guard
        reply = engine.generate_reply("在吗？")
        assert reply == "默认回复"

    def test_compliance_passes(self):
        engine = _make_engine(compliance_enabled=True)
        mock_guard = MagicMock()
        mock_guard.evaluate_content.return_value = {"blocked": False}
        engine._compliance_guard = mock_guard
        reply = engine.generate_reply("在吗？")
        assert "在的" in reply

    def test_compliance_exception(self):
        engine = _make_engine(compliance_enabled=True)
        mock_guard = MagicMock()
        mock_guard.evaluate_content.side_effect = Exception("guard error")
        engine._compliance_guard = mock_guard
        reply = engine.generate_reply("在吗？")
        assert "在的" in reply

    def test_no_guard_returns_text(self):
        engine = _make_engine(compliance_enabled=True)
        engine._compliance_guard = None
        with patch.object(engine, "_get_compliance_guard", return_value=None):
            reply = engine._check_compliance("test text")
            assert reply == "test text"

    def test_ai_intent_in_generate_reply(self):
        engine = _make_engine(ai_intent_enabled=True, compliance_enabled=False)
        with patch.object(engine, "_ai_classify_intent", return_value="chat"):
            reply = engine.generate_reply("随便聊聊")
            assert "默认回复" in reply


class TestGenerateReplyWithIntent:
    def test_basic(self):
        engine = _make_engine(compliance_enabled=False)
        result = engine.generate_reply_with_intent("在吗？")
        assert "reply" in result
        assert "intent" in result
        assert "intent_label" in result
        assert "should_quote" in result

    def test_should_quote_price_inquiry(self):
        engine = _make_engine(compliance_enabled=False)
        engine.rules.insert(0, IntentRule(name="price_inquiry", reply="报价", keywords=["多少钱"]))
        result = engine.generate_reply_with_intent("多少钱")
        assert result["should_quote"] is True


class TestParseRule:
    def test_missing_reply_defaults(self):
        engine = _make_engine()
        rule = engine._parse_rule({"name": "test"})
        assert rule.reply == "默认回复"

    def test_full_rule(self):
        engine = _make_engine()
        rule = engine._parse_rule({
            "name": "r1",
            "reply": "Hi",
            "keywords": ["hello"],
            "patterns": [r"\d+"],
            "priority": 50,
        })
        assert rule.name == "r1"
        assert rule.priority == 50


class TestIsVirtualContext:
    def test_in_message(self):
        engine = _make_engine()
        assert engine._is_virtual_context("我要买卡密", "") is True

    def test_in_title(self):
        engine = _make_engine()
        assert engine._is_virtual_context("", "cdk商品") is True

    def test_not_virtual(self):
        engine = _make_engine()
        assert engine._is_virtual_context("hello", "普通商品") is False


class TestNormalizeText:
    def test_basic(self):
        assert ReplyStrategyEngine._normalize_text("  Hello ") == "hello"

    def test_empty(self):
        assert ReplyStrategyEngine._normalize_text("") == ""
        assert ReplyStrategyEngine._normalize_text(None) == ""

"""核心模块行为测试。"""

import os
from unittest.mock import AsyncMock
from unittest.mock import Mock

import pytest

from src.core.error_handler import BrowserError
from src.modules.listing.service import ListingService, XianyuSelectors
from src.modules.media.service import MediaService
from src.modules.messages.service import MessagesService
from src.modules.compliance.center import ComplianceDecision
from src.modules.operations.service import OperationsService


def test_listing_selectors_publish_page() -> None:
    selectors = XianyuSelectors()
    assert selectors.PUBLISH_PAGE == "https://www.goofish.com/sell"


@pytest.mark.asyncio
async def test_select_category_clicks_mapped_option(mock_controller) -> None:
    service = ListingService(controller=mock_controller)

    await service._step_select_category("page_test_id", "数码手机")

    mock_controller.click.assert_any_call("page_test_id", service.selectors.CATEGORY_SELECT)
    assert mock_controller.execute_script.await_count >= 1
    script = mock_controller.execute_script.await_args_list[-1].args[1]
    assert "手机" in script


@pytest.mark.asyncio
async def test_select_condition_clicks_target_option(mock_controller) -> None:
    service = ListingService(controller=mock_controller)

    await service._step_select_condition("page_test_id", ["99新", "国行"])

    mock_controller.click.assert_any_call("page_test_id", service.selectors.CONDITION_SELECT)
    assert mock_controller.execute_script.await_count >= 1


@pytest.mark.asyncio
async def test_batch_polish_requires_controller() -> None:
    service = OperationsService(controller=None)
    with pytest.raises(BrowserError):
        await service.batch_polish(max_items=5)


@pytest.mark.asyncio
async def test_batch_polish_uses_real_ids_and_counts_failures(mock_controller) -> None:
    service = OperationsService(controller=mock_controller)
    service.compliance._last_action_at.clear()

    mock_controller.find_elements = AsyncMock(return_value=[{"idx": 1}, {"idx": 2}, {"idx": 3}])
    mock_controller.execute_script = AsyncMock(return_value=["item_a", "item_b", "item_c"])

    state = {"polish_clicks": 0}

    async def click_side_effect(_page_id, selector):
        if selector == service.selectors.POLISH_BUTTON:
            state["polish_clicks"] += 1
            return state["polish_clicks"] != 2
        if selector == service.selectors.POLISH_CONFIRM:
            return True
        return True

    mock_controller.click = AsyncMock(side_effect=click_side_effect)

    result = await service.batch_polish(max_items=3)

    assert result["total"] == 3
    assert result["success"] == 2
    assert result["failed"] == 1
    assert [item["product_id"] for item in result["details"]] == ["item_a", "item_b", "item_c"]


def test_media_save_format_mapping_case_insensitive() -> None:
    service = MediaService()
    assert service._get_save_format("PNG") == "PNG"
    assert service._get_save_format("webp") == "WEBP"


def test_messages_generate_reply_uses_keyword_template() -> None:
    service = MessagesService(controller=None, config={"reply_prefix": "【自动回复】"})
    reply = service.generate_reply("还在吗？")
    assert "在的" in reply
    assert reply.startswith("【自动回复】")


def test_messages_generate_reply_for_virtual_card_code() -> None:
    service = MessagesService(controller=None, config={})
    reply = service.generate_reply("这个多久发卡密？", item_title="流媒体会员卡密")
    assert "虚拟商品" in reply
    assert "关于「流媒体会员卡密」" in reply


def test_messages_generate_reply_for_online_fulfillment() -> None:
    service = MessagesService(controller=None, config={})
    reply = service.generate_reply("支持代下单吗")
    assert "支持代下单服务" in reply


def test_messages_generate_reply_forces_non_empty_fallback_when_default_blank() -> None:
    service = MessagesService(
        controller=None,
        config={
            "default_reply": "",
            "virtual_default_reply": "",
            "force_non_empty_reply": True,
            "non_empty_reply_fallback": "询价格式：xx省 - xx省 - 重量（kg）\n长宽高（单位cm）",
        },
    )
    reply = service.generate_reply("随便问问")
    assert "询价格式" in reply


def test_messages_extract_locations_non_greedy_origin() -> None:
    origin, destination = MessagesService._extract_locations("从安徽寄到北京市朝阳区 2kg 多少钱")
    assert origin == "安徽"
    assert destination == "北京市朝阳区"


def test_messages_extract_locations_with_from_by_prefix() -> None:
    origin, destination = MessagesService._extract_locations("由杭州发到深圳市 1kg 报价")
    assert origin == "杭州"
    assert destination == "深圳市"


def test_messages_quote_keywords_fallback_when_empty_configured() -> None:
    service = MessagesService(controller=None, config={"quote_intent_keywords": []})
    assert service._is_quote_request("安徽到上海 1kg 圆通多少钱") is True


def test_messages_resolve_ws_cookie_prefers_env_over_config(monkeypatch: pytest.MonkeyPatch) -> None:
    service = MessagesService(controller=None, config={"cookie": "unb=config_user; _m_h5_tk=configtoken_1"})
    origin_getenv = os.getenv

    def _fake_getenv(key: str, default: str | None = None) -> str | None:
        if key == "XIANYU_COOKIE_1":
            return "unb=env_user; _m_h5_tk=envtoken_1"
        return origin_getenv(key, default)

    monkeypatch.setattr(os, "getenv", _fake_getenv)
    resolved = service._resolve_ws_cookie()
    assert resolved.startswith("unb=env_user")


def test_messages_quote_detection_avoids_false_positive_for_logistics_status() -> None:
    service = MessagesService(controller=None, config={"quote_intent_keywords": []})
    assert service._is_quote_request("你好 到货了吗") is False
    assert service._is_quote_request("你好 到货了吗 2kg") is False


def test_messages_extract_locations_supports_compact_separator_format() -> None:
    origin, destination = MessagesService._extract_locations("杭州～北京～2kg")
    assert origin == "杭州"
    assert destination == "北京"


def test_messages_extract_locations_supports_labeled_format() -> None:
    origin, destination = MessagesService._extract_locations("寄件杭州 收件北京 2kg")
    assert origin == "杭州"
    assert destination == "北京"


def test_messages_build_quote_request_extracts_volume_and_volume_weight() -> None:
    service = MessagesService(controller=None, config={})
    req, missing = service._build_quote_request("杭州～北京～2kg 30x20x10cm 体积重1.6kg")
    assert missing == []
    assert req is not None
    assert req.volume == 6000
    assert req.volume_weight == 1.6


@pytest.mark.asyncio
async def test_messages_auto_reply_unread_dry_run(mock_controller) -> None:
    service = MessagesService(controller=mock_controller, config={"max_replies_per_run": 5})
    service.get_unread_sessions = AsyncMock(
        return_value=[
            {
                "session_id": "s1",
                "peer_name": "买家A",
                "item_title": "iPhone 15",
                "last_message": "最低多少",
                "unread_count": 1,
            },
            {
                "session_id": "s2",
                "peer_name": "买家B",
                "item_title": "",
                "last_message": "还在吗",
                "unread_count": 2,
            },
        ]
    )
    service.reply_to_session = AsyncMock(return_value=True)

    result = await service.auto_reply_unread(limit=10, dry_run=True)

    assert result["total"] == 2
    assert result["success"] == 2
    assert result["failed"] == 0
    assert result["dry_run"] is True
    service.reply_to_session.assert_not_called()


@pytest.mark.asyncio
async def test_messages_quote_request_generates_quote(mock_controller) -> None:
    service = MessagesService(controller=mock_controller, config={"max_replies_per_run": 3, "fast_reply_enabled": True})
    service.get_unread_sessions = AsyncMock(
        return_value=[
            {
                "session_id": "q1",
                "peer_name": "买家Q",
                "item_title": "快递服务",
                "last_message": "从上海寄到杭州 2kg 多少钱",
                "unread_count": 1,
            }
        ]
    )

    result = await service.auto_reply_unread(limit=5, dry_run=True)
    detail = result["details"][0]

    assert detail["is_quote"] is True
    assert detail["quote_success"] is True
    assert "首单价格" in detail["reply"] or "可选快递报价" in detail["reply"]
    assert "预计" in detail["reply"]
    assert result["quote_success_rate"] == 1.0


@pytest.mark.asyncio
async def test_messages_quote_request_single_courier_mode(mock_controller) -> None:
    service = MessagesService(
        controller=mock_controller,
        config={"max_replies_per_run": 3, "fast_reply_enabled": True, "quote_reply_all_couriers": False},
    )
    service.get_unread_sessions = AsyncMock(
        return_value=[
            {
                "session_id": "q_single",
                "peer_name": "买家Q",
                "item_title": "快递服务",
                "last_message": "从上海寄到杭州 2kg 多少钱",
                "unread_count": 1,
            }
        ]
    )

    result = await service.auto_reply_unread(limit=5, dry_run=True)
    detail = result["details"][0]

    assert detail["is_quote"] is True
    assert detail["quote_success"] is True
    assert "首单价格" in detail["reply"]
    assert "quote_all_couriers" not in detail


@pytest.mark.asyncio
async def test_messages_quote_request_missing_fields_returns_followup_question(mock_controller) -> None:
    service = MessagesService(controller=mock_controller, config={"max_replies_per_run": 3})
    service.get_unread_sessions = AsyncMock(
        return_value=[
            {
                "session_id": "q2",
                "peer_name": "买家M",
                "item_title": "快递服务",
                "last_message": "寄到北京运费多少",
                "unread_count": 1,
            }
        ]
    )

    result = await service.auto_reply_unread(limit=5, dry_run=True)
    detail = result["details"][0]

    assert detail["is_quote"] is True
    assert detail["quote_need_info"] is True
    assert detail["quote_success"] is False
    assert "询价格式" in detail["reply"]


@pytest.mark.asyncio
async def test_messages_strict_format_mode_forces_standard_template(mock_controller) -> None:
    service = MessagesService(
        controller=mock_controller, config={"max_replies_per_run": 3, "strict_format_reply_enabled": True}
    )
    service.get_unread_sessions = AsyncMock(
        return_value=[
            {
                "session_id": "q_strict",
                "peer_name": "买家S",
                "item_title": "快递服务",
                "last_message": "在吗",
                "unread_count": 1,
            }
        ]
    )

    result = await service.auto_reply_unread(limit=5, dry_run=True)
    detail = result["details"][0]

    assert detail["is_quote"] is True
    assert detail["quote_need_info"] is True
    assert detail["format_enforced"] is True
    assert "询价格式" in detail["reply"]


@pytest.mark.asyncio
async def test_messages_non_strict_mode_keeps_general_reply_for_non_quote(mock_controller) -> None:
    service = MessagesService(
        controller=mock_controller, config={"max_replies_per_run": 3, "strict_format_reply_enabled": False}
    )
    service.get_unread_sessions = AsyncMock(
        return_value=[
            {
                "session_id": "q_non_strict",
                "peer_name": "买家N",
                "item_title": "快递服务",
                "last_message": "这个商品有货吗",
                "unread_count": 1,
            }
        ]
    )

    result = await service.auto_reply_unread(limit=5, dry_run=True)
    detail = result["details"][0]

    assert detail["is_quote"] is False
    assert "询价格式" not in detail["reply"]


@pytest.mark.asyncio
async def test_messages_greeting_forces_standard_template_even_non_strict(mock_controller) -> None:
    service = MessagesService(
        controller=mock_controller, config={"max_replies_per_run": 3, "strict_format_reply_enabled": False}
    )
    service.get_unread_sessions = AsyncMock(
        return_value=[
            {
                "session_id": "q_greeting",
                "peer_name": "买家G",
                "item_title": "快递服务",
                "last_message": "你好",
                "unread_count": 1,
            }
        ]
    )

    result = await service.auto_reply_unread(limit=5, dry_run=True)
    detail = result["details"][0]

    assert detail["is_quote"] is True
    assert detail["quote_need_info"] is True
    assert detail["format_enforced"] is True
    assert detail["format_enforced_reason"] == "greeting"
    assert "询价格式" in detail["reply"]


@pytest.mark.asyncio
async def test_messages_courier_choice_returns_checkout_guide(mock_controller) -> None:
    service = MessagesService(
        controller=mock_controller,
        config={
            "max_replies_per_run": 3,
            "strict_format_reply_enabled": False,
            "context_memory_enabled": True,
            "quote_reply_all_couriers": True,
            "quote": {"preferred_couriers": ["圆通", "中通", "韵达", "顺丰"]},
        },
    )

    first = await service.process_session(
        {
            "session_id": "ctx_follow_1",
            "peer_name": "买家C",
            "item_title": "快递服务",
            "last_message": "从上海寄到杭州 多少钱",
            "unread_count": 1,
        },
        dry_run=True,
    )
    assert first["is_quote"] is True
    assert first["quote_need_info"] is True
    assert first["quote_success"] is False

    second = await service.process_session(
        {
            "session_id": "ctx_follow_1",
            "peer_name": "买家C",
            "item_title": "快递服务",
            "last_message": "2kg",
            "unread_count": 1,
        },
        dry_run=True,
    )
    assert second["is_quote"] is True
    assert second["quote_success"] is True
    assert ("可选快递报价" in second["reply"]) or ("首单价格" in second["reply"])


@pytest.mark.asyncio
async def test_messages_courier_choice_returns_checkout_guide(mock_controller) -> None:
    service = MessagesService(
        controller=mock_controller,
        config={
            "max_replies_per_run": 3,
            "strict_format_reply_enabled": False,
            "context_memory_enabled": True,
            "quote_reply_all_couriers": True,
            "quote": {"preferred_couriers": ["圆通", "中通", "韵达", "顺丰"]},
        },
    )

    quoted = await service.process_session(
        {
            "session_id": "ctx_order_1",
            "peer_name": "买家O",
            "item_title": "快递服务",
            "last_message": "从上海寄到杭州 2kg 多少钱",
            "unread_count": 1,
        },
        dry_run=True,
    )
    assert quoted["is_quote"] is True
    assert quoted["quote_success"] is True

    choose = await service.process_session(
        {
            "session_id": "ctx_order_1",
            "peer_name": "买家O",
            "item_title": "快递服务",
            "last_message": "选圆通",
            "unread_count": 1,
        },
        dry_run=True,
    )
    assert choose["is_quote"] is False
    assert choose["courier_locked"] is True
    assert "先拍下链接" in choose["reply"]
    assert "无需提供" in choose["reply"]


@pytest.mark.asyncio
async def test_messages_get_unread_sessions_fallback_to_dom_when_ws_not_ready(mock_controller) -> None:
    service = MessagesService(
        controller=mock_controller, config={"transport": "auto", "strict_format_reply_enabled": True}
    )
    ws_transport = Mock()
    ws_transport.get_unread_sessions = AsyncMock(return_value=[])
    ws_transport.is_ready = Mock(return_value=False)
    service._ensure_ws_transport = AsyncMock(return_value=ws_transport)
    service._get_unread_sessions_dom = AsyncMock(
        return_value=[
            {
                "session_id": "dom_1",
                "peer_name": "买家D",
                "item_title": "快递服务",
                "last_message": "你好",
                "unread_count": 1,
            }
        ]
    )

    result = await service.get_unread_sessions(limit=5)

    assert len(result) == 1
    assert result[0]["session_id"] == "dom_1"
    service._get_unread_sessions_dom.assert_awaited_once()


@pytest.mark.asyncio
async def test_messages_reply_to_session_fallback_to_dom_when_ws_send_failed(mock_controller) -> None:
    service = MessagesService(
        controller=mock_controller, config={"transport": "auto", "strict_format_reply_enabled": True}
    )
    ws_transport = Mock()
    ws_transport.send_text = AsyncMock(return_value=False)
    service._ensure_ws_transport = AsyncMock(return_value=ws_transport)
    service._send_reply_on_page = AsyncMock(return_value=True)

    sent = await service.reply_to_session(
        "session_dom_fallback", "询价格式：xx省 - xx省 - 重量（kg）\n长宽高（单位cm）"
    )

    assert sent is True
    service._send_reply_on_page.assert_awaited_once()


@pytest.mark.asyncio
async def test_messages_ws_mode_does_not_fallback_to_dom_when_ws_send_failed(mock_controller) -> None:
    service = MessagesService(
        controller=mock_controller, config={"transport": "ws", "strict_format_reply_enabled": True}
    )
    ws_transport = Mock()
    ws_transport.send_text = AsyncMock(return_value=False)
    service._ensure_ws_transport = AsyncMock(return_value=ws_transport)
    service._send_reply_on_page = AsyncMock(return_value=True)

    sent = await service.reply_to_session("session_ws_only", "询价格式：xx省 - xx省 - 重量（kg）\n长宽高（单位cm）")

    assert sent is False
    service._send_reply_on_page.assert_not_called()


@pytest.mark.asyncio
async def test_messages_quote_blocked_by_policy_not_counted_as_quote_success(mock_controller) -> None:
    service = MessagesService(controller=mock_controller, config={"max_replies_per_run": 3})
    service.get_unread_sessions = AsyncMock(
        return_value=[
            {
                "session_id": "q3",
                "peer_name": "买家B",
                "item_title": "快递服务",
                "last_message": "从上海寄到杭州 2kg 多少钱",
                "unread_count": 1,
            }
        ]
    )
    service.compliance_center.evaluate_before_send = Mock(
        return_value=ComplianceDecision(
            allowed=False,
            blocked=True,
            reason="high_risk_stop_word",
            hits=["站外"],
            policy_scope="global",
        )
    )

    result = await service.auto_reply_unread(limit=5, dry_run=False)
    detail = result["details"][0]

    assert detail["is_quote"] is True
    assert detail["blocked_by_policy"] is True
    assert detail["quote_success"] is False
    assert detail["quote_blocked_by_policy"] is True
    assert result["quote_success_rate"] == 0.0

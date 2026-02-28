"""消息 WebSocket 适配层基础测试。"""

import base64
import json

from src.modules.messages.ws_live import GoofishWsTransport, decode_sync_payload, extract_chat_event, parse_cookie_header


def test_parse_cookie_header_extracts_pairs() -> None:
    cookie = "a=1; b=2; _tb_token_=abc123"
    parsed = parse_cookie_header(cookie)
    assert parsed["a"] == "1"
    assert parsed["b"] == "2"
    assert parsed["_tb_token_"] == "abc123"


def test_decode_sync_payload_supports_urlsafe_base64() -> None:
    payload = {"hello": "world", "ok": True}
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")
    assert decode_sync_payload(encoded) == payload


def test_extract_chat_event_with_string_keys() -> None:
    event = extract_chat_event(
        {
            "1": {
                "2": "chat_1@goofish",
                "5": 1772257395252,
                "10": {
                    "reminderContent": "从上海寄到杭州 1kg 多少钱",
                    "senderUserId": "10001",
                    "reminderTitle": "买家A",
                    "reminderUrl": "https://www.goofish.com/im?itemId=123456",
                },
            }
        }
    )
    assert event is not None
    assert event["chat_id"] == "chat_1"
    assert event["sender_user_id"] == "10001"
    assert event["sender_name"] == "买家A"
    assert event["item_id"] == "123456"


def test_extract_chat_event_with_int_keys() -> None:
    event = extract_chat_event(
        {
            1: {
                2: "chat_2@goofish",
                5: 1772257395252,
                10: {
                    "content": "还在吗",
                    "fromUserId": "20002",
                    "senderNick": "买家B",
                },
            }
        }
    )
    assert event is not None
    assert event["chat_id"] == "chat_2"
    assert event["sender_user_id"] == "20002"
    assert event["sender_name"] == "买家B"
    assert event["text"] == "还在吗"


def test_ws_transport_cookie_hot_reload() -> None:
    holder = {
        "cookie": "unb=10001; _m_h5_tk=token_a_123; cookie2=a; _tb_token_=t; sgcookie=s"
    }

    transport = GoofishWsTransport(
        cookie_text=holder["cookie"],
        config={"token_refresh_interval_seconds": 3600},
        cookie_supplier=lambda: holder["cookie"],
    )
    transport._token = "cached-token"
    transport._token_ts = 123.0

    holder["cookie"] = "unb=10001; _m_h5_tk=token_b_456; cookie2=b; _tb_token_=t2; sgcookie=s2"
    changed = transport._maybe_reload_cookie(reason="test")
    assert changed is True
    assert transport.cookies["_m_h5_tk"] == "token_b_456"
    assert transport._token == ""
    assert transport._token_ts == 0.0


def test_ws_transport_auth_error_marker() -> None:
    assert GoofishWsTransport._is_auth_related_error(Exception("Token API failed: ['FAIL_SYS_USER_VALIDATE']")) is True
    assert GoofishWsTransport._is_auth_related_error(Exception("server rejected WebSocket connection: HTTP 400")) is True
    assert GoofishWsTransport._is_auth_related_error(Exception("network reset by peer")) is False


def test_ws_transport_auth_hold_until_cookie_update_enabled_by_default() -> None:
    transport = GoofishWsTransport(
        cookie_text="unb=10001; _m_h5_tk=token_a_123; cookie2=a; _tb_token_=t; sgcookie=s",
        config={},
    )
    assert transport.auth_hold_until_cookie_update is True

    transport_relaxed = GoofishWsTransport(
        cookie_text="unb=10001; _m_h5_tk=token_a_123; cookie2=a; _tb_token_=t; sgcookie=s",
        config={"auth_hold_until_cookie_update": False},
    )
    assert transport_relaxed.auth_hold_until_cookie_update is False

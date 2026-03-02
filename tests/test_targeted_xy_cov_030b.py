from __future__ import annotations

from types import CodeType, FunctionType

from src.modules.messages import ws_live


def test_extract_chat_event_inner_pick_returns_none_for_non_dict_object() -> None:
    pick_code = next(
        const
        for const in ws_live.extract_chat_event.__code__.co_consts
        if isinstance(const, CodeType) and const.co_name == "_pick"
    )
    pick = FunctionType(pick_code, ws_live.extract_chat_event.__globals__)

    assert pick("not-a-dict", "1", 1) is None

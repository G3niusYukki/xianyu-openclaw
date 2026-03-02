from src.modules.messages.safety_guard import SafetyGuard


def test_safety_guard_keeps_prohibited_when_keyword_exists() -> None:
    guard = SafetyGuard(lambda _m, _c: {"is_prohibited": True, "prohibited_reason": "疑似禁寄"})
    decision = guard.check("杭州到北京寄手机")

    assert decision.llm_flagged is True
    assert decision.prohibited is True
    assert decision.matched_keyword == "手机"


def test_safety_guard_overrides_context_pollution_false_positive() -> None:
    guard = SafetyGuard(lambda _m, _c: {"is_prohibited": True, "prohibited_reason": "历史提及手机"})
    decision = guard.check("杭州到北京 2kg")

    assert decision.llm_flagged is True
    assert decision.prohibited is False
    assert decision.matched_keyword is None


def test_safety_guard_non_prohibited_when_llm_says_no() -> None:
    guard = SafetyGuard(lambda _m, _c: {"is_prohibited": False})
    decision = guard.check("杭州到北京 2kg")
    assert decision.prohibited is False
    assert decision.llm_flagged is False


def test_safety_guard_whitelist_keyword_returns_none() -> None:
    guard = SafetyGuard(lambda _m, _c: {"is_prohibited": True})
    assert guard._match_keyword("蓝牙耳机") is None

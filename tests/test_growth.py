"""增长实验与漏斗测试。"""

from src.modules.growth.service import GrowthService


def test_growth_assignment_is_stable(temp_dir) -> None:
    service = GrowthService(db_path=str(temp_dir / "growth.db"))

    a1 = service.assign_variant("exp_reply", "session_1")
    a2 = service.assign_variant("exp_reply", "session_1")

    assert a1["variant"] in {"A", "B"}
    assert a2["variant"] == a1["variant"]
    assert a2["new_assignment"] is False


def test_growth_funnel_and_compare(temp_dir) -> None:
    service = GrowthService(db_path=str(temp_dir / "growth.db"))

    service.assign_variant("exp_quote", "u1", variants=("A", "B"))
    service.assign_variant("exp_quote", "u2", variants=("A", "B"))

    service.record_event("u1", "inquiry", experiment_id="exp_quote")
    service.record_event("u1", "quoted", experiment_id="exp_quote")
    service.record_event("u1", "ordered", experiment_id="exp_quote")

    service.record_event("u2", "inquiry", experiment_id="exp_quote")
    service.record_event("u2", "quoted", experiment_id="exp_quote")

    funnel = service.funnel_stats(days=7, bucket="day")
    compare = service.compare_variants("exp_quote", from_stage="inquiry", to_stage="ordered")

    assert funnel["series"]
    assert compare["experiment_id"] == "exp_quote"
    assert "variants" in compare


def test_growth_strategy_version_and_rollback(temp_dir) -> None:
    service = GrowthService(db_path=str(temp_dir / "growth.db"))

    service.set_strategy_version("quote", "v1", active=True, baseline=True)
    service.set_strategy_version("quote", "v2", active=True, baseline=False)

    active_before = service.get_active_strategy("quote")
    rolled = service.rollback_to_baseline("quote")
    active_after = service.get_active_strategy("quote")

    assert active_before["version"] == "v2"
    assert rolled["version"] == "v1"
    assert active_after["version"] == "v1"

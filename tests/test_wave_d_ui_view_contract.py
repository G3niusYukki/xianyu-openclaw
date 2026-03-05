from src.dashboard_server import DASHBOARD_HTML


def test_wave_d_ui_product_ops_only_uses_stable_fields() -> None:
    for key in (
        "exposure_count",
        "paid_order_count",
        "paid_amount_cents",
        "refund_order_count",
        "exception_count",
        "manual_takeover_count",
        "conversion_rate_pct",
    ):
        assert key in DASHBOARD_HTML


def test_wave_d_ui_has_placeholder_and_disabled_action_copy() -> None:
    assert "占位(禁用态)" in DASHBOARD_HTML
    assert "可执行动作（禁用态）" in DASHBOARD_HTML


def test_wave_d_ui_uses_escaped_newline_sequences_in_inspect_view() -> None:
    assert '.join("\\n")' in DASHBOARD_HTML

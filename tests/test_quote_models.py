"""报价结果文案格式测试。"""

from src.modules.quote.models import QuoteResult


def test_compose_reply_displays_eta_in_days() -> None:
    result = QuoteResult(
        provider="cost_table_markup",
        base_fee=4.71,
        surcharges={"续重": 3.10},
        total_fee=7.81,
        eta_minutes=2880,
        explain={
            "matched_origin": "上海",
            "matched_destination": "北京",
            "matched_courier": "韵达",
            "actual_weight_kg": 2.0,
        },
    )

    reply = result.compose_reply(validity_minutes=30)

    assert "预估报价 ¥7.81" in reply
    assert "预计时效约 2天" in reply
    assert "报价有效期" not in reply


def test_compose_reply_template_fallback_when_template_invalid() -> None:
    result = QuoteResult(
        provider="rule_table",
        base_fee=8.0,
        surcharges={"distance": 4.0},
        total_fee=12.0,
        eta_minutes=720,
        explain={},
    )

    reply = result.compose_reply(validity_minutes=15, template="{unknown_field}")

    assert "预估报价 ¥12.00" in reply
    assert "预计时效约 1天" in reply
    assert "报价有效期" not in reply


def test_compose_reply_strips_validity_clause_from_custom_template() -> None:
    result = QuoteResult(
        provider="rule_table",
        base_fee=8.0,
        surcharges={},
        total_fee=8.0,
        eta_minutes=1440,
        explain={"matched_origin": "杭州", "matched_destination": "南京"},
    )

    reply = result.compose_reply(
        validity_minutes=45,
        template="您好，{origin} 到 {destination}，预估报价 ¥{price}，报价有效期 {validity_minutes} 分钟。",
    )

    assert "预估报价 ¥8.00" in reply
    assert "报价有效期" not in reply


def test_compose_reply_supports_legacy_alias_placeholders() -> None:
    result = QuoteResult(
        provider="cost_table_markup",
        base_fee=5.0,
        surcharges={"续重": 1.6},
        total_fee=6.6,
        eta_minutes=1440,
        explain={
            "matched_origin": "安徽",
            "matched_destination": "浙江",
            "matched_courier": "韵达",
            "actual_weight_kg": 1.2,
            "billing_weight_kg": 1.6,
            "volume_weight_kg": 1.6,
            "volume_divisor": 6000,
        },
    )

    reply = result.compose_reply(
        template=(
            "{origin_province}到{dest_province} {billing_weight}kg\n"
            "{volume_formula}\n"
            "{courier_name}: {total_price} 元\n"
            "首重{first_price} 续重{remaining_price} 续重单位{additional_units}kg"
        )
    )

    assert "安徽到浙江 1.6kg" in reply
    assert "体积(cm³)/6000" in reply
    assert "韵达: 6.60 元" in reply
    assert "首重5.00 续重1.60 续重单位0.6kg" in reply

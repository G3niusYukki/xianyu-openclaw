from __future__ import annotations

import hashlib

from src.integrations.xianguanjia.signing import (
    sign_open_platform_request,
    sign_virtual_supply_request,
    verify_open_platform_callback_signature,
    verify_virtual_supply_callback_signature,
)


def test_open_platform_sign_formula() -> None:
    body = '{"product_id":"219530767978565"}'
    sign = sign_open_platform_request(
        app_key="A1B2C3D4",
        app_secret="SECRET",
        timestamp="1740380565",
        body=body,
    )
    body_md5 = hashlib.md5(body.encode("utf-8")).hexdigest()
    expected = hashlib.md5(f"A1B2C3D4,{body_md5},1740380565,SECRET".encode("utf-8")).hexdigest()
    assert sign == expected


def test_virtual_supply_sign_formula() -> None:
    body = '{"goods_type":1,"goods_no":"12344532"}'
    sign = sign_virtual_supply_request(
        app_id="677859093659717",
        app_secret="wK63PxlOBaY9NoqMksLeZySzGIW25ifA",
        mch_id="1001",
        mch_secret="o9wl81dncmvby3ijpq7eur456zhgtaxs",
        timestamp="1724414553",
        body=body,
    )
    body_md5 = hashlib.md5(body.encode("utf-8")).hexdigest()
    expected = hashlib.md5(
        (
            "677859093659717,wK63PxlOBaY9NoqMksLeZySzGIW25ifA,"
            f"{body_md5},1724414553,1001,o9wl81dncmvby3ijpq7eur456zhgtaxs"
        ).encode("utf-8")
    ).hexdigest()
    assert sign == expected


def test_callback_verify_pass_and_fail() -> None:
    op_sign = sign_open_platform_request(
        app_key="AK",
        app_secret="AS",
        timestamp="1000",
        body="{}",
    )
    assert verify_open_platform_callback_signature(
        app_key="AK",
        app_secret="AS",
        timestamp="1000",
        sign=op_sign,
        body="{}",
    )
    assert not verify_open_platform_callback_signature(
        app_key="AK",
        app_secret="AS",
        timestamp="1000",
        sign="deadbeef",
        body="{}",
    )

    vs_sign = sign_virtual_supply_request(
        app_id="1",
        app_secret="2",
        mch_id="3",
        mch_secret="4",
        timestamp="1000",
        body="{}",
    )
    assert verify_virtual_supply_callback_signature(
        app_id="1",
        app_secret="2",
        mch_id="3",
        mch_secret="4",
        timestamp="1000",
        sign=vs_sign,
        body="{}",
    )
    assert not verify_virtual_supply_callback_signature(
        app_id="1",
        app_secret="2",
        mch_id="3",
        mch_secret="4",
        timestamp="1000",
        sign="deadbeef",
        body="{}",
    )


def test_dual_signature_not_mixed() -> None:
    body = '{"k":"v"}'
    op_sign = sign_open_platform_request(app_key="ak", app_secret="as", timestamp="1", body=body)
    assert not verify_virtual_supply_callback_signature(
        app_id="ak",
        app_secret="as",
        mch_id="m",
        mch_secret="ms",
        timestamp="1",
        sign=op_sign,
        body=body,
    )

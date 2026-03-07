"""闲管家签名与验签工具。

开放平台（自研模式）: md5("appKey,bodyMd5,timestamp,appSecret")
虚拟货源（已废弃，仅保留兼容）: md5("app_id,app_secret,bodyMd5,timestamp,mch_id,mch_secret")

参考文档: docs/xianguanjiajieruapi.md 签名规则说明
"""

from __future__ import annotations

import hashlib
import hmac

__all__ = [
    "sign_open_platform_request",
    "sign_virtual_supply_request",
    "verify_open_platform_callback_signature",
    "verify_virtual_supply_callback_signature",
]


def _md5_hex(value: str | bytes) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.md5(data).hexdigest()


def _body_md5(body: str | bytes | None) -> str:
    if body is None:
        payload = ""
    else:
        payload = body
    return _md5_hex(payload)


def sign_open_platform_request(
    *,
    app_key: str,
    app_secret: str,
    timestamp: str | int,
    body: str | bytes | None,
) -> str:
    """开放平台请求签名（自研模式，逗号分隔拼接）。

    sign = md5("appKey,bodyMd5,timestamp,appSecret")
    """
    parts = [str(app_key), _body_md5(body), str(timestamp), str(app_secret)]
    return _md5_hex(",".join(parts))


def sign_virtual_supply_request(
    *,
    app_id: str | int,
    app_secret: str,
    mch_id: str | int,
    mch_secret: str,
    timestamp: str | int,
    body: str | bytes | None,
) -> str:
    """虚拟货源请求签名。已废弃 — 用户场景不需要，仅保留兼容。"""
    plain = ",".join(
        [
            str(app_id),
            str(app_secret),
            _body_md5(body),
            str(timestamp),
            str(mch_id),
            str(mch_secret),
        ]
    )
    return _md5_hex(plain)


def verify_open_platform_callback_signature(
    *,
    app_key: str,
    app_secret: str,
    timestamp: str | int,
    sign: str,
    body: str | bytes | None,
) -> bool:
    """校验开放平台回调签名（订单/商品推送通知验签）。"""
    expected = sign_open_platform_request(
        app_key=app_key,
        app_secret=app_secret,
        timestamp=timestamp,
        body=body,
    )
    return hmac.compare_digest(expected, str(sign).strip().lower())


def verify_virtual_supply_callback_signature(
    *,
    app_id: str | int,
    app_secret: str,
    mch_id: str | int,
    mch_secret: str,
    timestamp: str | int,
    sign: str,
    body: str | bytes | None,
) -> bool:
    """校验虚拟货源回调签名。已废弃 — 用户场景不需要，仅保留兼容。"""
    expected = sign_virtual_supply_request(
        app_id=app_id,
        app_secret=app_secret,
        mch_id=mch_id,
        mch_secret=mch_secret,
        timestamp=timestamp,
        body=body,
    )
    return hmac.compare_digest(expected, str(sign).strip().lower())

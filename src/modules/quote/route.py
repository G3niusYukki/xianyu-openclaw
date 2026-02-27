"""地理路由标准化。"""

from __future__ import annotations

import re
from dataclasses import replace

from src.modules.quote.models import QuoteRequest

_ALIAS_MAP = {
    "北京": "北京市",
    "北京市": "北京市",
    "上海": "上海市",
    "上海市": "上海市",
    "天津": "天津市",
    "天津市": "天津市",
    "重庆": "重庆市",
    "重庆市": "重庆市",
    "内蒙": "内蒙古自治区",
    "内蒙古": "内蒙古自治区",
    "新疆": "新疆维吾尔自治区",
    "广西": "广西壮族自治区",
    "宁夏": "宁夏回族自治区",
    "西藏": "西藏自治区",
    "香港": "香港特别行政区",
    "澳门": "澳门特别行政区",
}

_SUFFIX_RE = re.compile(r"(?:省|市|区|县|自治区|自治州|地区|特别行政区)$")


def normalize_location(raw: str) -> str:
    text = re.sub(r"\s+", "", (raw or "").strip())
    if not text:
        return ""
    if text in _ALIAS_MAP:
        return _ALIAS_MAP[text]

    # 常见省市区后缀兼容：用于合并 cache key 与同义比较
    base = _SUFFIX_RE.sub("", text)
    return _ALIAS_MAP.get(base, text)


def normalize_request_route(request: QuoteRequest) -> QuoteRequest:
    return replace(
        request,
        origin=normalize_location(request.origin),
        destination=normalize_location(request.destination),
        service_level=(request.service_level or "standard").lower(),
        courier=(request.courier or "auto").lower(),
    )

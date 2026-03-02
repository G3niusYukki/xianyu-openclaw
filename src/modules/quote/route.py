"""地理路由标准化与三级模糊匹配。"""

from __future__ import annotations

from dataclasses import replace

from src.modules.quote.geo_resolver import GeoResolver
from src.modules.quote.models import QuoteRequest

_ALIAS_TO_FULL = {
    "北京": "北京市",
    "北京市": "北京市",
    "上海": "上海市",
    "上海市": "上海市",
    "天津": "天津市",
    "天津市": "天津市",
    "重庆": "重庆市",
    "重庆市": "重庆市",
}


def normalize_location(raw: str) -> str:
    compact = str(raw or "").strip()
    if compact in _ALIAS_TO_FULL:
        return _ALIAS_TO_FULL[compact]
    normalized = GeoResolver.normalize(compact)
    return _ALIAS_TO_FULL.get(normalized, normalized)


def normalize_request_route(request: QuoteRequest) -> QuoteRequest:
    return replace(
        request,
        origin=normalize_location(request.origin),
        destination=normalize_location(request.destination),
        service_level=(request.service_level or "standard").lower(),
        courier=(request.courier or "auto").lower(),
    )


def route_candidates(origin: str, destination: str, resolver: GeoResolver | None = None) -> list[tuple[str, str]]:
    """三级候选：精确 -> 省市混配候选。"""
    geo = resolver or GeoResolver()
    normalized_origin = GeoResolver.normalize(origin)
    normalized_destination = GeoResolver.normalize(destination)
    candidates: list[tuple[str, str]] = []
    if normalized_origin and normalized_destination:
        candidates.append((normalized_origin, normalized_destination))

    for pair in geo.cross_candidates(normalized_origin, normalized_destination):
        if pair not in candidates:
            candidates.append(pair)
    return candidates


def contains_match(origin: str, destination: str, row_origin: str, row_destination: str) -> bool:
    """第三级模糊匹配：双向包含。"""

    def _hit(left: str, right: str) -> bool:
        if not left or not right:
            return False
        if left == right:
            return True
        if len(left) >= 2 and left in right:
            return True
        if len(right) >= 2 and right in left:
            return True
        return False

    return _hit(GeoResolver.normalize(origin), GeoResolver.normalize(row_origin)) and _hit(
        GeoResolver.normalize(destination), GeoResolver.normalize(row_destination)
    )

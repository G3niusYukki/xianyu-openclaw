"""Tests for src.modules.quote.route."""

from src.modules.quote.models import QuoteRequest
from src.modules.quote.route import contains_match, normalize_location, normalize_request_route, route_candidates


def test_normalize_location_alias_and_resolver(monkeypatch) -> None:
    """分支：直辖市别名命中、GeoResolver.normalize兜底。"""
    assert normalize_location("北京") == "北京市"

    monkeypatch.setattr("src.modules.quote.route.GeoResolver.normalize", lambda raw: f"N-{raw}")
    assert normalize_location("杭州") == "N-杭州"


def test_normalize_request_route_lowercase_and_defaults(monkeypatch) -> None:
    """分支：service_level/courier lower；空值默认 standard/auto。"""
    monkeypatch.setattr("src.modules.quote.route.GeoResolver.normalize", lambda raw: raw)

    req = QuoteRequest(origin="上海", destination="北京", weight=1.0, service_level="EXPRESS", courier="SF")
    got = normalize_request_route(req)
    assert got.origin == "上海市"
    assert got.destination == "北京市"
    assert got.service_level == "express"
    assert got.courier == "sf"

    req2 = QuoteRequest(origin="杭州", destination="宁波", weight=1.0, service_level="", courier="")
    got2 = normalize_request_route(req2)
    assert got2.service_level == "standard"
    assert got2.courier == "auto"


class _Resolver:
    def cross_candidates(self, origin, destination):
        return [
            (origin, destination),
            ("浙江", destination),
            ("浙江", destination),
            (origin, "广东"),
        ]


def test_route_candidates_deduplicate_and_empty_normalized(monkeypatch) -> None:
    """分支：首个精确候选 + cross候选去重；normalize为空时无首项。"""
    monkeypatch.setattr("src.modules.quote.route.GeoResolver.normalize", lambda x: x.strip())

    candidates = route_candidates("杭州", "广州", resolver=_Resolver())
    assert candidates == [("杭州", "广州"), ("浙江", "广州"), ("杭州", "广东")]

    candidates2 = route_candidates(" ", "广州", resolver=_Resolver())
    assert candidates2 == [("", "广州"), ("浙江", "广州"), ("", "广东")]


def test_contains_match_cover_hit_paths(monkeypatch) -> None:
    """分支：相等命中、双向包含命中、长度<2不命中。"""
    monkeypatch.setattr("src.modules.quote.route.GeoResolver.normalize", lambda x: str(x or "").strip())

    assert contains_match("杭州", "广州", "杭州", "广州") is True
    assert contains_match("杭州", "广州", "浙江杭州", "广东广州") is True
    assert contains_match("A", "B", "ABC", "BCD") is False

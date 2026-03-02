from src.modules.messages.info_extractor import InfoExtractor


def test_info_extractor_regex_extracts_route_weight_dimension_and_courier() -> None:
    extractor = InfoExtractor()
    info = extractor.extract("杭州到北京 3kg 30x20x10 韵达")

    assert info.source == "regex"
    assert info.origin == "杭州"
    assert info.destination == "北京"
    assert info.weight == 3.0
    assert info.length == 30.0
    assert info.width == 20.0
    assert info.height == 10.0
    assert info.courier == "韵达"


def test_info_extractor_regex_converts_jin_to_kg() -> None:
    extractor = InfoExtractor()
    info = extractor.extract("广州到深圳 8斤")
    assert info.weight == 4.0


def test_info_extractor_llm_fallback_only_when_layer1_incomplete() -> None:
    calls = {"n": 0}

    def fake_llm(message: str, context: str) -> dict:
        calls["n"] += 1
        return {
            "origin": "杭州",
            "destination": "北京",
            "weight": 2.0,
            "courier": "圆通",
        }

    extractor = InfoExtractor(llm_extractor=fake_llm)

    complete = extractor.extract("杭州到北京 1kg")
    assert complete.source == "regex"
    assert calls["n"] == 0

    incomplete = extractor.extract("帮我查下报价")
    assert incomplete.source == "llm"
    assert incomplete.origin == "杭州"
    assert incomplete.destination == "北京"
    assert incomplete.weight == 2.0
    assert calls["n"] == 1

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.error_handler import BrowserError
from src.modules.listing.service import ListingService
from src.modules.messages.info_extractor import InfoExtractor
from src.modules.messages.reply_engine import ReplyStrategyEngine
from src.modules.orders.service import OrderFulfillmentService
from src.modules.quote.geo_resolver import GeoResolver


def test_geo_resolver_missing_file_and_empty_inputs(tmp_path: Path) -> None:
    resolver = GeoResolver(mapping_file=tmp_path / "nope.json")

    assert resolver.province_of(None) == ""
    assert resolver.expand_city_province_candidates("   ") == []


def test_geo_resolver_skip_invalid_map_items_and_keep_province_alias(tmp_path: Path) -> None:
    mapping = {
        "city_to_province": {
            "  ": "浙江省",  # invalid city -> skip
            "杭州": "浙江省",
            "宁波": "",  # invalid province -> skip
        }
    }
    p = tmp_path / "m.json"
    p.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")

    resolver = GeoResolver(mapping_file=p)

    assert resolver.province_of("杭州") == "浙江"
    assert resolver.province_of("浙江省") == "浙江"


def test_geo_resolver_ensure_suffix_and_empty() -> None:
    assert GeoResolver.ensure_full_province_suffix("") == ""
    assert GeoResolver.ensure_full_province_suffix("北京市") == "北京市"


def test_info_extractor_courier_custom_filters_blank_and_as_float_none_cases() -> None:
    ext = InfoExtractor(couriers=[" ", "顺丰", "顺丰"])
    assert ext._couriers == ["顺丰"]
    assert ext._as_float(None) is None
    assert ext._as_float("") is None
    assert ext._as_float("abc") is None


def test_info_extractor_normalize_location_empty_and_normalize_none(monkeypatch) -> None:
    ext = InfoExtractor()
    assert ext._normalize_location("   ") is None

    monkeypatch.setattr(ext.geo_resolver, "normalize", lambda _v: "")
    assert ext._normalize_location("杭州") is None


def test_reply_engine_parse_rule_default_reply_and_legacy_skip_empty() -> None:
    engine = ReplyStrategyEngine(
        default_reply="默认",
        virtual_default_reply="",
        keyword_replies={"": "x", "有值": "", "ok": "回"},
        intent_rules=[{"name": "n1", "reply": "", "keywords": ["a"]}],
    )

    parsed = engine._parse_rule({"name": "x", "reply": "  ", "keywords": []})
    assert parsed.reply == "默认"

    legacy = engine._build_legacy_keyword_rules({"": "x", "k": "  ", "kk": "vv"})
    assert len(legacy) == 1
    assert legacy[0].name == "legacy_kk"


def test_reply_engine_intent_rule_pattern_match_case_insensitive() -> None:
    engine = ReplyStrategyEngine(default_reply="默认", virtual_default_reply="虚拟")
    got = engine.generate_reply("预计 10 小时 到账 吗")
    assert "几分钟内处理" in got


def test_orders_map_status_fallback_branches(temp_dir: Path) -> None:
    svc = OrderFulfillmentService(db_path=str(temp_dir / "orders_map.db"))

    assert svc.map_status("need PAY now") == "paid"
    assert svc.map_status("ready to SHIP") == "shipping"
    assert svc.map_status("after case") == "after_sales"
    assert svc.map_status("signed 已签收") == "completed"
    assert svc.map_status("user cancel it") == "closed"


def test_orders_deliver_virtual_dry_run_completed_and_event(temp_dir: Path) -> None:
    svc = OrderFulfillmentService(db_path=str(temp_dir / "orders_dryrun.db"))
    svc.upsert_order(order_id="v1", raw_status="已付款", item_type="virtual")

    res = svc.deliver("v1", dry_run=True)
    trace = svc.trace_order("v1")

    assert res["status"] == "completed"
    assert trace["events"][-1]["event_type"] == "delivery"
    assert trace["events"][-1]["detail"]["dry_run"] is True


@pytest.mark.asyncio
async def test_listing_step_upload_images_logs_when_no_valid_paths(monkeypatch) -> None:
    controller = SimpleNamespace(find_elements=AsyncMock(return_value=[object()]), upload_files=AsyncMock())
    svc = ListingService(controller=controller)
    svc.delay_range = (0, 0)
    svc.logger = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None, success=lambda *a, **k: None)

    async def _no_sleep(_v):
        return None

    monkeypatch.setattr("src.modules.listing.service.asyncio.sleep", _no_sleep)

    await svc._step_upload_images("p1", ["", "   ", None])
    controller.upload_files.assert_not_awaited()


@pytest.mark.asyncio
async def test_listing_submit_warning_and_extract_product_id_exception_branch(monkeypatch) -> None:
    controller = SimpleNamespace(click=AsyncMock(return_value=False))
    svc = ListingService(controller=controller)
    svc.delay_range = (0, 0)
    svc.logger = SimpleNamespace(
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        success=lambda *a, **k: None,
        debug=lambda *a, **k: None,
    )

    async def _no_sleep(_v):
        return None

    monkeypatch.setattr("src.modules.listing.service.asyncio.sleep", _no_sleep)

    await svc._step_submit("p2")

    class BadUrl:
        def __str__(self):
            raise ValueError("bad")

    assert svc._extract_product_id(BadUrl()) == ""


@pytest.mark.asyncio
async def test_listing_verify_update_delete_raise_without_controller() -> None:
    svc = ListingService(controller=None)

    with pytest.raises(BrowserError):
        await svc.verify_listing("pid")
    with pytest.raises(BrowserError):
        await svc.update_listing("pid", {"price": 1})
    with pytest.raises(BrowserError):
        await svc.delete_listing("pid")

def test_reply_engine_virtual_default_fallback_branch() -> None:
    engine = ReplyStrategyEngine(default_reply="默认", virtual_default_reply="虚拟回复")
    assert engine.generate_reply("你好", item_title="超值会员卡").endswith("虚拟回复")


def test_info_extractor_extract_fast_empty_message_returns_default() -> None:
    ext = InfoExtractor()
    info = ext.extract_fast("   ")
    assert info.source == "regex"
    assert info.origin is None and info.destination is None and info.weight is None

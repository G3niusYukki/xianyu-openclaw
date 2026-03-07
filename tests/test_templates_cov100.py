from __future__ import annotations

from unittest.mock import patch

from src.modules.listing.templates import TEMPLATES, get_template, list_templates, render_template
from src.modules.listing.templates.base import (
    _build,
    _e,
    _features_html,
    _price_html,
    _tpl_account,
    _tpl_exchange,
    _tpl_express,
    _tpl_game,
    _tpl_movie_ticket,
    _tpl_recharge,
)

_SAFE_COMMON_STYLE = """
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    width: 750px; height: 1000px; overflow: hidden;
    background: linear-gradient(135deg, {bg_from} 0%, {bg_to} 100%);
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    padding: 40px;
}}
.card {{
    background: rgba(255,255,255,0.95); border-radius: 24px;
    padding: 48px 40px; width: 100%;
}}
.badge {{
    display: inline-block; background: {accent}; color: #fff;
    font-size: 14px; font-weight: 600; padding: 6px 16px;
    border-radius: 20px; margin-bottom: 16px;
}}
.title {{
    font-size: 32px; font-weight: 700; color: #1a1a2e;
}}
.desc {{
    font-size: 18px; color: #555; margin-bottom: 24px;
}}
.features {{
    list-style: none; padding: 0;
}}
.features li {{
    font-size: 16px; color: #333; padding: 10px 0;
}}
.features li::before {{
    content: "✓"; color: {accent}; font-weight: 700;
    margin-right: 12px; font-size: 18px;
}}
.price-tag {{
    margin-top: 24px; text-align: center;
}}
.price-tag .price {{
    font-size: 48px; font-weight: 800; color: {accent};
}}
.price-tag .unit {{
    font-size: 20px; color: #999; margin-left: 4px;
}}
.footer {{
    margin-top: 20px; text-align: center;
    font-size: 14px; color: #aaa;
}}
"""


def _patch_style():
    return patch("src.modules.listing.templates.base._COMMON_STYLE", _SAFE_COMMON_STYLE)


class TestHelpers:
    def test_escape(self):
        assert _e("<script>") == "&lt;script&gt;"
        assert _e("") == ""
        assert _e(None) == ""

    def test_features_html_empty(self):
        assert _features_html([]) == ""

    def test_features_html_items(self):
        result = _features_html(["A", "B"])
        assert "<li>" in result
        assert "A" in result

    def test_features_html_truncates_at_8(self):
        items = [str(i) for i in range(12)]
        result = _features_html(items)
        assert result.count("<li>") == 8

    def test_price_html_none(self):
        assert _price_html(None) == ""

    def test_price_html_value(self):
        result = _price_html(99.9)
        assert "¥" in result
        assert "99.9" in result


class TestBuild:
    def test_build_minimal(self):
        with _patch_style():
            html = _build(title="Test")
            assert "Test" in html
            assert "<!DOCTYPE html>" in html

    def test_build_full(self):
        with _patch_style():
            html = _build(
                title="T",
                desc="D",
                badge="B",
                features=["F1", "F2"],
                price=19.9,
                footer="Foot",
                bg_from="#fff",
                bg_to="#000",
                accent="#f00",
            )
            assert "T" in html
            assert "D" in html
            assert "B" in html
            assert "F1" in html
            assert "¥" in html
            assert "Foot" in html

    def test_build_no_badge_no_footer(self):
        with _patch_style():
            html = _build(title="X", badge="", footer="")
            assert "X" in html


class TestTemplateRenderers:
    def test_express_defaults(self):
        with _patch_style():
            html = _tpl_express({})
            assert "快递代发" in html

    def test_express_custom(self):
        with _patch_style():
            html = _tpl_express({"title": "Custom Express", "price": 5.5})
            assert "Custom Express" in html
            assert "5.5" in html

    def test_recharge_defaults(self):
        with _patch_style():
            html = _tpl_recharge({})
            assert "充值" in html

    def test_exchange_defaults(self):
        with _patch_style():
            html = _tpl_exchange({})
            assert "兑换码" in html

    def test_account_defaults(self):
        with _patch_style():
            html = _tpl_account({})
            assert "账号" in html

    def test_movie_ticket_defaults(self):
        with _patch_style():
            html = _tpl_movie_ticket({})
            assert "电影票" in html

    def test_game_defaults(self):
        with _patch_style():
            html = _tpl_game({})
            assert "游戏" in html

    def test_all_custom_params(self):
        with _patch_style():
            for func in [_tpl_express, _tpl_recharge, _tpl_exchange, _tpl_account, _tpl_movie_ticket, _tpl_game]:
                html = func({
                    "title": "T",
                    "desc": "D",
                    "badge": "B",
                    "features": ["F"],
                    "price": 10,
                    "footer": "FT",
                })
                assert "T" in html
                assert "D" in html


class TestModuleFunctions:
    def test_list_templates(self):
        result = list_templates()
        assert len(result) == 6
        keys = {item["key"] for item in result}
        assert "express" in keys
        assert "game" in keys

    def test_get_template_existing(self):
        tpl = get_template("express")
        assert tpl is not None
        assert "render" in tpl

    def test_get_template_missing(self):
        assert get_template("nonexistent") is None

    def test_render_template_valid(self):
        with _patch_style():
            html = render_template("express", {"title": "Hello"})
            assert html is not None
            assert "Hello" in html

    def test_render_template_missing_key_falls_back_to_exchange(self):
        with _patch_style():
            html = render_template("nonexistent_key_xyz")
            assert html is not None
            assert "兑换码" in html

    def test_render_template_no_params(self):
        with _patch_style():
            html = render_template("game")
            assert html is not None

    def test_render_template_completely_empty_templates(self):
        with patch.dict("src.modules.listing.templates.base.TEMPLATES", {}, clear=True):
            result = render_template("anything")
            assert result is None


class TestInitImports:
    def test_all_exports(self):
        from src.modules.listing.templates import __all__
        assert "TEMPLATES" in __all__
        assert "get_template" in __all__
        assert "list_templates" in __all__
        assert "render_template" in __all__

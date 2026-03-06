"""HTML 模板引擎 — 商品图片生成。

所有模板输出 750x1000 像素的 HTML 页面，
使用内联 CSS，无外部依赖，可直接被 Playwright 截图。
"""

from __future__ import annotations

from html import escape
from typing import Any

_COMMON_STYLE = """
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    width: 750px; height: 1000px; overflow: hidden;
    font-family: -apple-system, "PingFang SC", "Helvetica Neue", "Microsoft YaHei", sans-serif;
    background: linear-gradient(135deg, {bg_from} 0%, {bg_to} 100%);
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    padding: 40px;
}}
.card {{
    background: rgba(255,255,255,0.95); border-radius: 24px;
    padding: 48px 40px; width: 100%;
    box-shadow: 0 8px 32px rgba(0,0,0,0.08);
}}
.badge {{
    display: inline-block; background: {accent}; color: #fff;
    font-size: 14px; font-weight: 600; padding: 6px 16px;
    border-radius: 20px; margin-bottom: 16px;
}}
.title {{
    font-size: 32px; font-weight: 700; color: #1a1a2e;
    line-height: 1.4; margin-bottom: 20px;
}}
.desc {{
    font-size: 18px; color: #555; line-height: 1.8; margin-bottom: 24px;
}}
.features {{
    list-style: none; padding: 0;
}}
.features li {{
    font-size: 16px; color: #333; padding: 10px 0;
    border-bottom: 1px solid #f0f0f0;
    display: flex; align-items: center;
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

_HTML_SKELETON = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><style>{style}</style></head>
<body>
<div class="card">
  {badge}
  <div class="title">{title}</div>
  <div class="desc">{desc}</div>
  {features_html}
  {price_html}
  {footer_html}
</div>
</body>
</html>"""


def _e(text: str) -> str:
    return escape(str(text or ""))


def _features_html(items: list[str]) -> str:
    if not items:
        return ""
    li = "".join(f"<li>{_e(f)}</li>" for f in items[:8])
    return f'<ul class="features">{li}</ul>'


def _price_html(price: str | float | None) -> str:
    if price is None:
        return ""
    return f'<div class="price-tag"><span class="price">¥{_e(str(price))}</span><span class="unit">元</span></div>'


def _build(
    *,
    title: str,
    desc: str = "",
    badge: str = "",
    features: list[str] | None = None,
    price: str | float | None = None,
    footer: str = "",
    bg_from: str = "#e8f0fe",
    bg_to: str = "#f3e8ff",
    accent: str = "#4f46e5",
) -> str:
    style = _COMMON_STYLE.format(bg_from=bg_from, bg_to=bg_to, accent=accent)
    return _HTML_SKELETON.format(
        style=style,
        badge=f'<span class="badge">{_e(badge)}</span>' if badge else "",
        title=_e(title),
        desc=_e(desc),
        features_html=_features_html(features or []),
        price_html=_price_html(price),
        footer_html=f'<div class="footer">{_e(footer)}</div>' if footer else "",
    )


def _tpl_express(p: dict[str, Any]) -> str:
    return _build(
        title=p.get("title", "快递代发 · 全国包邮"),
        desc=p.get("desc", "专业快递代发，全国各大快递覆盖，一件代发无忧"),
        badge=p.get("badge", "快递代发"),
        features=p.get("features") or [
            "全国主流快递覆盖",
            "当天揽收，时效稳定",
            "支持退换补发",
            "批量下单优惠",
        ],
        price=p.get("price"),
        footer=p.get("footer", "下单后请提供收件信息"),
        bg_from="#e0f2fe", bg_to="#dbeafe", accent="#0284c7",
    )


def _tpl_recharge(p: dict[str, Any]) -> str:
    return _build(
        title=p.get("title", "话费 / 流量充值"),
        desc=p.get("desc", "三网通充，官方渠道，到账快速安全"),
        badge=p.get("badge", "充值卡"),
        features=p.get("features") or [
            "移动/联通/电信三网覆盖",
            "充值到账快，通常几分钟",
            "官方正规渠道",
            "下单留号自动充值",
        ],
        price=p.get("price"),
        footer=p.get("footer", "请确认手机号后下单"),
        bg_from="#fef3c7", bg_to="#fde68a", accent="#d97706",
    )


def _tpl_exchange(p: dict[str, Any]) -> str:
    return _build(
        title=p.get("title", "兑换码 · 即买即发"),
        desc=p.get("desc", "正版授权兑换码，付款后自动发送，安全可靠"),
        badge=p.get("badge", "兑换码"),
        features=p.get("features") or [
            "正版授权，安全保障",
            "付款后秒发卡密",
            "支持多平台兑换",
            "售后无忧",
        ],
        price=p.get("price"),
        footer=p.get("footer", "付款后自动发送兑换码"),
        bg_from="#ede9fe", bg_to="#e0e7ff", accent="#7c3aed",
    )


def _tpl_account(p: dict[str, Any]) -> str:
    return _build(
        title=p.get("title", "优质账号出售"),
        desc=p.get("desc", "账号安全可靠，资料齐全，支持验号"),
        badge=p.get("badge", "账号"),
        features=p.get("features") or [
            "账号资料完整",
            "支持买家验号",
            "提供售后保障",
            "安全换绑指导",
        ],
        price=p.get("price"),
        footer=p.get("footer", "请先咨询再下单"),
        bg_from="#dcfce7", bg_to="#d1fae5", accent="#16a34a",
    )


def _tpl_movie_ticket(p: dict[str, Any]) -> str:
    return _build(
        title=p.get("title", "电影票代购 · 全国影院"),
        desc=p.get("desc", "低价观影，全国主流影院覆盖，在线选座"),
        badge=p.get("badge", "电影票"),
        features=p.get("features") or [
            "低于平台价",
            "全国主流影院覆盖",
            "支持在线选座",
            "出票快速，电子票直接入场",
        ],
        price=p.get("price"),
        footer=p.get("footer", "请提供影院、场次、座位信息"),
        bg_from="#fce7f3", bg_to="#fce4ec", accent="#db2777",
    )


def _tpl_game(p: dict[str, Any]) -> str:
    return _build(
        title=p.get("title", "游戏充值 / 道具代购"),
        desc=p.get("desc", "正规渠道充值，快速到账，安全稳定"),
        badge=p.get("badge", "游戏"),
        features=p.get("features") or [
            "支持主流手游/端游",
            "正规渠道充值",
            "到账速度快",
            "专业客服售后",
        ],
        price=p.get("price"),
        footer=p.get("footer", "请提供游戏ID和区服信息"),
        bg_from="#fee2e2", bg_to="#fecaca", accent="#dc2626",
    )


TEMPLATES: dict[str, Any] = {
    "express": {"name": "快递代发", "render": _tpl_express},
    "recharge": {"name": "充值卡", "render": _tpl_recharge},
    "exchange": {"name": "兑换码/卡密", "render": _tpl_exchange},
    "account": {"name": "账号", "render": _tpl_account},
    "movie_ticket": {"name": "电影票", "render": _tpl_movie_ticket},
    "game": {"name": "游戏", "render": _tpl_game},
}


def list_templates() -> list[dict[str, str]]:
    return [{"key": k, "name": v["name"]} for k, v in TEMPLATES.items()]


def get_template(key: str) -> dict[str, Any] | None:
    return TEMPLATES.get(key)


def render_template(key: str, params: dict[str, Any] | None = None) -> str | None:
    tpl = TEMPLATES.get(key)
    if not tpl:
        tpl = TEMPLATES.get("exchange")
        if not tpl:
            return None
    return tpl["render"](params or {})

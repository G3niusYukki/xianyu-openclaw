"""商品图片 HTML 模板集合。

每个模板函数接收 params dict，返回完整 HTML 字符串。
截图服务 (image_generator.py) 使用 Playwright 将 HTML 渲染为 PNG。

支持品类:
- express      快递代发/物流
- recharge     充值卡
- exchange     兑换码/卡密
- account      账号
- movie_ticket 电影票/影院代购
- game         游戏道具/点券
"""

from .base import TEMPLATES, get_template, list_templates, render_template

__all__ = ["TEMPLATES", "get_template", "list_templates", "render_template"]

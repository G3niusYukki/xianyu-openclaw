"""虚拟货源模块 — 已废弃。

用户业务场景不需要自建供货服务，自动发货由闲管家平台完成。
本模块仅保留是因为 orders/store.py 和 dashboard_server.py 仍有数据结构依赖。
后续 Phase 将彻底移除。
"""

from .service import VirtualGoodsService
from .store import VirtualGoodsStore

__all__ = ["VirtualGoodsService", "VirtualGoodsStore"]

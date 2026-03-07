"""
运营操作服务
Operations Service

提供闲鱼店铺日常运营操作功能
"""

from __future__ import annotations

import asyncio
import random
import time
from datetime import datetime, timezone
from typing import Any

from src.core.compliance import get_compliance_guard
from src.core.config import get_config
from src.core.logger import get_logger
from src.integrations.xianguanjia.open_platform_client import OpenPlatformClient
from src.modules.analytics.service import AnalyticsService
from src.modules.listing.models import Listing
from src.modules.listing.service import ListingService


class OperationsSelectors:
    """
    运营页面元素选择器

    使用 Playwright 文本匹配和稳定属性选择器，
    避免依赖 React 动态生成的 class 名。
    """

    MY_SELLING = "https://www.goofish.com/my/selling"

    SELLING_ITEM = "[class*='item-card'], [class*='goods-item'], [class*='product-card']"
    ITEM_TITLE = "[class*='title']"
    ITEM_PRICE = "[class*='price']"

    POLISH_BUTTON = "button:has-text('擦亮'), a:has-text('擦亮'), [class*='polish'] button"
    POLISH_CONFIRM = "button:has-text('确认'), button:has-text('确定')"
    POLISH_SUCCESS = "[class*='success'], [class*='toast']"

    EDIT_PRICE = "button:has-text('调价'), button:has-text('改价'), a:has-text('调价')"
    PRICE_INPUT = "input[placeholder*='价格'], [class*='modal'] input[type='number'], [class*='price'] input"
    PRICE_MODAL = "[class*='modal'], [class*='dialog'], [role='dialog']"
    PRICE_SUBMIT = "button:has-text('确认'), button:has-text('确定')"

    DELIST_BUTTON = "button:has-text('下架'), a:has-text('下架'), button:has-text('删除')"
    DELIST_CONFIRM = "button:has-text('确定'), button:has-text('确认')"
    DELIST_REASON = "[class*='reason'] select, [class*='reason'] [class*='select']"

    RELIST_BUTTON = "button:has-text('重新上架'), a:has-text('重新上架'), button:has-text('上架')"
    RELIST_CONFIRM = "button:has-text('确定'), button:has-text('确认')"

    REFRESH_BUTTON = "button:has-text('刷新'), a:has-text('刷新')"

    BATCH_SELECT = "[class*='batch'] [class*='select'], input[type='checkbox'][class*='all']"
    BATCH_ACTION = "[class*='batch'] [class*='action'], [class*='toolbar']"

    NEXT_PAGE = "button:has-text('下一页'), a:has-text('下一页'), [class*='next']"
    PAGE_INFO = "[class*='page'], [class*='pagination']"


class OperationsService:
    """
    运营操作服务

    封装店铺日常运营操作，包括擦亮、降价、下架等
    """

    def __init__(
        self,
        controller=None,
        config: dict | None = None,
        analytics: AnalyticsService | None = None,
        api_client: OpenPlatformClient | None = None,
    ):
        self.controller = controller
        self.config = config or {}
        self.logger = get_logger()
        self.analytics = analytics
        self.compliance = get_compliance_guard()
        self.api_client = api_client or self._build_api_client()

        browser_config = get_config().browser
        self.delay_range = (
            browser_config.get("delay", {}).get("min", 1),
            browser_config.get("delay", {}).get("max", 3),
        )

        self.selectors = OperationsSelectors()

    def _build_api_client(self) -> OpenPlatformClient | None:
        cfg = self.config.get("xianguanjia")
        if not isinstance(cfg, dict) or not cfg.get("enabled", False):
            return None
        app_key = str(cfg.get("app_key", "")).strip()
        app_secret = str(cfg.get("app_secret", "")).strip()
        if not app_key or not app_secret:
            return None
        try:
            return OpenPlatformClient(
                base_url=str(cfg.get("base_url", "https://open.goofish.pro")).strip(),
                app_key=app_key,
                app_secret=app_secret,
                timeout=float(cfg.get("timeout", 30.0)),
            )
        except Exception as e:
            self.logger.warning(f"Failed to initialize XianGuanJia API client: {e}")
            return None

    @staticmethod
    def _ts() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @classmethod
    def _exec_contract(
        cls,
        *,
        ok: bool,
        action: str,
        code: str,
        message: str,
        data: dict[str, Any] | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "ok": bool(ok),
            "action": action,
            "code": code,
            "message": message,
            "data": data or {},
            "errors": list(errors or []),
            "ts": cls._ts(),
        }

    @staticmethod
    def _price_to_minor_units(value: float | int) -> int:
        return round(float(value) * 100)

    async def _try_update_price_via_api(
        self, product_id: str, new_price: float, original_price: float | None = None
    ) -> tuple[dict[str, Any] | None, str | None]:
        if not self.api_client:
            return None, "api_client_not_configured"

        payload: dict[str, Any] = {
            "product_id": str(product_id),
            "price": self._price_to_minor_units(new_price),
        }
        if original_price is not None:
            payload["original_price"] = self._price_to_minor_units(original_price)

        try:
            response = await asyncio.to_thread(self.api_client.edit_product, payload)
        except Exception as e:
            self.logger.warning(f"XianGuanJia price update failed for {product_id}: {e}")
            return None, str(e)

        if not response.ok:
            return None, response.error_message or "api_call_failed"

        return {
            "success": True,
            "product_id": product_id,
            "action": "price_update",
            "old_price": original_price,
            "new_price": new_price,
            "channel": "xianguanjia_api",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, None

    def _random_delay(self, min_factor: float = 1.0, max_factor: float = 1.0) -> float:
        """生成随机延迟"""
        min_delay = self.delay_range[0] * min_factor
        max_delay = self.delay_range[1] * max_factor
        return random.uniform(min_delay, max_delay)

    async def execute_product_action(
        self,
        action: str,
        *,
        payload: dict[str, Any] | None = None,
        internal_listing_id: str | None = None,
        api_client: OpenPlatformClient | None = None,
    ) -> dict[str, Any]:
        listing_service = ListingService(
            controller=self.controller,
            config=self.config,
            analytics=self.analytics,
        )
        listing = None
        if internal_listing_id:
            req = dict(payload or {})
            listing = Listing(
                title=str(req.get("title", "")),
                description=str(req.get("description", "")),
                price=float(req.get("price", 0.0) or 0.0),
                images=req.get("images") if isinstance(req.get("images"), list) else [],
                internal_listing_id=internal_listing_id,
            )
        return await listing_service.execute_product_action(
            action,
            payload=payload,
            listing=listing,
            api_client=api_client or self.api_client,
            allow_dom_fallback=False,
        )

    async def polish_listing(self, product_id: str) -> dict[str, Any]:
        """擦亮功能已停用。闲鱼平台已限制擦亮效果，该功能不再提供价值。"""
        return {
            "success": False,
            "product_id": product_id,
            "action": "polish",
            "error": "feature_disabled",
            "message": "擦亮功能已停用：闲鱼平台已限制擦亮效果",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    async def batch_polish(self, product_ids: list[str] | None = None, max_items: int = 50) -> dict[str, Any]:
        """批量擦亮功能已停用。"""
        return {
            "success": 0,
            "failed": 0,
            "total": 0,
            "action": "batch_polish",
            "blocked": True,
            "message": "擦亮功能已停用：闲鱼平台已限制擦亮效果",
            "details": [],
        }

    async def modify_order_price(self, order_no: str, order_price: int, express_fee: int | None = None) -> dict[str, Any]:
        if not self.api_client:
            return {"success": False, "channel": "xianguanjia_api", "error": "api_client_not_configured"}
        payload: dict[str, Any] = {
            "order_no": str(order_no),
            "order_price": int(order_price),
        }
        if express_fee is not None:
            payload["express_fee"] = int(express_fee)
        try:
            response = await asyncio.to_thread(self.api_client.modify_order_price, payload)
            if not response.ok:
                return {
                    "success": False,
                    "channel": "xianguanjia_api",
                    "order_no": order_no,
                    "order_price": int(order_price),
                    "error": response.error_message or "api_call_failed",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            return {
                "success": True,
                "channel": "xianguanjia_api",
                "order_no": order_no,
                "order_price": int(order_price),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception as e:
            return {
                "success": False,
                "channel": "xianguanjia_api",
                "order_no": order_no,
                "order_price": int(order_price),
                "error": str(e),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

    async def update_price(
        self, product_id: str, new_price: float, original_price: float | None = None
    ) -> dict[str, Any]:
        """通过闲管家 API 更新商品价格（纯 API，无 DOM fallback）。"""
        self.logger.info(f"Updating price for {product_id}: {original_price} -> {new_price}")

        api_result, api_error = await self._try_update_price_via_api(product_id, new_price, original_price)
        if api_result is not None:
            if self.analytics:
                await self.analytics.log_operation("PRICE_UPDATE", product_id, details=api_result)
            return api_result

        result = self._error_result("price_update", product_id, api_error or "api_client_not_configured")
        result["old_price"] = original_price
        result["new_price"] = new_price
        result["channel"] = "xianguanjia_api"
        if self.analytics:
            await self.analytics.log_operation("PRICE_UPDATE", product_id, details=result)
        return result

    async def batch_update_price(self, updates: list[dict[str, Any]], delay_range: tuple = (3, 6)) -> dict[str, Any]:
        """
        批量更新价格

        Args:
            updates: 更新列表 [{"product_id": "xxx", "new_price": 100}]
            delay_range: 操作间隔时间范围

        Returns:
            操作汇总结果
        """
        self.logger.info(f"Starting batch price update for {len(updates)} items...")

        results = []

        for i, update in enumerate(updates):
            product_id = update.get("product_id")
            new_price = update.get("new_price")
            original_price = update.get("original_price")

            try:
                result = await self.update_price(product_id, new_price, original_price)
                results.append(result)
            except Exception as e:
                results.append(self._error_result("price_update", product_id, str(e)))

            if i < len(updates) - 1:
                delay = random.uniform(*delay_range)
                await asyncio.sleep(delay)

        summary = {
            "success": sum(1 for r in results if r.get("success")),
            "failed": sum(1 for r in results if not r.get("success")),
            "total": len(results),
            "action": "batch_price_update",
            "details": results,
        }

        if self.analytics:
            await self.analytics.log_operation("BATCH_PRICE_UPDATE", None, details=summary)

        self.logger.success(f"Batch price update complete: {summary['success']}/{summary['total']}")
        return summary

    async def delist(self, product_id: str, reason: str = "不卖了") -> dict[str, Any]:
        """通过闲管家 API 下架商品。"""
        self.logger.info(f"Delisting {product_id}, reason: {reason}")

        if not self.api_client:
            return self._error_result("delist", product_id, "api_client_not_configured")

        try:
            response = await asyncio.to_thread(
                self.api_client.unpublish_product, {"product_id": str(product_id)}
            )
            success = response.ok
            result = {
                "success": success,
                "product_id": product_id,
                "action": "delist",
                "reason": reason,
                "channel": "xianguanjia_api",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            if not success:
                result["error"] = response.error_message or "api_call_failed"

            if self.analytics:
                await self.analytics.log_operation("DELIST", product_id, details=result)
            return result
        except Exception as e:
            self.logger.error(f"Delist failed: {e}")
            return self._error_result("delist", product_id, str(e))

    async def relist(self, product_id: str) -> dict[str, Any]:
        """通过闲管家 API 重新上架商品。"""
        self.logger.info(f"Relisting {product_id}")

        if not self.api_client:
            return self._error_result("relist", product_id, "api_client_not_configured")

        try:
            response = await asyncio.to_thread(
                self.api_client.publish_product, {"product_id": str(product_id)}
            )
            success = response.ok
            result = {
                "success": success,
                "product_id": product_id,
                "action": "relist",
                "channel": "xianguanjia_api",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            if not success:
                result["error"] = response.error_message or "api_call_failed"

            if self.analytics:
                await self.analytics.log_operation("RELIST", product_id, details=result)
            return result
        except Exception as e:
            self.logger.error(f"Relist failed: {e}")
            return self._error_result("relist", product_id, str(e))

    async def refresh_inventory(self) -> dict[str, Any]:
        """通过闲管家 API 获取商品列表刷新库存。"""
        self.logger.info("Refreshing inventory...")

        if not self.api_client:
            return {"success": False, "action": "inventory_refresh", "error": "api_client_not_configured"}

        try:
            response = await asyncio.to_thread(
                self.api_client.list_products, {"page_no": 1, "page_size": 100}
            )
            if not response.ok:
                return {"success": False, "action": "inventory_refresh", "error": response.error_message}

            data = response.data or {}
            items = data.get("list", []) if isinstance(data, dict) else []
            return {
                "success": True,
                "action": "inventory_refresh",
                "total_items": len(items) if isinstance(items, list) else 0,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception as e:
            self.logger.error(f"Inventory refresh failed: {e}")
            return {"success": False, "action": "inventory_refresh", "error": str(e)}

    async def get_listing_stats(self) -> dict[str, Any]:
        """通过闲管家 API 获取商品统计。"""
        self.logger.info("Fetching listing statistics...")

        if not self.api_client:
            return {"error": "api_client_not_configured"}

        try:
            response = await asyncio.to_thread(
                self.api_client.list_products, {"page_no": 1, "page_size": 100}
            )
            if not response.ok:
                return {"error": response.error_message or "api_call_failed"}

            data = response.data or {}
            items = data.get("list", []) if isinstance(data, dict) else []
            if not isinstance(items, list):
                items = []

            total = len(items)
            active = sum(1 for i in items if isinstance(i, dict) and i.get("status") in (1, "1", "on_sale"))
            return {
                "total": total,
                "active": active,
                "sold": 0,
                "deleted": 0,
                "total_views": sum(i.get("view_count", 0) for i in items if isinstance(i, dict)),
                "total_wants": sum(i.get("want_count", 0) for i in items if isinstance(i, dict)),
            }
        except Exception as e:
            self.logger.error(f"Failed to fetch stats: {e}")
            return {"error": str(e)}

    async def auto_adjust_price(
        self,
        product_id: str,
        current_price: float,
        *,
        strategy: str = "step_down",
        step_amount: float = 1.0,
        min_price: float | None = None,
        max_discount_pct: float = 0.3,
    ) -> dict[str, Any]:
        """自动改价 — 未支付订单场景下的策略性降价。

        Args:
            product_id: 商品 ID
            current_price: 当前价格
            strategy: 改价策略 (step_down=阶梯降价, restore=恢复原价)
            step_amount: 每次降价金额
            min_price: 最低价格保护
            max_discount_pct: 最大折扣比例 (0.0~1.0)
        """
        if not 0.0 <= max_discount_pct <= 1.0:
            return self._error_result("auto_adjust_price", product_id, "max_discount_pct must be between 0.0 and 1.0")

        if strategy == "restore":
            return await self.update_price(product_id, current_price)

        floor = min_price if min_price is not None else current_price * (1 - max_discount_pct)
        new_price = max(floor, current_price - step_amount)
        new_price = round(new_price, 2)

        if new_price >= current_price:
            return {
                "success": False,
                "product_id": product_id,
                "action": "auto_adjust_price",
                "error": "price_at_floor",
                "current_price": current_price,
                "floor_price": floor,
            }

        result = await self.update_price(product_id, new_price, current_price)
        result["action"] = "auto_adjust_price"
        result["strategy"] = strategy
        result["price_change"] = round(current_price - new_price, 2)
        return result

    def _error_result(self, action: str, product_id: str | None, error: str) -> dict[str, Any]:
        """生成错误结果"""
        return {
            "success": False,
            "product_id": product_id,
            "action": action,
            "error": error,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

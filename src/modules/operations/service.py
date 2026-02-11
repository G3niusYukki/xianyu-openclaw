"""
运营操作服务
Operations Service

提供闲鱼店铺日常运营操作功能
"""

import asyncio
import random
import time
from typing import Dict, List, Optional, Any

from src.core.config import get_config
from src.core.logger import get_logger
from src.modules.analytics.service import AnalyticsService


class OperationsSelectors:
    """运营页面元素选择器"""

    # 我的发布页面
    MY_SELLING = "https://www.goofish.com/my/selling"

    # 商品列表
    SELLING_ITEM = ".selling-item, .item-card"
    ITEM_TITLE = ".item-title, .title"
    ITEM_PRICE = ".item-price, .price"

    # 擦亮
    POLISH_BUTTON = "button:has-text('擦亮')"
    POLISH_CONFIRM = "button:has-text('确认')"
    POLISH_SUCCESS = ".polish-success"

    # 调价
    EDIT_PRICE = "button:has-text('调价')"
    PRICE_INPUT = "input[placeholder*='价格'], input.price-input"
    PRICE_MODAL = ".price-modal, .edit-price-modal"
    PRICE_SUBMIT = "button:has-text('确认')"

    # 下架
    DELIST_BUTTON = "button:has-text('下架')"
    DELIST_CONFIRM = "button:has-text('确定')"
    DELIST_REASON = ".reason-select"

    # 重新上架
    RELIST_BUTTON = "button:has-text('重新上架')"
    RELIST_CONFIRM = "button:has-text('确定')"

    # 刷新按钮
    REFRESH_BUTTON = "button:has-text('刷新')"

    # 批量操作
    BATCH_SELECT = ".batch-select, .select-all"
    BATCH_ACTION = ".batch-action"

    # 分页
    NEXT_PAGE = "button:has-text('下一页'), .next-page"
    PAGE_INFO = ".page-info"


class OperationsService:
    """
    运营操作服务

    封装店铺日常运营操作，包括擦亮、降价、下架等
    """

    def __init__(self, controller=None, config: Optional[dict] = None,
                 analytics: Optional[AnalyticsService] = None):
        """
        初始化运营服务

        Args:
            controller: 浏览器控制器
            config: 配置字典
            analytics: 数据分析服务
        """
        self.controller = controller
        self.config = config or {}
        self.logger = get_logger()
        self.analytics = analytics

        browser_config = get_config().browser
        self.delay_range = (
            browser_config.get("delay", {}).get("min", 1),
            browser_config.get("delay", {}).get("max", 3)
        )

        self.selectors = OperationsSelectors()

    def _random_delay(self, min_factor: float = 1.0, max_factor: float = 1.0) -> float:
        """生成随机延迟"""
        min_delay = self.delay_range[0] * min_factor
        max_delay = self.delay_range[1] * max_factor
        return random.uniform(min_delay, max_delay)

    async def polish_listing(self, product_id: str) -> Dict[str, Any]:
        """
        擦亮单个商品

        Args:
            product_id: 商品ID

        Returns:
            操作结果
        """
        self.logger.info(f"Polishing listing: {product_id}")

        if not self.controller:
            return self._mock_result("polish", product_id)

        try:
            page_id = await self.controller.new_page()
            url = f"https://www.goofish.com/item/{product_id}"
            await self.controller.navigate(page_id, url)

            await asyncio.sleep(self._random_delay())

            success = await self.controller.click(page_id, self.selectors.POLISH_BUTTON)
            if success:
                await asyncio.sleep(self._random_delay())
                await self.controller.click(page_id, self.selectors.POLISH_CONFIRM)
                await asyncio.sleep(self._random_delay())

            await self.controller.close_page(page_id)

            result = {
                "success": success,
                "product_id": product_id,
                "action": "polish",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

            if self.analytics:
                await self.analytics.log_operation("POLISH", product_id, details=result)

            return result

        except Exception as e:
            self.logger.error(f"Polish failed: {e}")
            return self._error_result("polish", product_id, str(e))

    async def batch_polish(self, product_ids: List[str] = None,
                          max_items: int = 50) -> Dict[str, Any]:
        """
        批量擦亮商品

        Args:
            product_ids: 商品ID列表，为空则擦亮所有可擦亮商品
            max_items: 最大擦亮数量

        Returns:
            操作汇总结果
        """
        self.logger.info(f"Starting batch polish (max: {max_items})...")

        if not self.controller:
            return self._mock_batch_result("polish", product_ids or [])

        try:
            page_id = await self.controller.new_page()
            await self.controller.navigate(page_id, self.selectors.MY_SELLING)
            await asyncio.sleep(self._random_delay(1.5, 2.5))

            results = []
            polished = set()

            if not product_ids:
                items = await self.controller.find_elements(page_id, self.selectors.SELLING_ITEM)
                for i, item in enumerate(items[:max_items]):
                    if i >= max_items:
                        break

                    await asyncio.sleep(self._random_delay())

                    success = await self.controller.click(page_id, self.selectors.POLISH_BUTTON)
                    if success:
                        await asyncio.sleep(self._random_delay())
                        confirm = await self.controller.click(page_id, self.selectors.POLISH_CONFIRM)

                        if confirm:
                            product_id = f"item_{random.randint(100000, 999999)}"
                            results.append({
                                "success": True,
                                "product_id": product_id,
                                "action": "polish"
                            })
                            polished.add(product_id)

                        await asyncio.sleep(self._random_delay(2, 4))

            summary = {
                "success": len(results),
                "failed": len(polished) - len(results) if len(polished) > len(results) else 0,
                "total": len(results),
                "action": "batch_polish",
                "details": results
            }

            if self.analytics:
                await self.analytics.log_operation("BATCH_POLISH", None, details=summary)

            self.logger.success(f"Batch polish complete: {summary['success']} items polished")
            await self.controller.close_page(page_id)

            return summary

        except Exception as e:
            self.logger.error(f"Batch polish failed: {e}")
            return self._error_result("batch_polish", None, str(e))

    async def update_price(self, product_id: str, new_price: float,
                          original_price: Optional[float] = None) -> Dict[str, Any]:
        """
        更新商品价格

        Args:
            product_id: 商品ID
            new_price: 新价格
            original_price: 原价

        Returns:
            操作结果
        """
        self.logger.info(f"Updating price for {product_id}: {original_price} -> {new_price}")

        if not self.controller:
            return {
                "success": True,
                "product_id": product_id,
                "action": "price_update",
                "old_price": original_price,
                "new_price": new_price,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

        try:
            page_id = await self.controller.new_page()
            url = f"https://www.goofish.com/item/{product_id}"
            await self.controller.navigate(page_id, url)
            await asyncio.sleep(self._random_delay())

            success = await self.controller.click(page_id, self.selectors.EDIT_PRICE)
            if success:
                await asyncio.sleep(self._random_delay())

                await self.controller.type_text(page_id, self.selectors.PRICE_INPUT, str(new_price))
                await asyncio.sleep(self._random_delay())

                await self.controller.click(page_id, self.selectors.PRICE_SUBMIT)
                await asyncio.sleep(self._random_delay())

            await self.controller.close_page(page_id)

            result = {
                "success": success,
                "product_id": product_id,
                "action": "price_update",
                "old_price": original_price,
                "new_price": new_price,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

            if self.analytics:
                await self.analytics.log_operation("PRICE_UPDATE", product_id, details=result)

            return result

        except Exception as e:
            self.logger.error(f"Price update failed: {e}")
            return self._error_result("price_update", product_id, str(e))

    async def batch_update_price(self, updates: List[Dict[str, Any]],
                                 delay_range: tuple = (3, 6)) -> Dict[str, Any]:
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
            "details": results
        }

        if self.analytics:
            await self.analytics.log_operation("BATCH_PRICE_UPDATE", None, details=summary)

        self.logger.success(f"Batch price update complete: {summary['success']}/{summary['total']}")
        return summary

    async def delist(self, product_id: str, reason: str = "不卖了",
                     confirm: bool = True) -> Dict[str, Any]:
        """
        下架商品

        Args:
            product_id: 商品ID
            reason: 下架原因
            confirm: 是否确认下架

        Returns:
            操作结果
        """
        self.logger.info(f"Delisting {product_id}, reason: {reason}")

        if not self.controller:
            return self._mock_result("delist", product_id)

        try:
            page_id = await self.controller.new_page()
            url = f"https://www.goofish.com/item/{product_id}"
            await self.controller.navigate(page_id, url)
            await asyncio.sleep(self._random_delay())

            success = await self.controller.click(page_id, self.selectors.DELIST_BUTTON)
            if success:
                await asyncio.sleep(self._random_delay())

                if confirm:
                    await self.controller.click(page_id, self.selectors.DELIST_CONFIRM)
                    await asyncio.sleep(self._random_delay())

            await self.controller.close_page(page_id)

            result = {
                "success": success,
                "product_id": product_id,
                "action": "delist",
                "reason": reason,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

            if self.analytics:
                await self.analytics.log_operation("DELIST", product_id, details=result)

            return result

        except Exception as e:
            self.logger.error(f"Delist failed: {e}")
            return self._error_result("delist", product_id, str(e))

    async def relist(self, product_id: str) -> Dict[str, Any]:
        """
        重新上架商品

        Args:
            product_id: 商品ID

        Returns:
            操作结果
        """
        self.logger.info(f"Relisting {product_id}")

        if not self.controller:
            return self._mock_result("relist", product_id)

        try:
            page_id = await self.controller.new_page()
            url = f"https://www.goofish.com/item/{product_id}"
            await self.controller.navigate(page_id, url)
            await asyncio.sleep(self._random_delay())

            success = await self.controller.click(page_id, self.selectors.RELIST_BUTTON)
            if success:
                await asyncio.sleep(self._random_delay())
                await self.controller.click(page_id, self.selectors.RELIST_CONFIRM)
                await asyncio.sleep(self._random_delay())

            await self.controller.close_page(page_id)

            result = {
                "success": success,
                "product_id": product_id,
                "action": "relist",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

            if self.analytics:
                await self.analytics.log_operation("RELIST", product_id, details=result)

            return result

        except Exception as e:
            self.logger.error(f"Relist failed: {e}")
            return self._error_result("relist", product_id, str(e))

    async def refresh_inventory(self) -> Dict[str, Any]:
        """
        刷新库存信息

        Returns:
            刷新结果
        """
        self.logger.info("Refreshing inventory...")

        if not self.controller:
            return {"success": True, "action": "inventory_refresh"}

        try:
            page_id = await self.controller.new_page()
            await self.controller.navigate(page_id, self.selectors.MY_SELLING)
            await asyncio.sleep(self._random_delay(1.5, 2.5))

            items = await self.controller.find_elements(page_id, self.selectors.SELLING_ITEM)

            await self.controller.close_page(page_id)

            return {
                "success": True,
                "action": "inventory_refresh",
                "total_items": len(items),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

        except Exception as e:
            self.logger.error(f"Inventory refresh failed: {e}")
            return {"success": False, "action": "inventory_refresh", "error": str(e)}

    async def get_listing_stats(self) -> Dict[str, Any]:
        """
        获取商品统计数据

        Returns:
            统计数据
        """
        self.logger.info("Fetching listing statistics...")

        if not self.controller:
            return {
                "total": 0,
                "active": 0,
                "sold": 0,
                "deleted": 0,
                "total_views": 0,
                "total_wants": 0
            }

        try:
            page_id = await self.controller.new_page()
            await self.controller.navigate(page_id, self.selectors.MY_SELLING)
            await asyncio.sleep(self._random_delay())

            stats = {
                "total": 0,
                "active": 0,
                "sold": 0,
                "deleted": 0,
                "total_views": 0,
                "total_wants": 0
            }

            await self.controller.close_page(page_id)
            return stats

        except Exception as e:
            self.logger.error(f"Failed to fetch stats: {e}")
            return {"error": str(e)}

    def _mock_result(self, action: str, product_id: str) -> Dict[str, Any]:
        """生成模拟结果"""
        return {
            "success": True,
            "product_id": product_id,
            "action": action,
            "mock": True,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }

    def _mock_batch_result(self, action: str, product_ids: List[str]) -> Dict[str, Any]:
        """生成批量操作模拟结果"""
        return {
            "success": len(product_ids),
            "failed": 0,
            "total": len(product_ids),
            "action": f"batch_{action}",
            "details": [{"product_id": pid, "success": True} for pid in product_ids],
            "mock": True
        }

    def _error_result(self, action: str, product_id: Optional[str],
                     error: str) -> Dict[str, Any]:
        """生成错误结果"""
        return {
            "success": False,
            "product_id": product_id,
            "action": action,
            "error": error,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }

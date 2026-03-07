from __future__ import annotations

import pytest

from src.modules.interfaces import (
    IAccountsService,
    IAnalyticsService,
    IContentService,
    IListingService,
    IMediaService,
    IMonitorService,
    IOperationsService,
    ISchedulerService,
)


class ConcreteListingService(IListingService):
    async def create_listing(self, listing, account_id=None):
        return {"ok": True}

    async def batch_create_listings(self, listings, account_id=None, delay_range=(5, 10)):
        return [{"ok": True}]

    async def update_listing(self, product_id, updates):
        return True

    async def delete_listing(self, product_id):
        return True

    async def get_my_listings(self, limit=50):
        return [{"id": "1"}]


class ConcreteContentService(IContentService):
    def generate_title(self, product_name, features, category="General"):
        return "title"

    def generate_description(self, product_name, condition, reason, tags, extra_info=None):
        return "desc"

    def generate_listing_content(self, product_info):
        return {"title": "t", "description": "d"}

    def optimize_title(self, current_title, category="General"):
        return "optimized"


class ConcreteMediaService(IMediaService):
    def resize_image_for_xianyu(self, image_path, output_path=None):
        return image_path

    def add_watermark(self, image_path, output_path=None, text=None, position="bottom-right"):
        return image_path

    def batch_process_images(self, image_paths, output_dir=None, add_watermark=True):
        return image_paths

    def compress_image(self, image_path, output_path=None, quality=85):
        return image_path

    def validate_image(self, image_path):
        return (True, "")


class ConcreteOperationsService(IOperationsService):
    async def batch_polish(self, max_items=50):
        return {"polished": 0}

    async def batch_update_price(self, updates):
        return {"updated": 0}

    async def batch_delist(self, product_ids, reason=""):
        return {"delisted": 0}

    async def get_product_stats(self, product_id):
        return {"views": 0}


class ConcreteAnalyticsService(IAnalyticsService):
    async def log_operation(self, operation_type, product_id=None, account_id=None,
                            details=None, status="success", error_message=None):
        return 1

    async def get_dashboard_stats(self):
        return {"total": 0}

    async def get_trend_data(self, metric="views", days=30):
        return [{"day": "2025-01-01", "value": 0}]

    async def export_data(self, data_type="products", format="csv", filepath=None):
        return "/tmp/export.csv"


class ConcreteAccountsService(IAccountsService):
    def get_accounts(self, enabled_only=True, mask_sensitive=True):
        return []

    def get_account(self, account_id, mask_sensitive=True):
        return None

    def get_cookie(self, account_id=None):
        return None

    def set_current_account(self, account_id):
        return True

    def get_current_account(self):
        return None

    def update_account_stats(self, account_id, operation, success=True):
        pass

    def get_account_health(self, account_id):
        return {"score": 100}


class ConcreteSchedulerService(ISchedulerService):
    def create_task(self, task_type, name=None, cron_expression=None, interval=None, params=None):
        return {"id": "t1"}

    async def execute_task(self, task):
        return {"status": "done"}

    async def start(self):
        pass

    async def stop(self):
        pass

    def get_scheduler_status(self):
        return {"running": False}


class ConcreteMonitorService(IMonitorService):
    async def raise_alert(self, alert_type, title, message, source="",
                          details=None, auto_resolve=False):
        return {"id": "a1"}

    async def resolve_alert(self, alert_id):
        return True

    async def get_active_alerts(self, level=None):
        return []

    async def get_alert_summary(self):
        return {"total": 0}


class TestIListingService:
    async def test_create_listing(self):
        svc = ConcreteListingService()
        result = await svc.create_listing({"name": "test"})
        assert result == {"ok": True}

    async def test_batch_create_listings(self):
        svc = ConcreteListingService()
        result = await svc.batch_create_listings([{"name": "test"}])
        assert len(result) == 1

    async def test_update_listing(self):
        svc = ConcreteListingService()
        assert await svc.update_listing("p1", {"price": 100}) is True

    async def test_delete_listing(self):
        svc = ConcreteListingService()
        assert await svc.delete_listing("p1") is True

    async def test_get_my_listings(self):
        svc = ConcreteListingService()
        result = await svc.get_my_listings()
        assert len(result) == 1


class TestIContentService:
    def test_generate_title(self):
        svc = ConcreteContentService()
        assert svc.generate_title("phone", ["new"]) == "title"

    def test_generate_description(self):
        svc = ConcreteContentService()
        assert svc.generate_description("phone", "new", "upgrade", ["tag1"]) == "desc"

    def test_generate_listing_content(self):
        svc = ConcreteContentService()
        result = svc.generate_listing_content({"name": "phone"})
        assert "title" in result

    def test_optimize_title(self):
        svc = ConcreteContentService()
        assert svc.optimize_title("old title") == "optimized"


class TestIMediaService:
    def test_resize_image(self):
        svc = ConcreteMediaService()
        assert svc.resize_image_for_xianyu("/img.jpg") == "/img.jpg"

    def test_add_watermark(self):
        svc = ConcreteMediaService()
        assert svc.add_watermark("/img.jpg") == "/img.jpg"

    def test_batch_process_images(self):
        svc = ConcreteMediaService()
        assert svc.batch_process_images(["/a.jpg"]) == ["/a.jpg"]

    def test_compress_image(self):
        svc = ConcreteMediaService()
        assert svc.compress_image("/img.jpg") == "/img.jpg"

    def test_validate_image(self):
        svc = ConcreteMediaService()
        ok, msg = svc.validate_image("/img.jpg")
        assert ok is True


class TestIOperationsService:
    async def test_batch_polish(self):
        svc = ConcreteOperationsService()
        result = await svc.batch_polish()
        assert "polished" in result

    async def test_batch_update_price(self):
        svc = ConcreteOperationsService()
        result = await svc.batch_update_price([])
        assert "updated" in result

    async def test_batch_delist(self):
        svc = ConcreteOperationsService()
        result = await svc.batch_delist(["p1"])
        assert "delisted" in result

    async def test_get_product_stats(self):
        svc = ConcreteOperationsService()
        result = await svc.get_product_stats("p1")
        assert "views" in result


class TestIAnalyticsService:
    async def test_log_operation(self):
        svc = ConcreteAnalyticsService()
        assert await svc.log_operation("polish") == 1

    async def test_get_dashboard_stats(self):
        svc = ConcreteAnalyticsService()
        result = await svc.get_dashboard_stats()
        assert "total" in result

    async def test_get_trend_data(self):
        svc = ConcreteAnalyticsService()
        result = await svc.get_trend_data()
        assert len(result) == 1

    async def test_export_data(self):
        svc = ConcreteAnalyticsService()
        result = await svc.export_data()
        assert result.endswith(".csv")


class TestIAccountsService:
    def test_get_accounts(self):
        svc = ConcreteAccountsService()
        assert svc.get_accounts() == []

    def test_get_account(self):
        svc = ConcreteAccountsService()
        assert svc.get_account("a1") is None

    def test_get_cookie(self):
        svc = ConcreteAccountsService()
        assert svc.get_cookie() is None

    def test_set_current_account(self):
        svc = ConcreteAccountsService()
        assert svc.set_current_account("a1") is True

    def test_get_current_account(self):
        svc = ConcreteAccountsService()
        assert svc.get_current_account() is None

    def test_update_account_stats(self):
        svc = ConcreteAccountsService()
        svc.update_account_stats("a1", "polish")

    def test_get_account_health(self):
        svc = ConcreteAccountsService()
        result = svc.get_account_health("a1")
        assert "score" in result


class TestISchedulerService:
    def test_create_task(self):
        svc = ConcreteSchedulerService()
        result = svc.create_task("polish")
        assert "id" in result

    async def test_execute_task(self):
        svc = ConcreteSchedulerService()
        result = await svc.execute_task({"id": "t1"})
        assert result["status"] == "done"

    async def test_start(self):
        svc = ConcreteSchedulerService()
        await svc.start()

    async def test_stop(self):
        svc = ConcreteSchedulerService()
        await svc.stop()

    def test_get_scheduler_status(self):
        svc = ConcreteSchedulerService()
        result = svc.get_scheduler_status()
        assert "running" in result


class TestIMonitorService:
    async def test_raise_alert(self):
        svc = ConcreteMonitorService()
        result = await svc.raise_alert("error", "title", "msg")
        assert result["id"] == "a1"

    async def test_resolve_alert(self):
        svc = ConcreteMonitorService()
        assert await svc.resolve_alert("a1") is True

    async def test_get_active_alerts(self):
        svc = ConcreteMonitorService()
        assert await svc.get_active_alerts() == []

    async def test_get_alert_summary(self):
        svc = ConcreteMonitorService()
        result = await svc.get_alert_summary()
        assert "total" in result

"""自动上架编排器。

完整流程:
1. AI 生成标题/描述 (ContentService)
2. 选择模板 + 生成商品图片 (image_generator)
3. 合规检查 (ComplianceGuard)
4. 上传图片到 OSS (OSSUploader)
5. 获取 user_name (OpenPlatformClient.list_authorized_users)
6. 调用闲管家 API 创建商品 (OpenPlatformClient.create_product)

支持两种模式:
- full_auto: 直接发布
- review: 生成预览数据，等待人工确认后再发布
"""

from __future__ import annotations

import time
from typing import Any

from src.core.compliance import get_compliance_guard
from src.core.logger import get_logger
from src.integrations.xianguanjia.open_platform_client import OpenPlatformClient
from src.modules.content.service import ContentService

from .image_generator import generate_product_images, get_available_categories
from .oss_uploader import OSSUploader

logger = get_logger()


class AutoPublishService:
    """自动上架服务。"""

    def __init__(
        self,
        *,
        api_client: OpenPlatformClient | None = None,
        content_service: ContentService | None = None,
        oss_uploader: OSSUploader | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.config = config or {}
        self.api_client = api_client
        self.content_service = content_service or ContentService()
        self.oss_uploader = oss_uploader or OSSUploader(self.config.get("oss"))
        self.compliance = get_compliance_guard()

    async def generate_preview(self, product_config: dict[str, Any]) -> dict[str, Any]:
        """生成上架预览（不实际发布），返回预览数据供前端展示或人工确认。"""
        category = str(product_config.get("category", "exchange")).strip()
        product_name = str(product_config.get("name", "")).strip()
        features = product_config.get("features") or []
        price = product_config.get("price")
        extra_params = product_config.get("template_params") or {}

        content = self.content_service.generate_listing_content({
            "name": product_name or category,
            "features": features,
            "category": category,
            "condition": product_config.get("condition", "全新"),
            "reason": product_config.get("reason", "闲置出"),
            "tags": product_config.get("tags", []),
            "extra_info": product_config.get("extra_info"),
        })

        title = product_config.get("title") or content.get("title", product_name)
        description = product_config.get("description") or content.get("description", "")

        compliance_result = content.get("compliance", {})
        if compliance_result.get("blocked"):
            return {
                "ok": False,
                "step": "compliance",
                "error": compliance_result.get("message", "内容合规检查未通过"),
                "compliance": compliance_result,
            }

        image_params = [{
            "title": title,
            "desc": description[:80] if description else "",
            "badge": extra_params.get("badge", ""),
            "features": features[:6],
            "price": price,
            "footer": extra_params.get("footer", ""),
            **extra_params,
        }]
        extra_images = product_config.get("extra_images") or []
        for ep in extra_images:
            image_params.append(ep if isinstance(ep, dict) else {"title": str(ep)})

        local_images = await generate_product_images(
            category=category,
            params_list=image_params,
        )

        return {
            "ok": True,
            "step": "preview",
            "title": title,
            "description": description,
            "category": category,
            "price": price,
            "local_images": local_images,
            "compliance": compliance_result,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    async def publish(self, product_config: dict[str, Any]) -> dict[str, Any]:
        """执行完整自动上架流程。"""
        if not self.api_client:
            return {"ok": False, "step": "init", "error": "api_client_not_configured"}

        preview = await self.generate_preview(product_config)
        if not preview.get("ok"):
            return preview

        rate_check = await self.compliance.evaluate_publish_rate(
            f"auto_publish:{product_config.get('account_id', 'global')}"
        )
        if rate_check.get("blocked"):
            return {
                "ok": False,
                "step": "rate_limit",
                "error": rate_check.get("message", "发布频率限制"),
            }

        local_images = preview.get("local_images", [])
        if not local_images:
            return {"ok": False, "step": "image_gen", "error": "没有生成图片"}

        if not self.oss_uploader.configured:
            return {"ok": False, "step": "oss_upload", "error": "OSS 未配置"}

        image_urls = self.oss_uploader.upload_batch(local_images)
        if not image_urls:
            return {"ok": False, "step": "oss_upload", "error": "图片上传失败"}

        user_name = self._get_user_name()

        payload = self._build_create_payload(
            title=preview["title"],
            description=preview["description"],
            price=preview.get("price"),
            image_urls=image_urls,
            user_name=user_name,
            extra=product_config.get("api_payload"),
        )

        response = self.api_client.create_product(payload)
        if not response.ok:
            return {
                "ok": False,
                "step": "api_create",
                "error": response.error_message or "商品创建失败",
                "api_response": response.to_dict() if hasattr(response, "to_dict") else str(response),
            }

        product_data = response.data or {}
        product_id = product_data.get("product_id") or product_data.get("xianyu_product_id")

        return {
            "ok": True,
            "step": "done",
            "product_id": product_id,
            "title": preview["title"],
            "image_urls": image_urls,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    async def publish_from_preview(self, preview_data: dict[str, Any]) -> dict[str, Any]:
        """从预览数据直接发布（人工确认后调用）。"""
        if not self.api_client:
            return {"ok": False, "step": "init", "error": "api_client_not_configured"}

        local_images = preview_data.get("local_images", [])
        if not local_images:
            return {"ok": False, "step": "image_gen", "error": "预览数据中没有图片"}

        if not self.oss_uploader.configured:
            return {"ok": False, "step": "oss_upload", "error": "OSS 未配置"}

        image_urls = self.oss_uploader.upload_batch(local_images)
        if not image_urls:
            return {"ok": False, "step": "oss_upload", "error": "图片上传失败"}

        user_name = self._get_user_name()

        payload = self._build_create_payload(
            title=preview_data.get("title", ""),
            description=preview_data.get("description", ""),
            price=preview_data.get("price"),
            image_urls=image_urls,
            user_name=user_name,
            extra=preview_data.get("api_payload"),
        )

        response = self.api_client.create_product(payload)
        if not response.ok:
            return {
                "ok": False,
                "step": "api_create",
                "error": response.error_message or "商品创建失败",
            }

        product_data = response.data or {}
        return {
            "ok": True,
            "step": "done",
            "product_id": product_data.get("product_id"),
            "title": preview_data.get("title"),
            "image_urls": image_urls,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _get_user_name(self) -> str:
        """从闲管家获取授权用户名。"""
        if not self.api_client:
            return ""
        try:
            resp = self.api_client.list_authorized_users()
            if resp.ok and isinstance(resp.data, list) and resp.data:
                first_user = resp.data[0]
                if isinstance(first_user, dict):
                    return str(first_user.get("user_name") or first_user.get("nick_name") or "")
        except Exception as e:
            logger.warning(f"Failed to get authorized user name: {e}")
        return ""

    @staticmethod
    def _build_create_payload(
        *,
        title: str,
        description: str,
        price: float | int | None,
        image_urls: list[str],
        user_name: str = "",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "title": title,
            "desc": description,
            "images": image_urls,
        }
        if price is not None:
            payload["price"] = int(float(price) * 100)
        if user_name:
            payload["user_name"] = user_name
        if extra and isinstance(extra, dict):
            payload.update(extra)
        return payload

    @staticmethod
    def list_categories() -> list[dict[str, str]]:
        return get_available_categories()

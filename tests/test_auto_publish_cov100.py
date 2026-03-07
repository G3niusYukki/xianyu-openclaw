from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest


@pytest.fixture
def mock_content_service():
    svc = MagicMock()
    svc.generate_listing_content.return_value = {
        "title": "Generated Title",
        "description": "Generated Description",
        "compliance": {},
    }
    return svc


@pytest.fixture
def mock_oss_uploader():
    uploader = MagicMock()
    uploader.configured = True
    uploader.upload_batch.return_value = ["https://oss.example.com/img1.png"]
    return uploader


@pytest.fixture
def mock_api_client():
    client = MagicMock()
    resp = MagicMock()
    resp.ok = True
    resp.data = {"product_id": "prod_123"}
    resp.error_message = None
    client.create_product.return_value = resp
    client.list_authorized_users.return_value = MagicMock(
        ok=True,
        data=[{"user_name": "test_user", "nick_name": "test_nick"}],
    )
    return client


@pytest.fixture
def mock_compliance():
    guard = MagicMock()
    guard.evaluate_publish_rate = AsyncMock(return_value={})
    return guard


@pytest.fixture
def auto_publish_service(mock_content_service, mock_oss_uploader, mock_api_client, mock_compliance):
    with patch("src.modules.listing.auto_publish.get_compliance_guard", return_value=mock_compliance), \
         patch("src.modules.listing.auto_publish.ContentService", return_value=mock_content_service), \
         patch("src.modules.listing.auto_publish.OSSUploader", return_value=mock_oss_uploader):
        from src.modules.listing.auto_publish import AutoPublishService
        svc = AutoPublishService(
            api_client=mock_api_client,
            content_service=mock_content_service,
            oss_uploader=mock_oss_uploader,
            config={"oss": {}},
        )
    return svc


class TestAutoPublishServiceInit:
    def test_init_defaults(self):
        with patch("src.modules.listing.auto_publish.get_compliance_guard"), \
             patch("src.modules.listing.auto_publish.ContentService") as MockCS, \
             patch("src.modules.listing.auto_publish.OSSUploader") as MockOSS:
            from src.modules.listing.auto_publish import AutoPublishService
            svc = AutoPublishService()
            assert svc.config == {}
            assert svc.api_client is None
            MockCS.assert_called_once()
            MockOSS.assert_called_once_with(None)

    def test_init_with_config(self):
        with patch("src.modules.listing.auto_publish.get_compliance_guard"), \
             patch("src.modules.listing.auto_publish.ContentService"), \
             patch("src.modules.listing.auto_publish.OSSUploader") as MockOSS:
            from src.modules.listing.auto_publish import AutoPublishService
            cfg = {"oss": {"bucket": "test"}}
            svc = AutoPublishService(config=cfg)
            MockOSS.assert_called_once_with({"bucket": "test"})


class TestGeneratePreview:
    @pytest.mark.asyncio
    async def test_basic_preview(self, auto_publish_service, mock_content_service):
        with patch("src.modules.listing.auto_publish.generate_product_images", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = ["/tmp/img1.png"]
            result = await auto_publish_service.generate_preview({
                "category": "exchange",
                "name": "Test Product",
                "features": ["feat1", "feat2"],
                "price": 99.9,
            })
        assert result["ok"] is True
        assert result["step"] == "preview"
        assert result["title"] == "Generated Title"
        assert result["price"] == 99.9

    @pytest.mark.asyncio
    async def test_preview_compliance_blocked(self, auto_publish_service, mock_content_service):
        mock_content_service.generate_listing_content.return_value = {
            "title": "T",
            "description": "D",
            "compliance": {"blocked": True, "message": "违规"},
        }
        result = await auto_publish_service.generate_preview({"name": "bad"})
        assert result["ok"] is False
        assert result["step"] == "compliance"
        assert "违规" in result["error"]

    @pytest.mark.asyncio
    async def test_preview_with_extra_images_dict(self, auto_publish_service):
        with patch("src.modules.listing.auto_publish.generate_product_images", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = ["/tmp/img1.png"]
            result = await auto_publish_service.generate_preview({
                "extra_images": [{"title": "extra"}, "string_extra"],
                "template_params": {"badge": "HOT", "footer": "Limited"},
            })
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_preview_uses_product_config_title(self, auto_publish_service, mock_content_service):
        mock_content_service.generate_listing_content.return_value = {
            "compliance": {},
        }
        with patch("src.modules.listing.auto_publish.generate_product_images", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = ["/tmp/img.png"]
            result = await auto_publish_service.generate_preview({
                "title": "Custom Title",
                "description": "Custom Desc",
            })
        assert result["title"] == "Custom Title"
        assert result["description"] == "Custom Desc"


class TestPublish:
    @pytest.mark.asyncio
    async def test_publish_no_api_client(self, auto_publish_service):
        auto_publish_service.api_client = None
        result = await auto_publish_service.publish({})
        assert result["ok"] is False
        assert result["step"] == "init"

    @pytest.mark.asyncio
    async def test_publish_preview_fails(self, auto_publish_service, mock_content_service):
        mock_content_service.generate_listing_content.return_value = {
            "compliance": {"blocked": True, "message": "Blocked"},
        }
        result = await auto_publish_service.publish({"name": "bad"})
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_publish_rate_limited(self, auto_publish_service, mock_compliance):
        mock_compliance.evaluate_publish_rate = AsyncMock(return_value={"blocked": True, "message": "频率限制"})
        with patch("src.modules.listing.auto_publish.generate_product_images", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = ["/tmp/img1.png"]
            result = await auto_publish_service.publish({"name": "test"})
        assert result["ok"] is False
        assert result["step"] == "rate_limit"

    @pytest.mark.asyncio
    async def test_publish_no_images(self, auto_publish_service):
        with patch("src.modules.listing.auto_publish.generate_product_images", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = []
            result = await auto_publish_service.publish({"name": "test"})
        assert result["ok"] is False
        assert result["step"] == "image_gen"

    @pytest.mark.asyncio
    async def test_publish_oss_not_configured(self, auto_publish_service, mock_oss_uploader):
        mock_oss_uploader.configured = False
        with patch("src.modules.listing.auto_publish.generate_product_images", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = ["/tmp/img1.png"]
            result = await auto_publish_service.publish({"name": "test"})
        assert result["ok"] is False
        assert result["step"] == "oss_upload"

    @pytest.mark.asyncio
    async def test_publish_oss_upload_fails(self, auto_publish_service, mock_oss_uploader):
        mock_oss_uploader.upload_batch.return_value = []
        with patch("src.modules.listing.auto_publish.generate_product_images", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = ["/tmp/img1.png"]
            result = await auto_publish_service.publish({"name": "test"})
        assert result["ok"] is False
        assert result["step"] == "oss_upload"

    @pytest.mark.asyncio
    async def test_publish_api_create_fails(self, auto_publish_service, mock_api_client):
        resp = MagicMock()
        resp.ok = False
        resp.error_message = "API Error"
        resp.to_dict.return_value = {"error": "API Error"}
        mock_api_client.create_product.return_value = resp
        with patch("src.modules.listing.auto_publish.generate_product_images", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = ["/tmp/img1.png"]
            result = await auto_publish_service.publish({"name": "test"})
        assert result["ok"] is False
        assert result["step"] == "api_create"

    @pytest.mark.asyncio
    async def test_publish_api_create_fails_no_to_dict(self, auto_publish_service, mock_api_client):
        resp = MagicMock(spec=[])
        resp.ok = False
        resp.error_message = None
        mock_api_client.create_product.return_value = resp
        with patch("src.modules.listing.auto_publish.generate_product_images", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = ["/tmp/img1.png"]
            result = await auto_publish_service.publish({"name": "test"})
        assert result["ok"] is False
        assert "商品创建失败" in result["error"]

    @pytest.mark.asyncio
    async def test_publish_success(self, auto_publish_service):
        with patch("src.modules.listing.auto_publish.generate_product_images", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = ["/tmp/img1.png"]
            result = await auto_publish_service.publish({"name": "test", "price": 50})
        assert result["ok"] is True
        assert result["step"] == "done"
        assert result["product_id"] == "prod_123"


class TestPublishFromPreview:
    @pytest.mark.asyncio
    async def test_no_api_client(self, auto_publish_service):
        auto_publish_service.api_client = None
        result = await auto_publish_service.publish_from_preview({"local_images": ["/img.png"]})
        assert result["ok"] is False
        assert result["step"] == "init"

    @pytest.mark.asyncio
    async def test_no_images(self, auto_publish_service):
        result = await auto_publish_service.publish_from_preview({})
        assert result["ok"] is False
        assert result["step"] == "image_gen"

    @pytest.mark.asyncio
    async def test_oss_not_configured(self, auto_publish_service, mock_oss_uploader):
        mock_oss_uploader.configured = False
        result = await auto_publish_service.publish_from_preview({"local_images": ["/img.png"]})
        assert result["ok"] is False
        assert result["step"] == "oss_upload"

    @pytest.mark.asyncio
    async def test_oss_upload_fails(self, auto_publish_service, mock_oss_uploader):
        mock_oss_uploader.upload_batch.return_value = []
        result = await auto_publish_service.publish_from_preview({"local_images": ["/img.png"]})
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_api_create_fails(self, auto_publish_service, mock_api_client):
        resp = MagicMock()
        resp.ok = False
        resp.error_message = "fail"
        mock_api_client.create_product.return_value = resp
        result = await auto_publish_service.publish_from_preview({"local_images": ["/img.png"]})
        assert result["ok"] is False
        assert result["step"] == "api_create"

    @pytest.mark.asyncio
    async def test_success(self, auto_publish_service):
        result = await auto_publish_service.publish_from_preview({
            "local_images": ["/img.png"],
            "title": "Preview Title",
            "description": "Preview Desc",
            "price": 50,
        })
        assert result["ok"] is True
        assert result["step"] == "done"


class TestGetUserName:
    def test_no_api_client(self, auto_publish_service):
        auto_publish_service.api_client = None
        assert auto_publish_service._get_user_name() == ""

    def test_successful(self, auto_publish_service):
        name = auto_publish_service._get_user_name()
        assert name == "test_user"

    def test_nick_name_fallback(self, auto_publish_service, mock_api_client):
        mock_api_client.list_authorized_users.return_value = MagicMock(
            ok=True, data=[{"nick_name": "nick"}]
        )
        name = auto_publish_service._get_user_name()
        assert name == "nick"

    def test_empty_user_list(self, auto_publish_service, mock_api_client):
        mock_api_client.list_authorized_users.return_value = MagicMock(ok=True, data=[])
        name = auto_publish_service._get_user_name()
        assert name == ""

    def test_not_ok(self, auto_publish_service, mock_api_client):
        mock_api_client.list_authorized_users.return_value = MagicMock(ok=False, data=None)
        name = auto_publish_service._get_user_name()
        assert name == ""

    def test_exception(self, auto_publish_service, mock_api_client):
        mock_api_client.list_authorized_users.side_effect = RuntimeError("conn error")
        name = auto_publish_service._get_user_name()
        assert name == ""

    def test_non_dict_user(self, auto_publish_service, mock_api_client):
        mock_api_client.list_authorized_users.return_value = MagicMock(ok=True, data=["stringuser"])
        name = auto_publish_service._get_user_name()
        assert name == ""


class TestBuildCreatePayload:
    def test_basic(self):
        from src.modules.listing.auto_publish import AutoPublishService
        payload = AutoPublishService._build_create_payload(
            title="T", description="D", price=10.5,
            image_urls=["url1"], user_name="user", extra=None,
        )
        assert payload["title"] == "T"
        assert payload["price"] == 1050
        assert payload["user_name"] == "user"

    def test_no_price_no_user(self):
        from src.modules.listing.auto_publish import AutoPublishService
        payload = AutoPublishService._build_create_payload(
            title="T", description="D", price=None,
            image_urls=["url1"],
        )
        assert "price" not in payload
        assert "user_name" not in payload

    def test_with_extra(self):
        from src.modules.listing.auto_publish import AutoPublishService
        payload = AutoPublishService._build_create_payload(
            title="T", description="D", price=None,
            image_urls=["url1"], extra={"custom": "value"},
        )
        assert payload["custom"] == "value"

    def test_extra_not_dict(self):
        from src.modules.listing.auto_publish import AutoPublishService
        payload = AutoPublishService._build_create_payload(
            title="T", description="D", price=None,
            image_urls=["url1"], extra="not_dict",
        )
        assert "custom" not in payload


class TestListCategories:
    def test_list_categories(self):
        with patch("src.modules.listing.auto_publish.get_available_categories", return_value=[{"id": "exchange", "name": "兑换码"}]):
            from src.modules.listing.auto_publish import AutoPublishService
            cats = AutoPublishService.list_categories()
            assert len(cats) == 1
            assert cats[0]["id"] == "exchange"

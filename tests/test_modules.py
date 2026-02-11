"""
测试脚本
Tests

测试闲鱼自动化工具的核心功能
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_config():
    """测试配置加载"""
    from src.core.config import get_config

    config = get_config()
    assert config.app.get("name") == "xianyu-openclaw"
    print("✅ 配置加载测试通过")


def test_logger():
    """测试日志系统"""
    from src.core.logger import get_logger

    logger = get_logger()
    logger.info("测试日志")
    print("✅ 日志系统测试通过")


def test_models():
    """测试数据模型"""
    from src.modules.listing.models import Listing, ListingImage, PublishResult

    image = ListingImage(local_path="test.jpg")
    assert image.local_path == "test.jpg"

    listing = Listing(
        title="测试商品",
        description="测试描述",
        price=100.0,
        images=["img1.jpg", "img2.jpg"]
    )
    assert listing.title == "测试商品"
    assert len(listing.images) == 2

    result = PublishResult(success=True, product_id="item_123")
    assert result.success is True

    print("✅ 数据模型测试通过")


def test_media_service():
    """测试媒体处理服务"""
    from src.modules.media.service import MediaService

    service = MediaService()
    assert service.max_size == (1500, 1500)
    print("✅ 媒体处理服务测试通过")


def test_content_service():
    """测试内容生成服务"""
    from src.modules.content.service import ContentService

    service = ContentService()

    title = service._default_title("iPhone", ["95新", "国行"])
    assert "iPhone" in title
    assert len(title) <= 30

    description = service._default_description("iPhone", "95新", "换新手机", ["苹果"])
    assert "iPhone" in description

    keywords = service._get_sample_keywords("数码手机")
    assert "自用" in keywords

    print("✅ 内容生成服务测试通过")


def test_operations_selectors():
    """测试运营操作选择器"""
    from src.modules.operations.service import OperationsSelectors

    selectors = OperationsSelectors()
    assert selectors.MY_SELLING == "https://www.goofish.com/my/selling"
    assert "POLISH_BUTTON" in dir(selectors)

    print("✅ 运营操作选择器测试通过")


def test_listing_selectors():
    """测试商品上架选择器"""
    from src.modules.listing.service import XianyuSelectors

    selectors = XianyuSelectors()
    assert selectors.PUBLISH_PAGE == "https://www.goofish.com/publish"
    assert selectors.TITLE_INPUT

    print("✅ 商品上架选择器测试通过")


async def test_async_operations():
    """测试异步操作"""
    from src.modules.operations.service import OperationsService

    service = OperationsService()

    result = await service.polish_listing("test_item")
    assert "success" in result

    result = await service.delist("test_item")
    assert "success" in result

    result = await service.update_price("test_item", 100.0, 150.0)
    assert "success" in result

    print("✅ 异步操作测试通过")


async def test_analytics_service():
    """测试数据分析服务"""
    from src.modules.analytics.service import AnalyticsService

    service = AnalyticsService()

    stats = await service.get_dashboard_stats()
    assert "total_operations" in stats

    print("✅ 数据分析服务测试通过")


async def test_accounts_service():
    """测试账号管理服务"""
    from src.modules.accounts.service import AccountsService

    service = AccountsService()

    accounts = service.get_accounts()
    assert isinstance(accounts, list)

    current = service.get_current_account()
    assert current is None or isinstance(current, dict)

    print("✅ 账号管理服务测试通过")


def run_tests():
    """运行所有测试"""
    print("="*50)
    print("闲鱼自动化工具 - 功能测试")
    print("="*50)

    tests = [
        ("配置加载", test_config),
        ("日志系统", test_logger),
        ("数据模型", test_models),
        ("媒体处理", test_media_service),
        ("内容生成", test_content_service),
        ("运营选择器", test_operations_selectors),
        ("上架选择器", test_listing_selectors),
    ]

    for name, test_func in tests:
        try:
            test_func()
        except Exception as e:
            print(f"❌ {name} 测试失败: {e}")

    async def run_async_tests():
        async_tests = [
            ("异步操作", test_async_operations),
            ("数据分析", test_analytics_service),
            ("账号管理", test_accounts_service),
        ]

        for name, test_func in async_tests:
            try:
                await test_func()
            except Exception as e:
                print(f"❌ {name} 测试失败: {e}")

    asyncio.run(run_async_tests())

    print("\n" + "="*50)
    print("测试完成！")
    print("="*50)


if __name__ == "__main__":
    run_tests()

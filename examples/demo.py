#!/usr/bin/env python3
"""
闲鱼自动化工具 - 示例脚本
Xianyu Automation Tool - Demo Script

演示如何使用闲鱼自动化工具
"""

import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import get_config
from src.core.logger import get_logger
from src.modules.listing.service import ListingService
from src.modules.listing.models import Listing
from src.modules.media.service import MediaService
from src.modules.content.service import ContentService
from src.modules.operations.service import OperationsService
from src.modules.analytics.service import AnalyticsService
from src.modules.accounts.service import AccountsService


async def demo_listing_creation():
    """演示：创建单个商品"""
    print("\n" + "="*50)
    print("演示1: 创建单个商品")
    print("="*50)

    config = get_config()
    logger = get_logger()

    listing = Listing(
        title="iPhone 15 Pro Max 256GB 原色钛金属",
        description="出闲置 iPhone 15 Pro Max，256GB 原色钛金属，成色95新。\n\n2023年官网购买，有发票。\n电池健康度92%，无拆修，功能正常。\n配件齐全：原装盒子、充电器、数据线。\n\n诚心要的私聊，可小刀。",
        price=6999.0,
        original_price=8999.0,
        category="数码手机",
        images=["data/raw/iphone1.jpg", "data/raw/iphone2.jpg"],
        tags=["苹果", "iPhone", "95新", "国行"]
    )

    listing_service = ListingService()
    result = await listing_service.create_listing(listing)

    print(f"\n发布结果:")
    print(f"  成功: {result.success}")
    print(f"  商品ID: {result.product_id}")
    print(f"  商品链接: {result.product_url}")

    if result.error_message:
        print(f"  错误: {result.error_message}")


async def demo_batch_publish():
    """演示：批量发布商品"""
    print("\n" + "="*50)
    print("演示2: 批量发布商品")
    print("="*50)

    listings = [
        Listing(
            title="MacBook Pro 14寸 M3",
            description="出MacBook Pro，2024款，M3芯片，16GB内存，512GB SSD。",
            price=12000.0,
            category="电脑办公",
            images=["data/raw/macbook1.jpg"],
            tags=["苹果", "MacBook", "95新"]
        ),
        Listing(
            title="AirPods Pro 第二代",
            description="出AirPods Pro 2，USB-C接口，成色99新。",
            price=1500.0,
            category="数码手机",
            images=["data/raw/airpods.jpg"],
            tags=["苹果", "AirPods", "全新"]
        ),
    ]

    listing_service = ListingService()
    results = await listing_service.batch_create_listings(listings)

    print(f"\n批量发布结果:")
    print(f"  总数: {len(results)}")
    print(f"  成功: {sum(1 for r in results if r.success)}")
    print(f"  失败: {sum(1 for r in results if not r.success)}")


async def demo_content_generation():
    """演示：AI内容生成"""
    print("\n" + "="*50)
    print("演示2: AI内容生成")
    print("="*50)

    content_service = ContentService()

    print("\n生成标题...")
    title = content_service.generate_title(
        product_name="iPhone 15",
        features=["256GB", "蓝色", "国行", "电池90%"],
        category="数码手机"
    )
    print(f"  标题: {title}")

    print("\n生成描述...")
    description = content_service.generate_description(
        product_name="iPhone 15",
        condition="95新",
        reason="换新手机",
        tags=["苹果", "5G", "国行"]
    )
    print(f"  描述: {description[:100]}...")

    print("\n生成关键词...")
    keywords = content_service.generate_seo_keywords("iPhone 15", "数码手机")
    print(f"  关键词: {keywords}")


async def demo_media_processing():
    """演示：媒体处理"""
    print("\n" + "="*50)
    print("演示3: 媒体处理")
    print("="*50)

    media_service = MediaService()

    images = ["data/raw/sample1.jpg", "data/raw/sample2.jpg"]
    processed = media_service.batch_process_images(images)

    print(f"\n处理图片数: {len(processed)}")
    for i, path in enumerate(processed):
        print(f"  {i+1}. {path}")


async def demo_operations():
    """演示：运营操作"""
    print("\n" + "="*50)
    print("演示4: 运营操作")
    print("="*50)

    operations_service = OperationsService()

    print("\n擦亮单个商品...")
    result = await operations_service.polish_listing("item_123456")
    print(f"  成功: {result.get('success')}")

    print("\n批量擦亮...")
    result = await operations_service.batch_polish(max_items=10)
    print(f"  擦亮数: {result.get('success')}")

    print("\n更新价格...")
    result = await operations_service.update_price("item_123456", 5999.0, 6999.0)
    print(f"  成功: {result.get('success')}")


async def demo_data_analytics():
    """演示：数据分析"""
    print("\n" + "="*50)
    print("演示5: 数据分析")
    print("="*50)

    analytics = AnalyticsService()

    print("\n查询仪表盘数据...")
    stats = await analytics.get_dashboard_stats()
    print(f"  总操作数: {stats.get('total_operations', 0)}")
    print(f"  今日操作: {stats.get('today_operations', 0)}")
    print(f"  总商品数: {stats.get('total_products', 0)}")
    print(f"  在售商品: {stats.get('active_products', 0)}")


async def demo_accounts():
    """演示：账号管理"""
    print("\n" + "="*50)
    print("演示6: 账号管理")
    print("="*50)

    accounts_service = AccountsService()

    print("\n获取所有账号...")
    accounts = accounts_service.get_accounts()
    print(f"  账号数: {len(accounts)}")
    for acc in accounts:
        print(f"    - {acc.get('name')}: {acc.get('id')}")

    print("\n获取当前账号...")
    current = accounts_service.get_current_account()
    if current:
        print(f"  当前账号: {current.get('name')}")


async def main():
    """主函数"""
    print("="*50)
    print("闲鱼自动化工具 - 示例演示")
    print("="*50)

    await demo_content_generation()
    await demo_media_processing()
    await demo_data_analytics()
    await demo_accounts()

    print("\n" + "="*50)
    print("演示完成！")
    print("="*50)
    print("\n提示：浏览器自动化功能需要:")
    print("  1. OpenClaw服务正在运行")
    print("  2. 正确配置Cookie信息")
    print("  3. 使用demo_browser.py运行浏览器自动化演示")


if __name__ == "__main__":
    asyncio.run(main())

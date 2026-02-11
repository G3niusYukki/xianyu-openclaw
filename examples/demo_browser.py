#!/usr/bin/env python3
"""
闲鱼自动化工具 - 浏览器自动化演示
Xianyu Automation Tool - Browser Automation Demo

演示完整的浏览器自动化流程
"""

import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.logger import get_logger
from src.core.openclaw_controller import OpenClawController
from src.modules.listing.service import ListingService
from src.modules.listing.models import Listing
from src.modules.operations.service import OperationsService
from src.modules.analytics.service import AnalyticsService


async def demo_browser_connection():
    """演示：连接OpenClaw浏览器"""
    print("\n" + "="*50)
    print("演示1: 连接OpenClaw浏览器")
    print("="*50)

    controller = OpenClawController()

    print("\n正在连接OpenClaw...")
    connected = await controller.connect()

    if connected:
        print("✅ 连接成功！")

        page_id = await controller.new_page()
        print(f"✅ 创建页面成功: {page_id}")

        await controller.close_page(page_id)
        await controller.disconnect()
        print("✅ 已断开连接")
    else:
        print("❌ 连接失败，请确保OpenClaw服务正在运行")

    return connected


async def demo_publish_flow():
    """演示：完整发布流程"""
    print("\n" + "="*50)
    print("演示2: 完整商品发布流程")
    print("="*50)

    controller = OpenClawController()
    analytics = AnalyticsService()

    connected = await controller.connect()
    if not connected:
        print("❌ 无法连接OpenClaw")
        return False

    listing_service = ListingService(controller=controller, analytics=analytics)

    listing = Listing(
        title="测试商品 - iPhone 15 Pro",
        description="这是一条测试商品的描述。\n成色95新，功能正常。\n诚心要的私聊。",
        price=5999.0,
        category="数码手机",
        images=[],  # 添加实际图片路径
        tags=["测试", "iPhone", "95新"]
    )

    print("\n开始发布流程...")
    result = await listing_service.create_listing(listing)

    print(f"\n发布结果:")
    print(f"  成功: {result.success}")
    print(f"  商品ID: {result.product_id}")
    print(f"  商品链接: {result.product_url}")

    if result.error_message:
        print(f"  错误信息: {result.error_message}")

    await controller.disconnect()
    return result.success


async def demo_polish_flow():
    """演示：擦亮流程"""
    print("\n" + "="*50)
    print("演示3: 商品擦亮流程")
    print("="*50)

    controller = OpenClawController()
    analytics = AnalyticsService()

    connected = await controller.connect()
    if not connected:
        print("❌ 无法连接OpenClaw")
        return False

    operations_service = OperationsService(
        controller=controller,
        analytics=analytics
    )

    print("\n擦亮单个商品...")
    result = await operations_service.polish_listing("item_123456")
    print(f"  成功: {result.get('success')}")

    print("\n批量擦亮（模拟）...")
    batch_result = await operations_service.batch_polish(max_items=5)
    print(f"  擦亮数量: {batch_result.get('success')}/{batch_result.get('total')}")

    await controller.disconnect()
    return result.get('success')


async def demo_price_update():
    """演示：价格更新流程"""
    print("\n" + "="*50)
    print("演示4: 价格更新流程")
    print("="*50)

    controller = OpenClawController()

    connected = await controller.connect()
    if not connected:
        print("❌ 无法连接OpenClaw")
        return False

    operations_service = OperationsService(controller=controller)

    print("\n更新商品价格...")
    result = await operations_service.update_price(
        product_id="item_123456",
        new_price=5499.0,
        original_price=5999.0
    )
    print(f"  成功: {result.get('success')}")
    if result.get('success'):
        print(f"  价格变更: {result.get('old_price')} -> {result.get('new_price')}")

    await controller.disconnect()
    return result.get('success')


async def demo_navigation():
    """演示：页面导航"""
    print("\n" + "="*50)
    print("演示5: 页面导航操作")
    print("="*50)

    controller = OpenClawController()

    connected = await controller.connect()
    if not connected:
        print("❌ 无法连接OpenClaw")
        return False

    page_id = await controller.new_page()

    print("\n导航到闲鱼首页...")
    await controller.navigate(page_id, "https://www.goofish.com")
    await asyncio.sleep(1)
    print("✅ 导航成功")

    print("\n截图...")
    await controller.take_screenshot(page_id, "logs/homepage.png")
    print("✅ 截图已保存到 logs/homepage.png")

    print("\n执行JavaScript...")
    title = await controller.execute_script(page_id, "document.title")
    print(f"  页面标题: {title}")

    await controller.close_page(page_id)
    await controller.disconnect()

    return True


async def demo_element_operations():
    """演示：元素操作"""
    print("\n" + "="*50)
    print("演示6: 页面元素操作")
    print("="*50)

    controller = OpenClawController()

    connected = await controller.connect()
    if not connected:
        print("❌ 无法连接OpenClaw")
        return False

    page_id = await controller.new_page()
    await controller.navigate(page_id, "https://www.goofish.com")
    await asyncio.sleep(2)

    print("\n查找元素...")
    elements = await controller.find_elements(page_id, "a")
    print(f"  找到 {len(elements)} 个链接")

    print("\n查找单个元素...")
    element = await controller.find_element(page_id, "input[type='search']")
    if element:
        print("  ✅ 找到搜索框")
    else:
        print("  ⚠️ 未找到搜索框")

    await controller.close_page(page_id)
    await controller.disconnect()

    return True


async def main():
    """主函数"""
    print("="*60)
    print("闲鱼自动化工具 - 浏览器自动化演示")
    print("="*60)
    print("\n注意：需要OpenClaw服务正在运行才能进行浏览器自动化演示")
    print("启动OpenClaw: openclaw gateway --port 18789\n")

    demos = [
        ("连接测试", demo_browser_connection),
        ("发布流程", demo_publish_flow),
        ("擦亮流程", demo_polish_flow),
        ("价格更新", demo_price_update),
        ("页面导航", demo_navigation),
        ("元素操作", demo_element_operations),
    ]

    results = []

    for name, demo_func in demos:
        try:
            result = await demo_func()
            results.append((name, "✅ 成功" if result else "❌ 失败"))
        except Exception as e:
            print(f"\n演示出错: {e}")
            results.append((name, f"❌ 错误: {str(e)[:30]}"))

    print("\n" + "="*60)
    print("演示结果汇总")
    print("="*60)
    for name, status in results:
        print(f"  {name}: {status}")

    print("\n" + "="*60)


if __name__ == "__main__":
    asyncio.run(main())

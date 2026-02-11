#!/usr/bin/env python3
"""
数据分析功能演示
Analytics Demo Script

演示数据分析与报表功能
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def demo_dashboard():
    """演示仪表盘"""
    print("\n" + "="*50)
    print("演示1: 运营仪表盘")
    print("="*50)

    from src.modules.analytics.service import AnalyticsService
    from src.modules.analytics.visualization import DataVisualizer

    service = AnalyticsService()
    visualizer = DataVisualizer()

    stats = await service.get_dashboard_stats()
    print("\n📊 运营数据:")
    print(f"  总操作数: {stats.get('total_operations', 0)}")
    print(f"  今日操作: {stats.get('today_operations', 0)}")
    print(f"  在售商品: {stats.get('active_products', 0)}")
    print(f"  已售出: {stats.get('sold_products', 0)}")
    print(f"  总营收: {stats.get('total_revenue', 0):.2f}元")

    chart = visualizer.generate_metrics_dashboard()
    print(f"\n{chart}")


async def demo_reports():
    """演示报表生成"""
    print("\n" + "="*50)
    print("演示2: 报表生成")
    print("="*50)

    from src.modules.analytics.report_generator import ReportGenerator, ReportFormatter

    generator = ReportGenerator()

    print("\n📅 生成日报...")
    daily_report = await generator.generate_daily_report()
    print(f"  报表类型: {daily_report['report_type']}")
    print(f"  日期: {daily_report['date']}")
    print(f"  摘要: {daily_report['summary']}")

    print("\n📈 生成周报...")
    weekly_report = await generator.generate_weekly_report()
    print(f"  报表类型: {weekly_report['report_type']}")
    print(f"  周期: {weekly_report['period']['start']} - {weekly_report['period']['end']}")


async def demo_trends():
    """演示趋势分析"""
    print("\n" + "="*50)
    print("演示3: 趋势分析")
    print("="*50)

    from src.modules.analytics.service import AnalyticsService
    from src.modules.analytics.visualization import DataVisualizer

    service = AnalyticsService()
    visualizer = DataVisualizer()

    print("\n📈 浏览量趋势...")
    trend_data = await service.get_trend_data("views", 30)
    print(f"  数据点数: {len(trend_data)}")

    if trend_data:
        chart = visualizer.generate_line_chart(
            trend_data[-14:],
            "date", "value", "Views Trend (Last 14 Days)"
        )
        print(f"\n{chart}")


async def demo_performance():
    """演示商品表现"""
    print("\n" + "="*50)
    print("演示4: 商品表现排名")
    print("="*50)

    from src.modules.analytics.service import AnalyticsService
    from src.modules.analytics.visualization import DataVisualizer

    service = AnalyticsService()
    visualizer = DataVisualizer()

    print("\n🏆 Top 10 商品...")
    performance = await service.get_product_performance(30)
    print(f"  获取到 {len(performance)} 个商品")

    if performance:
        chart = visualizer.generate_bar_chart(
            performance[:10],
            "product_id", "total_wants", "Top Products by Wants"
        )
        print(f"\n{chart}")


async def demo_export():
    """演示数据导出"""
    print("\n" + "="*50)
    print("演示5: 数据导出")
    print("="*50)

    from src.modules.analytics.service import AnalyticsService

    service = AnalyticsService()

    print("\n📤 导出商品数据 (CSV)...")
    filepath = await service.export_data("products", "csv")
    print(f"  已导出: {filepath}")

    print("\n📤 导出日志数据 (JSON)...")
    filepath = await service.export_data("logs", "json")
    print(f"  已导出: {filepath}")


async def demo_charts():
    """演示图表生成"""
    print("\n" + "="*50)
    print("演示6: 图表生成")
    print("="*50)

    from src.modules.analytics.visualization import DataVisualizer, ChartExporter

    visualizer = DataVisualizer()

    sample_data = [
        {"label": "周一", "value": 120},
        {"label": "周二", "value": 150},
        {"label": "周三", "value": 180},
        {"label": "周四", "value": 140},
        {"label": "周五", "value": 200},
        {"label": "周六", "value": 250},
        {"label": "周日", "value": 220},
    ]

    print("\n📊 柱状图示例:")
    chart = visualizer.generate_bar_chart(
        sample_data, "label", "value", "Weekly Views"
    )
    print(chart)

    print("\n📈 折线图示例:")
    line_data = [
        {"date": f"2024-01-{i+1:02d}", "value": v["value"]}
        for i, v in enumerate(sample_data)
    ]
    chart = visualizer.generate_line_chart(
        line_data, "date", "value", "Weekly Trend"
    )
    print(chart)


async def main():
    """主函数"""
    print("="*60)
    print("闲鱼自动化工具 - 数据分析功能演示")
    print("="*60)

    demos = [
        ("运营仪表盘", demo_dashboard),
        ("报表生成", demo_reports),
        ("趋势分析", demo_trends),
        ("商品表现", demo_performance),
        ("数据导出", demo_export),
        ("图表生成", demo_charts),
    ]

    for name, demo_func in demos:
        try:
            await demo_func()
        except Exception as e:
            print(f"\n❌ {name} 演示失败: {e}")

    print("\n" + "="*60)
    print("演示完成！")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())

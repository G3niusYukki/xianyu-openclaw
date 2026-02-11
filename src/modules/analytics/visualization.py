"""
数据可视化
Data Visualization

提供数据图表生成功能
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.modules.analytics.service import AnalyticsService
from src.core.logger import get_logger


class DataVisualizer:
    """
    数据可视化器

    生成数据图表（ASCII/文本格式）
    """

    def __init__(self):
        self.logger = get_logger()
        self.analytics = AnalyticsService()

    def generate_bar_chart(self, data: List[Dict], label_key: str,
                          value_key: str, title: str = "",
                          max_width: int = 50) -> str:
        """
        生成柱状图（ASCII）

        Args:
            data: 数据列表
            label_key: 标签字段
            value_key: 数值字段
            title: 图表标题
            max_width: 最大宽度

        Returns:
            ASCII图表字符串
        """
        if not data:
            return "No data available"

        max_value = max(d.get(value_key, 0) for d in data)
        if max_value == 0:
            return "No data to display"

        lines = []

        if title:
            lines.append(f"📊 {title}")
            lines.append("-" * len(title))

        for item in data:
            label = str(item.get(label_key, ""))[:15]
            value = item.get(value_key, 0)
            bar_length = int(value / max_value * max_width)
            bar = "█" * bar_length
            lines.append(f"{label:15} │ {bar} {value}")

        return "\n".join(lines)

    def generate_line_chart(self, data: List[Dict], label_key: str,
                           value_key: str, title: str = "") -> str:
        """
        生成折线图（ASCII）

        Args:
            data: 数据列表
            label_key: X轴标签字段
            value_key: Y轴数值字段
            title: 图表标题

        Returns:
            ASCII图表字符串
        """
        if not data or len(data) < 2:
            return "Need at least 2 data points"

        values = [d.get(value_key, 0) for d in data]
        min_val = min(values)
        max_val = max(values)

        if max_val == min_val:
            return "No variation in data"

        lines = []

        if title:
            lines.append(f"📈 {title}")
            lines.append("-" * len(title))

        height = 10
        for i, (item, value) in enumerate(zip(data, values)):
            label = str(item.get(label_key, ""))[:10]
            normalized = (value - min_val) / (max_val - min_val)
            pos = int(normalized * height)
            line = " " * pos + "●" + "─" * (height - pos) + f" {label} ({value})"
            lines.append(line)

        return "\n".join(lines)

    def generate_metrics_dashboard(self) -> str:
        """
        生成指标仪表盘

        Returns:
            ASCII仪表盘
        """
        lines = ["=" * 50]
        lines.append("📊 闲鱼运营仪表盘")
        lines.append("=" * 50)
        lines.append("")

        asyncio.run(self._fill_dashboard(lines))

        lines.append("")
        lines.append("=" * 50)

        return "\n".join(lines)

    async def _fill_dashboard(self, lines: List[str]):
        """填充仪表盘内容"""
        stats = await self.analytics.get_dashboard_stats()

        metrics = [
            ("总操作数", stats.get("total_operations", 0)),
            ("今日操作", stats.get("today_operations", 0)),
            ("在售商品", stats.get("active_products", 0)),
            ("已售出", stats.get("sold_products", 0)),
            ("总营收", f"{stats.get('total_revenue', 0):.2f}元"),
            ("今日浏览", stats.get("today_views", 0)),
            ("今日想要", stats.get("today_wants", 0)),
        ]

        for label, value in metrics:
            label = label[:10]
            value = str(value)
            bar = "█" * min(len(value), 20)
            lines.append(f"{label:10} │ {bar} {value}")

    def generate_weekly_trend(self, weeks: int = 4) -> str:
        """
        生成周趋势图

        Args:
            weeks: 周数

        Returns:
            ASCII图表
        """
        asyncio.run(self._generate_trend_chart())

    async def _generate_trend_chart(self, weeks: int = 4):
        """生成趋势图"""
        trend_data = await self.analytics.get_trend_data("views", weeks * 7)

        if not trend_data:
            return "No trend data available"

        values = [d.get("value", 0) for d in trend_data]
        max_val = max(values) if values else 1

        lines = ["📈 Views Trend (Last 30 days)"]
        lines.append("-" * 40)

        for d, v in zip(trend_data[-14:], values[-14:]):
            date = d.get("date", "")[5:]
            bar_len = int(v / max_val * 20)
            bar = "▓" * bar_len
            lines.append(f"{date} │ {bar} {v}")

        return "\n".join(lines)


class ChartExporter:
    """
    图表导出器

    导出各种格式的报表
    """

    @staticmethod
    async def export_report(report: Dict, format: str = "markdown",
                             filepath: str = None) -> str:
        """
        导出报表

        Args:
            report: 报表数据
            format: 格式 (markdown, json, text)
            filepath: 文件路径

        Returns:
            文件路径
        """
        from src.modules.analytics.report_generator import ReportFormatter

        if not filepath:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"data/report_{report.get('report_type', 'unknown')}_{timestamp}"

        if format == "markdown":
            content = ReportFormatter.to_markdown(report)
            filepath += ".md"
        elif format == "json":
            import json
            content = json.dumps(report, ensure_ascii=False, indent=2)
            filepath += ".json"
        else:
            content = str(report)
            filepath += ".txt"

        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        return filepath

    @staticmethod
    async def export_daily_summary(format: str = "text") -> str:
        """
        导出每日摘要

        Args:
            format: 格式

        Returns:
            摘要文本
        """
        analytics = AnalyticsService()
        stats = await analytics.get_dashboard_stats()

        if format == "slack":
            from src.modules.analytics.report_generator import ReportFormatter
            return ReportFormatter.to_slack({"summary": stats, "period": {"date": datetime.now().strftime("%Y-%m-%d")}})

        lines = ["📊 每日运营摘要"]
        lines.append(f"日期: {datetime.now().strftime('%Y-%m-%d')}")
        lines.append("-" * 30)
        lines.append(f"总操作数: {stats.get('total_operations', 0)}")
        lines.append(f"今日操作: {stats.get('today_operations', 0)}")
        lines.append(f"在售商品: {stats.get('active_products', 0)}")
        lines.append(f"已售出: {stats.get('sold_products', 0)}")
        lines.append(f"总营收: {stats.get('total_revenue', 0):.2f}元")

        return "\n".join(lines)

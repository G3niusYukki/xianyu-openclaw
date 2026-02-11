"""
报表生成器
Report Generator

生成运营报表（日报、周报、月报）
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from pathlib import Path

from src.modules.analytics.service import AnalyticsService
from src.core.logger import get_logger


class ReportGenerator:
    """
    报表生成器

    生成各类运营报表
    """

    def __init__(self):
        self.logger = get_logger()
        self.analytics = AnalyticsService()

    async def generate_daily_report(self, date: datetime = None) -> Dict[str, Any]:
        """
        生成日报

        Args:
            date: 日期，默认昨天

        Returns:
            日报数据
        """
        target_date = date or (datetime.now() - timedelta(days=1))
        date_str = target_date.strftime("%Y-%m-%d")

        self.logger.info(f"Generating daily report for {date_str}")

        daily_data = await self.analytics.get_daily_report(target_date)

        report = {
            "report_type": "daily",
            "generated_at": datetime.now().isoformat(),
            "date": date_str,
            "operations": {
                "new_listings": daily_data["new_listings"],
                "polished": daily_data["polished_count"],
                "price_updates": daily_data["price_updates"],
                "delisted": daily_data["delisted_count"],
            },
            "engagement": {
                "views": daily_data["total_views"],
                "wants": daily_data["total_wants"],
                "sales": daily_data["total_sales"],
            },
            "summary": self._generate_summary(daily_data),
        }

        return report

    async def generate_weekly_report(self, end_date: datetime = None) -> Dict[str, Any]:
        """
        生成周报

        Args:
            end_date: 结束日期，默认昨天

        Returns:
            周报数据
        """
        end = end_date or datetime.now()
        start = end - timedelta(days=7)

        self.logger.info(f"Generating weekly report: {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}")

        weekly_data = await self.analytics.get_weekly_report(end)

        report = {
            "report_type": "weekly",
            "generated_at": datetime.now().isoformat(),
            "period": weekly_data["period"],
            "operations": weekly_data["summary"],
            "daily_breakdown": weekly_data["daily_breakdown"],
            "insights": self._generate_weekly_insights(weekly_data),
        }

        return report

    async def generate_monthly_report(self, year: int = None, month: int = None) -> Dict[str, Any]:
        """
        生成月报

        Args:
            year: 年份
            month: 月份

        Returns:
            月报数据
        """
        import calendar

        now = datetime.now()
        target_year = year or now.year
        target_month = month or (now.month - 1 or 12)

        if target_month == 12:
            target_year -= 1

        self.logger.info(f"Generating monthly report: {target_year}-{target_month:02d}")

        monthly_data = await self.analytics.get_monthly_report(target_year, target_month)

        report = {
            "report_type": "monthly",
            "generated_at": datetime.now().isoformat(),
            "period": monthly_data["period"],
            "summary": monthly_data["summary"],
            "category_breakdown": monthly_data["top_categories"],
            "insights": self._generate_monthly_insights(monthly_data),
        }

        return report

    async def generate_product_report(self, product_id: str, days: int = 30) -> Dict[str, Any]:
        """
        生成商品表现报告

        Args:
            product_id: 商品ID
            days: 查询天数

        Returns:
            商品报告
        """
        self.logger.info(f"Generating product report: {product_id}")

        metrics = await self.analytics.get_product_metrics(product_id, days)
        performance = await self.analytics.get_product_performance(days)

        product_data = next((p for p in performance if p.get("product_id") == product_id), None)

        trend_data = await self.analytics.get_trend_data("views", days)

        report = {
            "report_type": "product",
            "generated_at": datetime.now().isoformat(),
            "product_id": product_id,
            "period_days": days,
            "metrics_history": metrics,
            "current_stats": {
                "views": sum(m.get("views", 0) for m in metrics),
                "wants": sum(m.get("wants", 0) for m in metrics),
            },
            "trend": trend_data[:14],
            "ranking": self._calculate_ranking(product_id, performance),
        }

        return report

    async def generate_comparison_report(self, product_ids: List[str],
                                         days: int = 30) -> Dict[str, Any]:
        """
        生成商品对比报告

        Args:
            product_ids: 商品ID列表
            days: 查询天数

        Returns:
            对比报告
        """
        self.logger.info(f"Generating comparison report for {len(product_ids)} products")

        performance = await self.analytics.get_product_performance(days)

        comparison = []
        for pid in product_ids:
            product = next((p for p in performance if p.get("product_id") == pid), None)
            if product:
                comparison.append({
                    "product_id": pid,
                    "title": product.get("title", ""),
                    "price": product.get("price", 0),
                    "views": product.get("total_views", 0),
                    "wants": product.get("total_wants", 0),
                    "status": product.get("status", ""),
                })

        report = {
            "report_type": "comparison",
            "generated_at": datetime.now().isoformat(),
            "products": comparison,
            "ranking": sorted(comparison, key=lambda x: x["wants"], reverse=True),
        }

        return report

    def _generate_summary(self, data: Dict) -> str:
        """生成摘要文本"""
        lines = []

        if data["new_listings"] > 0:
            lines.append(f"发布了 {data['new_listings']} 个新商品")

        if data["polished_count"] > 0:
            lines.append(f"擦亮了 {data['polished_count']} 次商品")

        if data["total_views"] > 0:
            lines.append(f"获得 {data['total_views']} 次浏览")

        if data["total_wants"] > 0:
            lines.append(f"收到 {data['total_wants']} 个想要")

        if data["total_sales"] > 0:
            lines.append(f"成交 {data['total_sales']} 单")

        return "；".join(lines) if lines else "暂无运营数据"

    def _generate_weekly_insights(self, data: Dict) -> Dict[str, Any]:
        """生成周报洞察"""
        summary = data.get("summary", {})

        insights = {
            "highlights": [],
            "recommendations": [],
        }

        if summary.get("total_wants", 0) > 100:
            insights["highlights"].append("本周互动数据表现良好，想要数超过100")

        if summary.get("new_listings", 0) < 3:
            insights["recommendations"].append("建议增加上新频率，提高店铺活跃度")

        if summary.get("polished_count", 0) < 5:
            insights["recommendations"].append("建议定期擦亮商品，提高曝光率")

        return insights

    def _generate_monthly_insights(self, data: Dict) -> Dict[str, Any]:
        """生成月报洞察"""
        summary = data.get("summary", {})

        insights = {
            "highlights": [],
            "recommendations": [],
            "goals_progress": {},
        }

        if summary.get("total_revenue", 0) > 1000:
            insights["highlights"].append(f"本月收入突破 {summary['total_revenue']:.0f} 元")

        if summary.get("total_sold", 0) > 10:
            insights["highlights"].append(f"本月成功售出 {summary['total_sold']} 件商品")

        if data.get("top_categories"):
            top_cat = data["top_categories"][0]
            insights["highlights"].append(f"热销品类: {top_cat.get('category', '')}")

        if not insights["highlights"]:
            insights["recommendations"].append("本月运营数据较低，建议优化商品信息和定价策略")

        return insights

    def _calculate_ranking(self, product_id: str, performance: List[Dict]) -> Dict:
        """计算商品排名"""
        sorted_products = sorted(performance, key=lambda x: x.get("total_wants", 0), reverse=True)

        for i, p in enumerate(sorted_products):
            if p.get("product_id") == product_id:
                return {
                    "rank": i + 1,
                    "total": len(sorted_products),
                    "percentile": round((1 - i / len(sorted_products)) * 100, 1)
                }

        return {"rank": None, "total": len(sorted_products)}


class ReportFormatter:
    """
    报表格式化器

    将报表数据格式化为不同形式
    """

    @staticmethod
    def to_markdown(report: Dict) -> str:
        """转换为Markdown格式"""
        lines = [f"# {report['report_type'].title()} Report"]

        if report.get("generated_at"):
            lines.append(f"\n*Generated: {report['generated_at']}*")

        if report.get("period"):
            period = report["period"]
            if "date" in period:
                lines.append(f"\n**Date:** {period['date']}")
            else:
                lines.append(f"\n**Period:** {period.get('start', '')} to {period.get('end', '')}")

        if report.get("summary"):
            lines.append("\n## Summary")
            for key, value in report["summary"].items():
                if isinstance(value, (int, float)):
                    lines.append(f"- {key.replace('_', ' ').title()}: {value}")

        if report.get("operations"):
            lines.append("\n## Operations")
            for key, value in report["operations"].items():
                lines.append(f"- {key.replace('_', ' ').title()}: {value}")

        return "\n".join(lines)

    @staticmethod
    def to_slack(report: Dict) -> str:
        """转换为Slack格式"""
        lines = [f"📊 *{report['report_type'].title()} Report*"]

        if report.get("period"):
            period = report["period"]
            if "date" in period:
                lines.append(f"📅 {period['date']}")
            else:
                lines.append(f"📅 {period.get('start', '')} - {period.get('end', '')}")

        if report.get("summary"):
            summary = report["summary"]
            if "total_wants" in summary:
                lines.append(f"❤️ 想要: {summary['total_wants']}")
            if "total_views" in summary:
                lines.append(f"👀 浏览: {summary['total_views']}")
            if "total_sales" in summary:
                lines.append(f"💰 成交: {summary['total_sales']}")

        return "\n".join(lines)

"""
闲鱼数据统计技能
Xianyu Metrics Skill

提供商品数据查询和运营报表功能
"""

from openclaw.agent.skill import AgentSkill
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta


class XianyuMetricsSkill(AgentSkill):
    """
    数据统计技能

    查询和管理闲鱼店铺的运营数据
    """

    name = "xianyu-metrics"
    description = "Query and analyze Xianyu listing metrics, operational data, and generate reports"

    async def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        """
        执行数据查询操作

        Args:
            action: 操作类型
            **kwargs: 操作参数
        """
        action_map = {
            "dashboard": self._get_dashboard,
            "product_metrics": self._get_product_metrics,
            "operation_logs": self._get_operation_logs,
            "daily_report": self._get_daily_report,
            "weekly_report": self._get_weekly_report,
            "monthly_report": self._get_monthly_report,
            "product_report": self._get_product_report,
            "comparison": self._compare_products,
            "export": self._export_data,
            "trends": self._get_trends,
            "performance": self._get_performance,
            "cleanup": self._cleanup_data,
        }

        if action in action_map:
            return await action_map[action](kwargs)
        else:
            return {"status": "error", "message": f"Unknown action: {action}"}

    async def _get_dashboard(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取仪表盘数据
        """
        self.log("Fetching dashboard data")

        try:
            from src.modules.analytics.service import AnalyticsService
            from src.modules.analytics.visualization import DataVisualizer

            service = AnalyticsService()
            stats = await service.get_dashboard_stats()

            visualizer = DataVisualizer()
            chart = visualizer.generate_metrics_dashboard()

            return {
                "status": "success",
                "action": "dashboard",
                "data": {
                    "stats": stats,
                    "chart": chart
                }
            }

        except ImportError:
            return self._mock_dashboard()
        except Exception as e:
            self.log(f"Dashboard error: {e}", level="error")
            return {"status": "error", "message": str(e)}

    async def _get_product_metrics(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取商品指标
        """
        product_id = params.get("product_id")
        days = params.get("days", 7)

        if not product_id:
            return {"status": "error", "message": "Product ID required"}

        self.log(f"Fetching metrics for {product_id} ({days} days)")

        try:
            from src.modules.analytics.service import AnalyticsService

            service = AnalyticsService()
            history = await service.get_product_metrics(product_id, days)

            views = sum(h.get("views", 0) for h in history)
            wants = sum(h.get("wants", 0) for h in history)
            inquiries = sum(h.get("inquiries", 0) for h in history)
            sales = sum(h.get("sales", 0) for h in history)

            return {
                "status": "success",
                "action": "product_metrics",
                "product_id": product_id,
                "period_days": days,
                "data": {
                    "total_views": views,
                    "total_wants": wants,
                    "total_inquiries": inquiries,
                    "total_sales": sales,
                    "history": history[-7:]
                }
            }

        except ImportError:
            return self._mock_product_metrics(product_id, days)
        except Exception as e:
            self.log(f"Product metrics error: {e}", level="error")
            return {"status": "error", "message": str(e)}

    async def _get_operation_logs(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取操作日志
        """
        limit = params.get("limit", 100)
        operation_type = params.get("operation_type")

        self.log("Fetching operation logs")

        try:
            from src.modules.analytics.service import AnalyticsService

            service = AnalyticsService()
            logs = await service.get_operation_logs(limit, operation_type)

            return {
                "status": "success",
                "action": "operation_logs",
                "total": len(logs),
                "data": logs[:20]
            }

        except ImportError:
            return {"status": "success", "action": "operation_logs", "total": 0, "data": [], "mock": True}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _get_daily_report(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取日报
        """
        date_str = params.get("date")
        date = datetime.strptime(date_str, "%Y-%m-%d") if date_str else (datetime.now() - timedelta(days=1))

        self.log(f"Generating daily report for {date.strftime('%Y-%m-%d')}")

        try:
            from src.modules.analytics.service import AnalyticsService
            from src.modules.analytics.report_generator import ReportGenerator

            service = AnalyticsService()
            generator = ReportGenerator()

            daily_data = await service.get_daily_report(date)
            report = await generator.generate_daily_report(date)

            return {
                "status": "success",
                "action": "daily_report",
                "date": date.strftime("%Y-%m-%d"),
                "data": daily_data,
                "report": report
            }

        except ImportError:
            return self._mock_report("daily", date.strftime("%Y-%m-%d"))
        except Exception as e:
            self.log(f"Daily report error: {e}", level="error")
            return {"status": "error", "message": str(e)}

    async def _get_weekly_report(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取周报
        """
        end_date = params.get("end_date")
        end = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()

        self.log(f"Generating weekly report")

        try:
            from src.modules.analytics.report_generator import ReportGenerator

            generator = ReportGenerator()
            report = await generator.generate_weekly_report(end)

            return {
                "status": "success",
                "action": "weekly_report",
                "report": report
            }

        except ImportError:
            return {"status": "success", "action": "weekly_report", "mock": True}
        except Exception as e:
            self.log(f"Weekly report error: {e}", level="error")
            return {"status": "error", "message": str(e)}

    async def _get_monthly_report(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取月报
        """
        year = params.get("year", datetime.now().year - 1 if datetime.now().month == 1 else datetime.now().year)
        month = params.get("month", datetime.now().month - 1 or 12)

        self.log(f"Generating monthly report: {year}-{month:02d}")

        try:
            from src.modules.analytics.report_generator import ReportGenerator

            generator = ReportGenerator()
            report = await generator.generate_monthly_report(year, month)

            return {
                "status": "success",
                "action": "monthly_report",
                "report": report
            }

        except ImportError:
            return {"status": "success", "action": "monthly_report", "mock": True}
        except Exception as e:
            self.log(f"Monthly report error: {e}", level="error")
            return {"status": "error", "message": str(e)}

    async def _get_product_report(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取商品表现报告
        """
        product_id = params.get("product_id")
        days = params.get("days", 30)

        if not product_id:
            return {"status": "error", "message": "Product ID required"}

        self.log(f"Generating product report for {product_id}")

        try:
            from src.modules.analytics.report_generator import ReportGenerator

            generator = ReportGenerator()
            report = await generator.generate_product_report(product_id, days)

            return {
                "status": "success",
                "action": "product_report",
                "report": report
            }

        except ImportError:
            return {"status": "success", "action": "product_report", "mock": True}
        except Exception as e:
            self.log(f"Product report error: {e}", level="error")
            return {"status": "error", "message": str(e)}

    async def _compare_products(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        对比多个商品
        """
        products = params.get("products", [])
        days = params.get("days", 30)

        if len(products) < 2:
            return {"status": "error", "message": "At least 2 products required"}

        self.log(f"Comparing {len(products)} products")

        try:
            from src.modules.analytics.report_generator import ReportGenerator

            generator = ReportGenerator()
            report = await generator.generate_comparison_report(products, days)

            return {
                "status": "success",
                "action": "comparison",
                "report": report
            }

        except ImportError:
            return {"status": "success", "action": "comparison", "mock": True}
        except Exception as e:
            self.log(f"Comparison error: {e}", level="error")
            return {"status": "error", "message": str(e)}

    async def _export_data(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        导出数据
        """
        data_type = params.get("data_type", "products")
        format_type = params.get("format", "csv")
        filepath = params.get("filepath")

        self.log(f"Exporting {data_type} as {format_type}")

        try:
            from src.modules.analytics.service import AnalyticsService

            service = AnalyticsService()
            path = await service.export_data(data_type, format_type, filepath)

            return {
                "status": "success",
                "action": "export",
                "filepath": path,
                "format": format_type,
                "data_type": data_type
            }

        except ImportError:
            return {"status": "success", "action": "export", "mock": True}
        except Exception as e:
            self.log(f"Export error: {e}", level="error")
            return {"status": "error", "message": str(e)}

    async def _get_trends(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取趋势数据
        """
        metric = params.get("metric", "views")
        days = params.get("days", 30)

        self.log(f"Fetching {metric} trends for {days} days")

        try:
            from src.modules.analytics.service import AnalyticsService
            from src.modules.analytics.visualization import DataVisualizer

            service = AnalyticsService()
            trend_data = await service.get_trend_data(metric, days)

            visualizer = DataVisualizer()
            chart = visualizer.generate_line_chart(
                trend_data[-14:],
                "date", "value", f"{metric.title()} Trend"
            )

            return {
                "status": "success",
                "action": "trends",
                "metric": metric,
                "period_days": days,
                "data": trend_data,
                "chart": chart
            }

        except ImportError:
            return {"status": "success", "action": "trends", "mock": True}
        except Exception as e:
            self.log(f"Trends error: {e}", level="error")
            return {"status": "error", "message": str(e)}

    async def _get_performance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取商品表现排名
        """
        days = params.get("days", 30)

        self.log(f"Fetching product performance (last {days} days)")

        try:
            from src.modules.analytics.service import AnalyticsService
            from src.modules.analytics.visualization import DataVisualizer

            service = AnalyticsService()
            performance = await service.get_product_performance(days)

            visualizer = DataVisualizer()
            chart = visualizer.generate_bar_chart(
                performance[:10],
                "product_id", "total_wants", "Top Products by Wants"
            )

            return {
                "status": "success",
                "action": "performance",
                "period_days": days,
                "top_products": performance[:10],
                "chart": chart
            }

        except ImportError:
            return {"status": "success", "action": "performance", "mock": True}
        except Exception as e:
            self.log(f"Performance error: {e}", level="error")
            return {"status": "error", "message": str(e)}

    async def _cleanup_data(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        清理旧数据
        """
        days = params.get("days", 90)

        self.log(f"Cleaning up data older than {days} days")

        try:
            from src.modules.analytics.service import AnalyticsService

            service = AnalyticsService()
            result = await service.cleanup_old_data(days)

            return {
                "status": "success",
                "action": "cleanup",
                "deleted": result
            }

        except ImportError:
            return {"status": "success", "action": "cleanup", "mock": True}
        except Exception as e:
            self.log(f"Cleanup error: {e}", level="error")
            return {"status": "error", "message": str(e)}

    def _mock_dashboard(self) -> Dict[str, Any]:
        """生成模拟仪表盘数据"""
        return {
            "status": "success",
            "action": "dashboard",
            "data": {
                "stats": {
                    "total_operations": 0,
                    "today_operations": 0,
                    "total_products": 0,
                    "active_products": 0,
                    "sold_products": 0,
                    "total_revenue": 0,
                },
                "chart": "📊 Dashboard (mock data)"
            },
            "mock": True
        }

    def _mock_product_metrics(self, product_id: str, days: int) -> Dict[str, Any]:
        """生成模拟商品指标"""
        return {
            "status": "success",
            "action": "product_metrics",
            "product_id": product_id,
            "period_days": days,
            "data": {
                "total_views": 0,
                "total_wants": 0,
                "total_inquiries": 0,
                "total_sales": 0,
                "history": []
            },
            "mock": True
        }

    def _mock_report(self, report_type: str, date_str: str) -> Dict[str, Any]:
        """生成模拟报表数据"""
        return {
            "status": "success",
            "action": f"{report_type}_report",
            "date": date_str,
            "data": {},
            "mock": True
        }

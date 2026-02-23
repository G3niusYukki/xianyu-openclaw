"""
数据分析服务
Analytics Service

提供数据存储、查询、分析和报表生成功能
"""

import asyncio
import json
import csv
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict

import aiosqlite

from src.core.config import get_config
from src.core.logger import get_logger


@dataclass
class DateRange:
    """日期范围"""
    start_date: datetime
    end_date: datetime

    def __init__(self, start_date: datetime, end_date: datetime = None):
        self.start_date = start_date
        self.end_date = end_date or datetime.now()


class AnalyticsService:
    """
    数据分析服务

    负责运营数据的采集、存储、分析和报表生成
    """

    def __init__(self, config: Optional[dict] = None):
        """
        初始化分析服务

        Args:
            config: 配置字典
        """
        self.config = config or get_config().database
        self.logger = get_logger()

        db_path = self.config.get("path", "data/agent.db")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path

        self._allowed_metrics = {"views", "wants", "sales", "inquiries"}
        self._allowed_export_types = {"products", "logs", "metrics"}
        self._allowed_formats = {"csv", "json"}
        self._db_timeout = int(self.config.get("timeout", 30))
        self._write_lock = asyncio.Lock()
        self._init_db_sync()

    def _validate_metric(self, metric: str) -> str:
        """
        验证指标类型

        Args:
            metric: 指标类型

        Returns:
            验证后的指标类型

        Raises:
            ValueError: 指标类型不在白名单中
        """
        if metric not in self._allowed_metrics:
            raise ValueError(f"Invalid metric: {metric}. Must be one of {self._allowed_metrics}")
        return metric

    async def _init_db(self) -> None:
        """初始化数据库"""
        async with aiosqlite.connect(self.db_path, timeout=self._db_timeout) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS operation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_type TEXT NOT NULL,
                    product_id TEXT,
                    account_id TEXT,
                    details TEXT,
                    status TEXT,
                    error_message TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS product_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT NOT NULL,
                    product_title TEXT,
                    views INTEGER DEFAULT 0,
                    wants INTEGER DEFAULT 0,
                    inquiries INTEGER DEFAULT 0,
                    sales INTEGER DEFAULT 0,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT UNIQUE,
                    title TEXT,
                    price REAL,
                    cost_price REAL,
                    status TEXT,
                    category TEXT,
                    account_id TEXT,
                    product_url TEXT,
                    views INTEGER DEFAULT 0,
                    wants INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    sold_at DATETIME
                )
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_op_logs_type_time
                ON operation_logs(operation_type, timestamp, account_id)
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_op_logs_time
                ON operation_logs(timestamp)
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_metrics_product_time
                ON product_metrics(product_id, timestamp)
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_products_account
                ON products(account_id)
            """)

            await db.commit()
            self.logger.success("Analytics database initialized")

    def _init_db_sync(self) -> None:
        """同步初始化数据库，确保服务创建后表结构可立即使用"""
        with sqlite3.connect(self.db_path, timeout=self._db_timeout) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS operation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_type TEXT NOT NULL,
                    product_id TEXT,
                    account_id TEXT,
                    details TEXT,
                    status TEXT,
                    error_message TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS product_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT NOT NULL,
                    product_title TEXT,
                    views INTEGER DEFAULT 0,
                    wants INTEGER DEFAULT 0,
                    inquiries INTEGER DEFAULT 0,
                    sales INTEGER DEFAULT 0,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT UNIQUE,
                    title TEXT,
                    price REAL,
                    cost_price REAL,
                    status TEXT,
                    category TEXT,
                    account_id TEXT,
                    product_url TEXT,
                    views INTEGER DEFAULT 0,
                    wants INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    sold_at DATETIME
                )
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_op_logs_type_time
                ON operation_logs(operation_type, timestamp, account_id)
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_op_logs_time
                ON operation_logs(timestamp)
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_metrics_product_time
                ON product_metrics(product_id, timestamp)
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_products_account
                ON products(account_id)
            """)
            db.commit()
        self.logger.success("Analytics database initialized")

    async def log_operation(self, operation_type: str, product_id: Optional[str] = None,
                            account_id: Optional[str] = None, details: Optional[Dict] = None,
                            status: str = "success", error_message: Optional[str] = None) -> int:
        """
        记录操作日志

        Args:
            operation_type: 操作类型
            product_id: 商品ID
            account_id: 账号ID
            details: 详细信息
            status: 状态
            error_message: 错误信息

        Returns:
            日志ID
        """
        async with self._write_lock:
            async with aiosqlite.connect(self.db_path, timeout=self._db_timeout) as db:
                cursor = await db.execute("""
                    INSERT INTO operation_logs
                    (operation_type, product_id, account_id, details, status, error_message)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    operation_type,
                    product_id,
                    account_id,
                    json.dumps(details, ensure_ascii=False) if details else None,
                    status,
                    error_message
                ))
                await db.commit()
                return cursor.lastrowid

    async def record_metrics(self, product_id: str, product_title: Optional[str] = None,
                             views: int = 0, wants: int = 0, inquiries: int = 0,
                             sales: int = 0) -> int:
        """
        记录商品指标

        Args:
            product_id: 商品ID
            product_title: 商品标题
            views: 浏览量
            wants: 想要数
            inquiries: 咨询量
            sales: 成交量

        Returns:
            记录ID
        """
        async with self._write_lock:
            async with aiosqlite.connect(self.db_path, timeout=self._db_timeout) as db:
                cursor = await db.execute("""
                    INSERT INTO product_metrics
                    (product_id, product_title, views, wants, inquiries, sales)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (product_id, product_title, views, wants, inquiries, sales))
                await db.commit()
                return cursor.lastrowid

    async def add_product(self, product_id: str, title: str, price: float,
                          category: str = None, account_id: str = None) -> int:
        """
        添加商品

        Args:
            product_id: 商品ID
            title: 标题
            price: 价格
            category: 分类
            account_id: 账号ID

        Returns:
            商品ID
        """
        async with self._write_lock:
            async with aiosqlite.connect(self.db_path, timeout=self._db_timeout) as db:
                cursor = await db.execute("""
                    INSERT OR REPLACE INTO products
                    (product_id, title, price, category, account_id, status, created_at)
                    VALUES (?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)
                """, (product_id, title, price, category, account_id))
                await db.commit()
                return cursor.lastrowid

    async def update_product_status(self, product_id: str, status: str) -> bool:
        """
        更新商品状态

        Args:
            product_id: 商品ID
            status: 新状态

        Returns:
            是否成功
        """
        async with self._write_lock:
            async with aiosqlite.connect(self.db_path, timeout=self._db_timeout) as db:
                if status == "sold":
                    await db.execute("""
                        UPDATE products SET status = ?, sold_at = CURRENT_TIMESTAMP WHERE product_id = ?
                    """, (status, product_id))
                else:
                    await db.execute("""
                        UPDATE products SET status = ? WHERE product_id = ?
                    """, (status, product_id))
                await db.commit()
                return True

    async def get_operation_logs(self, limit: int = 100,
                                 operation_type: Optional[str] = None,
                                 start_date: Optional[datetime] = None,
                                 end_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        查询操作日志

        Args:
            limit: 返回数量限制
            operation_type: 操作类型过滤
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            日志列表
        """
        async with aiosqlite.connect(self.db_path, timeout=self._db_timeout) as db:
            db.row_factory = aiosqlite.Row

            query = "SELECT * FROM operation_logs WHERE 1=1"
            params = []

            if operation_type:
                query += " AND operation_type = ?"
                params.append(operation_type)

            if start_date:
                query += " AND timestamp >= ?"
                params.append(start_date.isoformat())

            if end_date:
                query += " AND timestamp <= ?"
                params.append(end_date.isoformat())

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

            return [dict(row) for row in rows]

    async def get_product_metrics(self, product_id: str,
                                 days: int = 7) -> List[Dict[str, Any]]:
        """
        获取商品指标历史

        Args:
            product_id: 商品ID
            days: 查询天数

        Returns:
            指标历史列表
        """
        async with aiosqlite.connect(self.db_path, timeout=self._db_timeout) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute("""
                SELECT * FROM product_metrics
                WHERE product_id = ?
                AND timestamp >= datetime('now', ?)
                ORDER BY timestamp ASC
            """, (product_id, f"-{days} days"))

            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_dashboard_stats(self) -> Dict[str, Any]:
        """
        获取仪表盘统计数据

        Returns:
            统计数据字典
        """
        async with aiosqlite.connect(self.db_path, timeout=self._db_timeout) as db:
            db.row_factory = aiosqlite.Row

            total_operations = await db.execute_fetchone(
                "SELECT COUNT(*) as count FROM operation_logs"
            )

            today = datetime.now().strftime("%Y-%m-%d")
            today_operations = await db.execute_fetchone(
                "SELECT COUNT(*) as count FROM operation_logs WHERE date(timestamp) = ?",
                (today,)
            )

            total_products = await db.execute_fetchone(
                "SELECT COUNT(*) as count FROM products"
            )

            active_products = await db.execute_fetchone(
                "SELECT COUNT(*) as count FROM products WHERE status = 'active'"
            )

            sold_products = await db.execute_fetchone(
                "SELECT COUNT(*) as count FROM products WHERE status = 'sold'"
            )

            total_revenue = await db.execute_fetchone(
                "SELECT COALESCE(SUM(price), 0) as total FROM products WHERE status = 'sold'"
            )

            today_start = f"{today} 00:00:00"
            today_metrics = await db.execute_fetchone("""
                SELECT COALESCE(SUM(views), 0) as views, COALESCE(SUM(wants), 0) as wants
                FROM product_metrics WHERE timestamp >= ?
            """, (today_start,))

            return {
                "total_operations": total_operations[0] or 0,
                "today_operations": today_operations[0] or 0,
                "total_products": total_products[0] or 0,
                "active_products": active_products[0] or 0,
                "sold_products": sold_products[0] or 0,
                "total_revenue": round(total_revenue[0] or 0, 2),
                "today_views": today_metrics[0] or 0,
                "today_wants": today_metrics[1] or 0,
            }

    async def get_daily_report(self, date: datetime = None) -> Dict[str, Any]:
        """
        获取日报数据

        Args:
            date: 日期，默认昨天

        Returns:
            日报数据
        """
        target_date = date or (datetime.now() - timedelta(days=1))
        date_str = target_date.strftime("%Y-%m-%d")

        async with aiosqlite.connect(self.db_path, timeout=self._db_timeout) as db:
            db.row_factory = aiosqlite.Row

            day_start = f"{date_str} 00:00:00"
            day_end = f"{date_str} 23:59:59"

            operations = await db.execute_fetchall("""
                SELECT operation_type, COUNT(*) as count
                FROM operation_logs
                WHERE timestamp BETWEEN ? AND ?
                GROUP BY operation_type
            """, (day_start, day_end))

            new_listings = sum(1 for op in operations if op[0] == "PUBLISH")
            polished = sum(op[1] for op in operations if "POLISH" in op[0])
            price_updates = sum(op[1] for op in operations if "PRICE" in op[0])
            delisted = sum(op[1] for op in operations if op[0] == "DELIST")

            metrics = await db.execute_fetchone("""
                SELECT COALESCE(SUM(views), 0) as views,
                       COALESCE(SUM(wants), 0) as wants,
                       COALESCE(SUM(sales), 0) as sales
                FROM product_metrics
                WHERE timestamp BETWEEN ? AND ?
            """, (day_start, day_end))

            return {
                "date": date_str,
                "new_listings": new_listings,
                "polished_count": polished,
                "price_updates": price_updates,
                "delisted_count": delisted,
                "total_views": metrics[0] or 0,
                "total_wants": metrics[1] or 0,
                "total_sales": metrics[2] or 0,
            }

    async def get_weekly_report(self, end_date: datetime = None) -> Dict[str, Any]:
        """
        获取周报数据

        Args:
            end_date: 结束日期，默认昨天

        Returns:
            周报数据
        """
        end = end_date or datetime.now()
        start = end - timedelta(days=7)

        async with aiosqlite.connect(self.db_path, timeout=self._db_timeout) as db:
            db.row_factory = aiosqlite.Row

            week_start = start.strftime("%Y-%m-%d 00:00:00")
            week_end = end.strftime("%Y-%m-%d 23:59:59")

            operations = await db.execute_fetchall("""
                SELECT operation_type, COUNT(*) as count
                FROM operation_logs
                WHERE timestamp BETWEEN ? AND ?
                GROUP BY operation_type
            """, (week_start, week_end))

            new_listings = sum(1 for op in operations if op[0] == "PUBLISH")
            polished = sum(op[1] for op in operations if "POLISH" in op[0])
            price_updates = sum(op[1] for op in operations if "PRICE" in op[0])

            metrics = await db.execute_fetchone("""
                SELECT COALESCE(SUM(views), 0) as views,
                       COALESCE(SUM(wants), 0) as wants,
                       COALESCE(SUM(sales), 0) as sales
                FROM product_metrics
                WHERE timestamp BETWEEN ? AND ?
            """, (week_start, week_end))

            daily_stats = await db.execute_fetchall("""
                SELECT date, new_listings, total_views, total_wants
                FROM daily_stats
                WHERE date BETWEEN ? AND ?
                ORDER BY date ASC
            """, (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")))

            return {
                "period": {
                    "start": start.strftime("%Y-%m-%d"),
                    "end": end.strftime("%Y-%m-%d"),
                    "days": 7
                },
                "summary": {
                    "new_listings": new_listings,
                    "polished_count": polished,
                    "price_updates": price_updates,
                    "total_views": metrics[0] or 0,
                    "total_wants": metrics[1] or 0,
                    "total_sales": metrics[2] or 0,
                },
                "daily_breakdown": [dict(row) for row in daily_stats]
            }

    async def get_monthly_report(self, year: int = None, month: int = None) -> Dict[str, Any]:
        """
        获取月报数据

        Args:
            year: 年份，默认今年
            month: 月份，默认上月

        Returns:
            月报数据
        """
        now = datetime.now()
        target_year = year or now.year
        target_month = month or (now.month - 1 or 12)

        if target_month == 12:
            target_year -= 1

        import calendar
        days_in_month = calendar.monthrange(target_year, target_month)[1]

        start_date = f"{target_year}-{target_month:02d}-01"
        end_date = f"{target_year}-{target_month:02d}-{days_in_month:02d}"

        async with aiosqlite.connect(self.db_path, timeout=self._db_timeout) as db:
            db.row_factory = aiosqlite.Row

            operations = await db.execute_fetchall("""
                SELECT operation_type, COUNT(*) as count
                FROM operation_logs
                WHERE date(timestamp) BETWEEN ? AND ?
                GROUP BY operation_type
            """, (start_date, end_date))

            new_listings = sum(1 for op in operations if op[0] == "PUBLISH")

            sold_products = await db.execute_fetchall("""
                SELECT price FROM products
                WHERE status = 'sold' AND date(sold_at) BETWEEN ? AND ?
            """, (start_date, end_date))

            revenue = sum(p[0] for p in sold_products)

            avg_sell_time = 0

            category_stats = await db.execute_fetchall("""
                SELECT category, COUNT(*) as count, AVG(price) as avg_price
                FROM products
                WHERE status = 'sold' AND date(sold_at) BETWEEN ? AND ?
                GROUP BY category
            """, (start_date, end_date))

            return {
                "period": {
                    "year": target_year,
                    "month": target_month,
                    "days": days_in_month
                },
                "summary": {
                    "total_listings": new_listings,
                    "total_sold": len(sold_products),
                    "total_revenue": round(revenue, 2),
                    "avg_sell_time_days": avg_sell_time,
                },
                "top_categories": [
                    {"category": c[0], "count": c[1], "avg_price": round(c[2] or 0, 2)}
                    for c in category_stats
                ]
            }

    async def get_product_performance(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        获取商品表现排名

        Args:
            days: 查询天数

        Returns:
            商品表现列表
        """
        async with aiosqlite.connect(self.db_path, timeout=self._db_timeout) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute("""
                SELECT p.*,
                       COALESCE(SUM(m.views), 0) as total_views,
                       COALESCE(SUM(m.wants), 0) as total_wants
                FROM products p
                LEFT JOIN product_metrics m ON p.product_id = m.product_id
                AND m.timestamp >= datetime('now', ?)
                GROUP BY p.product_id
                ORDER BY total_wants DESC, total_views DESC
                LIMIT 50
            """, (f"-{days} days",))

            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_trend_data(self, metric: str = "views", days: int = 30) -> List[Dict[str, Any]]:
        """
        获取趋势数据

        Args:
            metric: 指标类型 (views, wants, sales)
            days: 天数

        Returns:
            趋势数据列表
        """
        metric = self._validate_metric(metric)

        async with aiosqlite.connect(self.db_path, timeout=self._db_timeout) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(f"""
                SELECT date(timestamp) as date, SUM({metric}) as value
                FROM product_metrics
                WHERE timestamp >= datetime('now', ?)
                GROUP BY date(timestamp)
                ORDER BY date ASC
            """, (f"-{days} days",))

            rows = await cursor.fetchall()
            return [{"date": row[0], "value": row[1]} for row in rows]

    async def export_data(self, data_type: str = "products",
                         format: str = "csv",
                         filepath: str = None) -> str:
        """
        导出数据

        Args:
            data_type: 数据类型 (products, logs, metrics)
            format: 导出格式 (csv, json)
            filepath: 文件路径

        Returns:
            导出文件路径
        """
        if data_type not in self._allowed_export_types:
            raise ValueError(f"Invalid data_type: {data_type}. Must be one of {self._allowed_export_types}")

        if format not in self._allowed_formats:
            raise ValueError(f"Invalid format: {format}. Must be one of {self._allowed_formats}")

        if not filepath:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"data/export_{data_type}_{timestamp}.{format}"

        Path(filepath).parent.mkdir(parents=True, exist_ok=True)

        if data_type == "products":
            data = await self._export_products()
        elif data_type == "logs":
            data = await self._export_logs()
        elif data_type == "metrics":
            data = await self._export_metrics()
        else:
            data = []

        if format == "csv":
            return await self._write_csv(filepath, data)
        else:
            return await self._write_json(filepath, data)

    async def _export_products(self) -> List[Dict[str, Any]]:
        """导出商品数据"""
        async with aiosqlite.connect(self.db_path, timeout=self._db_timeout) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM products ORDER BY created_at DESC")
            return [dict(row) for row in await cursor.fetchall()]

    async def _export_logs(self) -> List[Dict[str, Any]]:
        """导出日志数据"""
        return await self.get_operation_logs(limit=10000)

    async def _export_metrics(self) -> List[Dict[str, Any]]:
        """导出指标数据"""
        async with aiosqlite.connect(self.db_path, timeout=self._db_timeout) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM product_metrics
                ORDER BY timestamp DESC LIMIT 10000
            """)
            return [dict(row) for row in await cursor.fetchall()]

    async def _write_csv(self, filepath: str, data: List[Dict]) -> str:
        """写入CSV文件"""
        if not data:
            return filepath

        with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)

        self.logger.success(f"Exported to {filepath}")
        return filepath

    async def _write_json(self, filepath: str, data: List[Dict]) -> str:
        """写入JSON文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        self.logger.success(f"Exported to {filepath}")
        return filepath

    async def cleanup_old_data(self, days: int = 90) -> Dict[str, int]:
        """
        清理旧数据

        Args:
            days: 保留天数

        Returns:
            清理统计
        """
        async with self._write_lock:
            async with aiosqlite.connect(self.db_path, timeout=self._db_timeout) as db:
                cursor = await db.execute("""
                    DELETE FROM operation_logs
                    WHERE timestamp < datetime('now', ?)
                """, (f"-{days} days",))
                logs_deleted = cursor.rowcount

                cursor = await db.execute("""
                    DELETE FROM product_metrics
                    WHERE timestamp < datetime('now', ?)
                """, (f"-{days} days",))
                metrics_deleted = cursor.rowcount

                await db.commit()

                return {
                    "logs_deleted": logs_deleted,
                    "metrics_deleted": metrics_deleted
                }

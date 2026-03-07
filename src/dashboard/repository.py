"""Dashboard data access — SQLite queries for stats, trends, operations, products."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime, timedelta
from typing import Any


class DashboardRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            yield conn

    def get_summary(self) -> dict[str, Any]:
        with self._connect() as conn:
            total_operations = conn.execute("SELECT COUNT(*) AS c FROM operation_logs").fetchone()["c"]
            today_operations = conn.execute(
                "SELECT COUNT(*) AS c FROM operation_logs WHERE date(timestamp)=date('now','localtime')"
            ).fetchone()["c"]
            active_products = conn.execute("SELECT COUNT(*) AS c FROM products WHERE status='active'").fetchone()["c"]
            sold_products = conn.execute("SELECT COUNT(*) AS c FROM products WHERE status='sold'").fetchone()["c"]
            total_views = conn.execute("SELECT COALESCE(SUM(views),0) AS s FROM product_metrics").fetchone()["s"]
            total_wants = conn.execute("SELECT COALESCE(SUM(wants),0) AS s FROM product_metrics").fetchone()["s"]
            total_sales = conn.execute("SELECT COALESCE(SUM(sales),0) AS s FROM product_metrics").fetchone()["s"]

        return {
            "total_operations": total_operations,
            "today_operations": today_operations,
            "active_products": active_products,
            "sold_products": sold_products,
            "total_views": total_views,
            "total_wants": total_wants,
            "total_sales": total_sales,
        }

    def get_trend(self, metric: str, days: int) -> list[dict[str, Any]]:
        allowed = {"views", "wants", "sales", "inquiries"}
        if metric not in allowed:
            metric = "views"

        start_date = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")

        column_map = {"views": "views", "wants": "wants", "sales": "sales", "inquiries": "inquiries"}
        col = column_map[metric]

        sql = f"""
            SELECT date(timestamp) AS d, COALESCE(SUM({col}),0) AS v
            FROM product_metrics
            WHERE date(timestamp) >= ?
            GROUP BY date(timestamp)
            ORDER BY d ASC
        """

        rows_by_day: dict[str, int] = {}
        with self._connect() as conn:
            for row in conn.execute(sql, (start_date,)).fetchall():
                rows_by_day[str(row["d"])] = int(row["v"])

        result = []
        for i in range(days):
            d = (datetime.now() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
            result.append({"date": d, "value": rows_by_day.get(d, 0)})
        return result

    def get_recent_operations(self, limit: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT operation_type, product_id, account_id, status, timestamp
                FROM operation_logs
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [dict(row) for row in rows]

    def get_top_products(self, limit: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                  p.product_id,
                  p.title,
                  p.status,
                  COALESCE(SUM(m.views),0) AS views,
                  COALESCE(SUM(m.wants),0) AS wants,
                  COALESCE(SUM(m.sales),0) AS sales
                FROM products p
                LEFT JOIN product_metrics m ON m.product_id = p.product_id
                GROUP BY p.product_id, p.title, p.status
                ORDER BY wants DESC, views DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [dict(row) for row in rows]

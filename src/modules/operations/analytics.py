import os
import sqlite3
from contextlib import closing

from loguru import logger


class AnalyticsService:
    def __init__(self, config):
        self.config = config
        self.db_path = "data/xianyu.db"
        self._init_db()

    def _init_db(self):
        """
        Initialize the SQLite database.
        """
        os.makedirs("data", exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            cursor = conn.cursor()

            # Create operations log table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS operation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    operation_type TEXT,
                    details TEXT,
                    status TEXT
                )
            """)

            # Create metrics table (e.g., views, wants)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS product_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    product_title TEXT,
                    views INTEGER,
                    wants INTEGER,
                    cconsultations INTEGER
                )
            """)

    def log_operation(self, op_type: str, details: str, status: str = "success"):
        """
        Log an automation operation.
        """
        try:
            with closing(sqlite3.connect(self.db_path)) as conn, conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=5000")
                conn.execute(
                    "INSERT INTO operation_logs (operation_type, details, status) VALUES (?, ?, ?)",
                    (op_type, details, status),
                )
        except Exception as e:
            logger.error(f"Failed to log operation: {e}")

    def record_metrics(self, title: str, views: int, wants: int, consultations: int):
        """
        Record product metrics.
        """
        try:
            with closing(sqlite3.connect(self.db_path)) as conn, conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=5000")
                conn.execute(
                    "INSERT INTO product_metrics (product_title, views, wants, cconsultations) VALUES (?, ?, ?, ?)",
                    (title, views, wants, consultations),
                )
        except Exception as e:
            logger.error(f"Failed to record metrics: {e}")

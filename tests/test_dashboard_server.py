"""dashboard_server 测试。"""

import sqlite3

from src.dashboard_server import DashboardRepository, _safe_int


def _init_db(path: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE operation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_type TEXT,
                product_id TEXT,
                account_id TEXT,
                details TEXT,
                status TEXT,
                error_message TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE product_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT,
                product_title TEXT,
                views INTEGER DEFAULT 0,
                wants INTEGER DEFAULT 0,
                inquiries INTEGER DEFAULT 0,
                sales INTEGER DEFAULT 0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT,
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
            """
        )

        conn.execute("INSERT INTO operation_logs (operation_type, status) VALUES ('PUBLISH','success')")
        conn.execute("INSERT INTO products (product_id, title, status) VALUES ('p1','商品A','active')")
        conn.execute("INSERT INTO product_metrics (product_id, views, wants, sales) VALUES ('p1', 100, 8, 1)")
        conn.commit()


def test_safe_int_clamps() -> None:
    assert _safe_int("200", default=10, min_value=1, max_value=120) == 120
    assert _safe_int("0", default=10, min_value=1, max_value=120) == 1
    assert _safe_int("abc", default=10, min_value=1, max_value=120) == 10


def test_dashboard_repository_summary(temp_dir) -> None:
    db_path = temp_dir / "dash.db"
    _init_db(str(db_path))

    repo = DashboardRepository(str(db_path))
    summary = repo.get_summary()

    assert summary["total_operations"] == 1
    assert summary["active_products"] == 1
    assert summary["total_views"] == 100

    trend = repo.get_trend("views", days=3)
    assert len(trend) == 3

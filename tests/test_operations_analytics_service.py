import sqlite3

from src.modules.operations.analytics import AnalyticsService


def test_analytics_service_init_and_record(tmp_path):
    svc = AnalyticsService(config={})
    svc.db_path = str(tmp_path / "ops.db")
    svc._init_db()

    svc.log_operation("publish", "ok")
    svc.record_metrics("item", 1, 2, 3)

    conn = sqlite3.connect(svc.db_path)
    c = conn.cursor()
    c.execute("select count(*) from operation_logs")
    assert c.fetchone()[0] == 1
    c.execute("select product_title, views, wants, cconsultations from product_metrics")
    assert c.fetchone() == ("item", 1, 2, 3)
    conn.close()


def test_analytics_service_error_branches(monkeypatch, tmp_path):
    svc = AnalyticsService(config={})
    svc.db_path = str(tmp_path / "ops2.db")
    svc._init_db()

    class Boom(Exception):
        pass

    def broken(_):
        raise Boom("x")

    monkeypatch.setattr("src.modules.operations.analytics.sqlite3.connect", broken)
    # should not raise
    svc.log_operation("x", "y")
    svc.record_metrics("x", 1, 1, 1)

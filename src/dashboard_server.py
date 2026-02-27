"""轻量后台可视化服务。"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from src.core.config import get_config


def _safe_int(value: str | None, default: int, min_value: int, max_value: int) -> int:
    try:
        if value is None:
            return default
        n = int(value)
        if n < min_value:
            return min_value
        if n > max_value:
            return max_value
        return n
    except (TypeError, ValueError):
        return default


class DashboardRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

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

        sql = f"""
            SELECT date(timestamp) AS d, COALESCE(SUM({metric}),0) AS v
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


DASHBOARD_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>闲鱼运营后台</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+SC:wght@400;500;700&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {
      --bg: #fff6eb;
      --card: #ffffff;
      --ink: #222;
      --muted: #666;
      --brand: #ff6a00;
      --brand-2: #007a78;
      --line: #ffe0bf;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "IBM Plex Sans SC", "PingFang SC", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 10% 20%, #ffd7b1 0, transparent 45%),
        radial-gradient(circle at 90% 10%, #d9ffef 0, transparent 35%),
        var(--bg);
    }
    .wrap { max-width: 1180px; margin: 0 auto; padding: 28px 18px 40px; }
    .title { display:flex; justify-content:space-between; align-items:end; gap: 12px; margin-bottom: 18px; }
    .title h1 { margin:0; font-size: 30px; letter-spacing:.5px; }
    .title p { margin:4px 0 0; color: var(--muted); }
    .grid { display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap:12px; margin-bottom: 14px; }
    .card {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px 14px;
      box-shadow: 0 8px 24px rgba(255,106,0,.08);
    }
    .k { font-size: 13px; color: var(--muted); margin-bottom:8px; }
    .v { font-size: 26px; font-weight: 700; color: var(--brand); }
    .panes { display:grid; grid-template-columns: 2fr 1fr; gap: 12px; margin-bottom: 14px; }
    .panel-title { font-size: 16px; font-weight: 600; margin:0 0 10px; }
    .table-wrap { overflow:auto; }
    table { width:100%; border-collapse: collapse; font-size:13px; }
    th, td { text-align:left; border-bottom:1px solid #f0f0f0; padding:8px 6px; white-space: nowrap; }
    th { color: var(--muted); font-weight: 500; }
    .badge { border-radius: 999px; padding: 2px 8px; font-size: 12px; color: #fff; }
    .ok { background: #14a44d; }
    .bad { background: #d63384; }
    .warn { background: #f08c00; }
    .footer { color: var(--muted); font-size: 12px; margin-top: 8px; }
    @media (max-width: 940px) {
      .grid { grid-template-columns: repeat(2, minmax(0,1fr)); }
      .panes { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="title">
      <div>
        <h1>闲鱼运营后台</h1>
        <p>自动每 30 秒刷新数据，展示运营趋势和最近操作。</p>
      </div>
      <div class="footer" id="updatedAt">--</div>
    </div>

    <section class="grid">
      <article class="card"><div class="k">总操作数</div><div class="v" id="totalOps">0</div></article>
      <article class="card"><div class="k">今日操作</div><div class="v" id="todayOps">0</div></article>
      <article class="card"><div class="k">在售商品</div><div class="v" id="activeProducts">0</div></article>
      <article class="card"><div class="k">累计想要</div><div class="v" id="totalWants">0</div></article>
    </section>

    <section class="panes">
      <article class="card">
        <h2 class="panel-title">近 30 天浏览趋势</h2>
        <canvas id="trendChart" height="110"></canvas>
      </article>
      <article class="card">
        <h2 class="panel-title">累计指标</h2>
        <canvas id="mixChart" height="110"></canvas>
      </article>
    </section>

    <section class="panes">
      <article class="card table-wrap">
        <h2 class="panel-title">最近操作日志</h2>
        <table>
          <thead>
            <tr><th>时间</th><th>操作</th><th>商品</th><th>账号</th><th>状态</th></tr>
          </thead>
          <tbody id="opsBody"></tbody>
        </table>
      </article>
      <article class="card table-wrap">
        <h2 class="panel-title">商品表现 Top</h2>
        <table>
          <thead>
            <tr><th>商品</th><th>想要</th><th>浏览</th><th>成交</th></tr>
          </thead>
          <tbody id="productBody"></tbody>
        </table>
      </article>
    </section>
  </div>

<script>
const trendCtx = document.getElementById('trendChart');
const mixCtx = document.getElementById('mixChart');

const trendChart = new Chart(trendCtx, {
  type: 'line',
  data: {
    labels: [],
    datasets: [{
      label: '浏览量',
      data: [],
      borderColor: '#ff6a00',
      tension: .3,
      fill: true,
      backgroundColor: 'rgba(255,106,0,.15)'
    }]
  },
  options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
});

const mixChart = new Chart(mixCtx, {
  type: 'bar',
  data: {
    labels: ['浏览', '想要', '成交'],
    datasets: [{ data: [0, 0, 0], backgroundColor: ['#ff6a00', '#007a78', '#2b8a3e'] }]
  },
  options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
});

function statusBadge(status) {
  const s = (status || '').toLowerCase();
  if (s === 'success') return '<span class="badge ok">success</span>';
  if (s === 'warning' || s === 'warn') return '<span class="badge warn">warning</span>';
  return '<span class="badge bad">' + (status || 'unknown') + '</span>';
}

async function refresh() {
  const [summaryRes, trendRes, opsRes, productsRes] = await Promise.all([
    fetch('/api/summary'),
    fetch('/api/trend?metric=views&days=30'),
    fetch('/api/recent-operations?limit=20'),
    fetch('/api/top-products?limit=12'),
  ]);

  const summary = await summaryRes.json();
  const trend = await trendRes.json();
  const ops = await opsRes.json();
  const products = await productsRes.json();

  document.getElementById('totalOps').textContent = summary.total_operations ?? 0;
  document.getElementById('todayOps').textContent = summary.today_operations ?? 0;
  document.getElementById('activeProducts').textContent = summary.active_products ?? 0;
  document.getElementById('totalWants').textContent = summary.total_wants ?? 0;
  document.getElementById('updatedAt').textContent = '更新时间: ' + new Date().toLocaleString();

  trendChart.data.labels = trend.map(i => i.date.slice(5));
  trendChart.data.datasets[0].data = trend.map(i => i.value);
  trendChart.update();

  mixChart.data.datasets[0].data = [summary.total_views ?? 0, summary.total_wants ?? 0, summary.total_sales ?? 0];
  mixChart.update();

  document.getElementById('opsBody').innerHTML = ops.map(o => `
    <tr>
      <td>${o.timestamp || '-'}</td>
      <td>${o.operation_type || '-'}</td>
      <td>${o.product_id || '-'}</td>
      <td>${o.account_id || '-'}</td>
      <td>${statusBadge(o.status)}</td>
    </tr>
  `).join('');

  document.getElementById('productBody').innerHTML = products.map(p => `
    <tr>
      <td title="${p.title || ''}">${(p.title || p.product_id || '-').slice(0, 18)}</td>
      <td>${p.wants ?? 0}</td>
      <td>${p.views ?? 0}</td>
      <td>${p.sales ?? 0}</td>
    </tr>
  `).join('');
}

refresh().catch(console.error);
setInterval(() => refresh().catch(console.error), 30000);
</script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    repo: DashboardRepository

    def _send_json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, html: str, status: int = 200) -> None:
        data = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        try:
            if path == "/":
                self._send_html(DASHBOARD_HTML)
                return

            if path == "/api/summary":
                self._send_json(self.repo.get_summary())
                return

            if path == "/api/trend":
                metric = (query.get("metric") or ["views"])[0]
                days = _safe_int((query.get("days") or ["30"])[0], default=30, min_value=1, max_value=120)
                self._send_json(self.repo.get_trend(metric=metric, days=days))
                return

            if path == "/api/recent-operations":
                limit = _safe_int((query.get("limit") or ["20"])[0], default=20, min_value=1, max_value=200)
                self._send_json(self.repo.get_recent_operations(limit=limit))
                return

            if path == "/api/top-products":
                limit = _safe_int((query.get("limit") or ["12"])[0], default=12, min_value=1, max_value=200)
                self._send_json(self.repo.get_top_products(limit=limit))
                return

            self._send_json({"error": "Not Found"}, status=404)
        except sqlite3.Error as e:
            self._send_json({"error": f"Database error: {e}"}, status=500)
        except Exception as e:  # pragma: no cover - safety net
            self._send_json({"error": str(e)}, status=500)

    def log_message(self, format: str, *args: Any) -> None:
        return


def run_server(host: str = "127.0.0.1", port: int = 8091, db_path: str | None = None) -> None:
    config = get_config()
    resolved_db = db_path or config.database.get("path", "data/agent.db")

    Path(resolved_db).parent.mkdir(parents=True, exist_ok=True)
    DashboardHandler.repo = DashboardRepository(resolved_db)

    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Dashboard running: http://{host}:{port}")
    print(f"Using database: {resolved_db}")
    server.serve_forever()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="闲鱼后台可视化服务")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8091, help="监听端口")
    parser.add_argument("--db-path", default=None, help="数据库路径（默认读取配置）")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_server(host=args.host, port=args.port, db_path=args.db_path)


if __name__ == "__main__":
    main()

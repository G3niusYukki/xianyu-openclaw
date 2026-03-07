# Node.js 后端 — 已弃用

此目录下的 Node.js 后端功能已全部迁移至 Python 统一后端 (`src/dashboard_server.py`)。

## 已迁移的功能

| 原 Node.js 路由 | 迁移至 Python |
| --- | --- |
| `GET/PUT /api/config` | `dashboard_server.py` — `do_GET/do_PUT` |
| `GET /api/config/sections` | `dashboard_server.py` — `do_GET` |
| `POST /api/xgj/proxy` | `dashboard_server.py` — `do_POST` |
| `POST /api/xgj/order/receive` | `dashboard_server.py` — `do_POST` |
| `POST /api/xgj/product/receive` | `dashboard_server.py` — `do_POST` |
| `GET /api/health/check` | `dashboard_server.py` — `do_GET` |
| `GET /health` | `dashboard_server.py` — `/healthz` |

## 前端 API 层

前端已统一使用 `api` 实例（baseURL: `/api`），代理指向 Python 后端 `localhost:8091`。

`nodeApi` 和 `pyApi` 仅作为向后兼容别名保留。

## 清理建议

当确认所有功能正常运行后，可以安全删除整个 `server/` 目录。

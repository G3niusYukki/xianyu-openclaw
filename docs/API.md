# API 文档

当前主线有两套 HTTP 服务：

- `Python Core`：核心业务接口，默认 `http://localhost:8091`
- `Node Proxy`：可选薄代理，默认 `http://localhost:3001`

## Python Core

### 健康检查

- `GET /healthz`
- `GET /api/status`

### 配置与账号

- `GET /api/config`
- `POST /api/config`
- `GET /api/config/sections`
- `GET /api/accounts`
- `POST /api/update-cookie`

### 商品与订单

- `GET /api/xgj/products`
- `GET /api/xgj/orders`
- `POST /api/xgj/product/publish`
- `POST /api/xgj/product/unpublish`
- `POST /api/xgj/order/modify-price`
- `POST /api/xgj/order/deliver`

### 自动上架

- `GET /api/listing/templates`
- `POST /api/listing/preview`
- `POST /api/listing/publish`
- `GET /api/generated-image?path=...`

### 运营与诊断

- `GET /api/summary`
- `GET /api/trend`
- `GET /api/top-products`
- `GET /api/recent-operations`
- `GET /api/logs/content`
- `POST /api/module/control`
- `POST /api/service/control`

## Node Proxy

### 健康检查

- `GET /health`

### 配置代理

- `GET /api/config`
- `POST /api/config`
- `PUT /api/config`
- `GET /api/config/sections`

这几条接口只是转发给 Python。

### 闲管家代理 / webhook

- `POST /api/xgj/proxy`
- `POST /api/xgj/order/receive`
- `POST /api/xgj/product/receive`

其中：

- `/api/xgj/proxy` 用于透传 Open Platform 请求。
- `/api/xgj/*/receive` 会先做签名校验，再转发给 Python 回调接口。

## CLI

项目仍保留 `python -m src.cli` 作为诊断和模块控制入口，但当前主路径是 Web 工作台 + HTTP API，不再依赖 OpenClaw Skill 调度。

## 约束

- 所有前端页面都必须走真实接口。
- 不允许为了展示而在接口层返回 mock 数据。
- Node 不是业务真相源，配置与状态以 Python 为准。

# DEPLOYMENT

## 部署口径

当前唯一推荐架构：

- `React` 前端
- `Python` 核心服务
- `Node` 可选代理

OpenClaw 不是默认路径，也不是必需依赖。

## 本地部署

```bash
cp .env.example .env
./start.sh
```

默认端口：

- `5173` 前端
- `8091` Python
- `3001` Node

## Docker Compose

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f
```

服务说明：

- `react-frontend`
- `python-backend`
- `node-backend`

## 必填配置

```env
XIANYU_COOKIE_1=
AI_PROVIDER=
AI_API_KEY=
AI_BASE_URL=
AI_MODEL=
XGJ_APP_KEY=
XGJ_APP_SECRET=
XGJ_BASE_URL=https://open.goofish.pro
```

常用可选配置：

```env
XGJ_MERCHANT_ID=
AUTH_PASSWORD=
AUTH_USERNAME=admin
FRONTEND_PORT=5173
NODE_PORT=3001
PYTHON_PORT=8091
```

## 健康检查

```bash
curl -fsS http://localhost:8091/healthz
curl -fsS http://localhost:3001/health
```

## 运维建议

- 配置只维护一套，以 Python 配置接口和根目录 `.env` 为准。
- Node 故障不会影响 Python 核心能力，但会影响 webhook 转发和部分代理路由。
- 如果商品/订单页面异常，优先排查闲管家配置和 Python 服务，不要先查 Node。

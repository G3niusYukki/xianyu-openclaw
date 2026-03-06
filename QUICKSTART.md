# QUICKSTART

目标：在本机启动 API-first 版闲鱼自动化工作台。

## 1. 准备环境

- Python `3.10+`
- Node.js `18+`
- 一个可用的闲鱼 Cookie
- 一个 AI 提供商 Key
- 一个闲管家 Open Platform 应用

## 2. 配置 `.env`

```bash
cp .env.example .env
```

最小配置：

```env
XIANYU_COOKIE_1=

AI_PROVIDER=deepseek
AI_API_KEY=
AI_BASE_URL=https://api.deepseek.com/v1
AI_MODEL=deepseek-chat

XGJ_APP_KEY=
XGJ_APP_SECRET=
XGJ_BASE_URL=https://open.goofish.pro
```

## 3. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd server && npm install
cd ../client && npm install
cd ..
```

## 4. 启动

推荐一条命令：

```bash
./start.sh
```

或分别启动：

```bash
python3 -m src.dashboard_server --host 127.0.0.1 --port 8091
cd server && npm run dev
cd client && npm run dev
```

## 5. 访问地址

- 前端：`http://127.0.0.1:5173`
- Python：`http://127.0.0.1:8091`
- Node：`http://127.0.0.1:3001`

## 6. 首次检查

先确认服务健康：

```bash
curl -fsS http://127.0.0.1:8091/healthz
curl -fsS http://127.0.0.1:3001/health
curl -fsS http://127.0.0.1:8091/api/config/sections
```

然后在前端检查：

1. `工作台` 是否能显示系统状态。
2. `店铺管理` 是否能识别 Cookie。
3. `系统配置` 是否能读到 AI / 闲管家配置。
4. `商品管理` / `订单中心` 是否能拉到真实数据。
5. `自动上架` 是否能生成真实预览图。

## 7. Docker 启动

```bash
docker compose up -d --build
docker compose ps
```

前端默认映射到 `5173`，Python 到 `8091`，Node 到 `3001`。

## 8. 重要说明

- 本项目当前不依赖 OpenClaw。
- Node 只是可选代理层，不是配置真相源。
- 不提供 mock 数据回退；接口缺失会直接暴露真实错误，便于排查。

# 快速开始

5 分钟内启动闲鱼管家。

## 1. 准备环境

## 前提条件

| 依赖 | 版本要求 | 说明 |
|------|---------|------|
| Python | 3.10+ | Python 后端运行时 |
| Node.js | 18+ | Node.js 后端和 React 前端 |
| npm | 随 Node.js 安装 | 包管理器 |
| 闲鱼 Cookie | - | 从浏览器获取的登录凭证 |
| AI API Key | - | DeepSeek / 阿里百炼 / OpenAI 等，任选一个 |

---

## 方式一：本地开发模式（推荐）

### 第 1 步：克隆项目

```bash
git clone https://github.com/G3niusYukki/xianyu-openclaw.git
cd xianyu-openclaw
```

### 第 2 步：安装依赖

```bash
# Python 依赖
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Node.js 依赖
cd server && npm install && cd ..
cd client && npm install && cd ..
```

> Windows 用户激活虚拟环境用 `.venv\Scripts\activate` 替代 `source .venv/bin/activate`。

### 第 3 步：配置环境变量

```bash
cp .env.example .env
```

用编辑器打开 `.env`，填入以下必需信息：

```bash
# 闲鱼 Cookie（从浏览器获取）
XIANYU_COOKIE_1=your_cookie_here

# AI 服务配置（以 DeepSeek 为例）
AI_PROVIDER=deepseek
AI_API_KEY=sk-your-deepseek-key
AI_BASE_URL=https://api.deepseek.com/v1
AI_MODEL=deepseek-chat

```

### 第 4 步：启动服务

使用一键启动脚本（推荐）：

```bash
# macOS / Linux
./start.sh

# Windows
start.bat
```

脚本会自动启动 Node.js 后端、React 前端和 Python 后端。如需 Lite 直连模式（WebSocket 消息监听 + AI 自动回复），可另开终端执行 `python -m src.lite`。

### 第 5 步：验证启动

打开浏览器，依次访问：

| 服务 | 地址 | 预期结果 |
|------|------|---------|
| React 前端 | http://localhost:5173 | 管理面板首页 |
| Python Dashboard | http://localhost:8091 | Dashboard 页面 |
| Node.js 后端 | http://localhost:3001/health | 返回健康状态 JSON |

---

## 方式二：Docker 模式

### 第 1 步：配置

```bash
cp .env.example .env
```

编辑 `.env`，填入闲鱼 Cookie、AI 服务等配置（同本地模式）。

### 第 2 步：启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd server && npm install
cd ../client && npm install
cd ..
```

Docker Compose 会启动以下容器：

| 容器 | 端口 | 说明 |
|------|------|------|
| xianyu-node-backend | 3001 | Node.js 后端 |
| xianyu-python-backend | 8091 | Python 后端 |
| xianyu-react-frontend | 5173 | React 前端 |

### 第 3 步：验证

```bash
python3 -m src.dashboard_server --host 127.0.0.1 --port 8091
cd server && npm run dev
cd client && npm run dev
```

## 5. 访问地址

- 前端工作台：`http://127.0.0.1:5173`
- Python 核心：`http://127.0.0.1:8091`
- Node 薄代理：`http://127.0.0.1:3001`

## 6. 首次检查

先做健康检查：

```bash
curl -fsS http://127.0.0.1:8091/healthz
curl -fsS http://127.0.0.1:3001/health
curl -fsS http://127.0.0.1:8091/api/config/sections
curl -fsS http://127.0.0.1:8091/api/accounts
```

再在前端确认：

1. `工作台` 能显示系统状态和首次配置引导。
2. `店铺管理` 能识别 Cookie 和账号状态。
3. `系统配置` 能读写 AI / 闲管家配置。
4. `商品管理` 和 `订单中心` 能拉到真实数据。
5. `自动上架` 能生成真实预览图。

## 7. Docker 启动

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f
```

所有容器应处于 `Up (healthy)` 状态。

访问 http://localhost:5173 打开管理面板。

---

## 获取闲鱼 Cookie

1. 用 Chrome 打开 https://www.goofish.com 并登录
2. 按 **F12** 打开开发者工具
3. 切换到 **Network** 标签
4. 按 **F5** 刷新页面
5. 点击任意一个请求
6. 在右侧 **Request Headers** 中找到 `Cookie:` 一行
7. 全部复制，粘贴到 `.env` 文件中

Cookie 有效期通常 7-30 天。过期后可通过管理面板或 Dashboard（http://localhost:8091/cookie）在线更新，或重新从浏览器获取。

---

## 常见问题

### 端口被占用

**症状**：启动时报 `port already in use` 或 `address already in use`。

**解决**：检查哪个进程占用了端口，停掉后重试：

```bash
# macOS/Linux
lsof -i :5173
lsof -i :3001
lsof -i :8091

# 或修改端口
# .env 中设置 FRONTEND_PORT、NODE_PORT、PYTHON_PORT
```

### Cookie 失效

**症状**：WebSocket 连接失败，或消息监听无响应。

**解决**：重新从浏览器获取 Cookie，更新到 `.env` 或通过 Dashboard 在线更新，然后重启 Python 后端。

### AI 服务报错

**症状**：自动回复无输出，或日志中出现 API 错误。

**解决**：
1. 检查 `.env` 中的 `AI_API_KEY` 是否正确
2. 确认 API Key 余额充足
3. 检查 `AI_BASE_URL` 是否可访问

### npm install 失败

**症状**：Node.js 依赖安装报错。

**解决**：
1. 确认 Node.js 版本 >= 18：`node -v`
2. 清除缓存重试：`npm cache clean --force && npm install`

### Python 依赖安装失败

**症状**：`pip install` 报错。

**解决**：
1. 确认 Python 版本 >= 3.10：`python3 --version`
2. 确认已激活虚拟环境
3. 国内用户可使用镜像源：`pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`

---

## 停止服务

```bash
# 本地模式：Ctrl+C 终止各终端进程

# Docker 模式
docker compose down          # 停止（保留数据）
docker compose down -v       # 停止并删除数据卷（谨慎）
```

---

## 下一步

- 详细使用指南：[USER_GUIDE.md](USER_GUIDE.md)
- 完整功能说明：[README.md](README.md)
- CLI 命令参考：`python -m src.cli --help`
- 参与开发：[CONTRIBUTING.md](CONTRIBUTING.md)

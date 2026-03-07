# DEPLOYMENT

> 闲鱼管家 (xianyu-openclaw) 完整部署方案

当前推荐的完整部署形态：

## 部署方式概览

| 部署方式 | 适用场景 | 难度 | 文档位置 |
|---------|---------|------|---------|
| **一键本地启动** | 开发测试、个人使用 | 简单 | [QUICKSTART.md](../QUICKSTART.md) |
| **Docker Compose** | 生产环境、多平台 | 中等 | 本文件第 3 节 |
| **Windows 脚本** | Windows 用户 | 简单 | 本文件第 4 节 |
| **模块化部署** | 大规模生产、分离运维 | 困难 | 本文件第 5 节 |

根目录 `.env` 是当前唯一推荐配置入口。

## 环境要求

### 本地一键启动

- **Python**: 3.10+
- **Node.js**: 16+
- **npm**: 8+

### Docker 部署

- **Docker Engine**: 20.10+
- **Docker Compose**: 2.0+

### 必需配置

- **闲鱼 Cookie**：系统支持自动从浏览器获取，也可手动粘贴
- **闲管家 API**：在 [闲管家开放平台](https://open.goofish.pro) 注册应用获取 AppKey/AppSecret
- **AI API Key**（可选）：支持 DeepSeek、通义千问等 OpenAI 兼容 API

---

## 一键本地启动

最简单的方式，适合开发和个人使用：

```bash
# 克隆项目
git clone https://github.com/G3niusYukki/xianyu-openclaw.git
cd xianyu-openclaw

# macOS / Linux
./start.sh

# Windows
start.bat
```

脚本会自动：
1. 检查 Python 和 Node.js 版本
2. 创建 `.env` 配置文件（如不存在）
3. 安装 Python 和 Node.js 依赖
4. 启动 Python 后端 (8091)、Node.js 后端 (3001)、React 前端 (5173)

启动后打开浏览器访问 `http://localhost:5173`。

---

## Docker Compose 部署

### 1. 克隆仓库

```bash
git clone https://github.com/G3niusYukki/xianyu-openclaw.git
cd xianyu-openclaw
```

常用可选项：

```bash
cp .env.example .env
# 编辑 .env 填入配置
```

关键配置项：

```bash
# 闲鱼 Cookie（可在前端页面自动获取）
XIANYU_COOKIE_1=your_cookie_here

# 闲管家开放平台
XGJ_APP_KEY=your_app_key
XGJ_APP_SECRET=your_app_secret

# AI 服务（推荐 DeepSeek）
AI_PROVIDER=deepseek
AI_API_KEY=your_api_key
AI_BASE_URL=https://api.deepseek.com/v1
AI_MODEL=deepseek-chat
```

## 本地部署

macOS / Linux：

```bash
docker compose up -d
docker compose logs -f
```

Compose 服务：

- `react-frontend`
- `python-backend`
- `node-backend`

持久化：

- `./data`：SQLite、生成图、运行态数据
- `./config`：只读配置目录
- `node-data`：Node 侧少量运行时数据

## 健康检查

```bash
docker compose ps

# 健康检查
curl http://localhost:8091/healthz  # Python 后端
curl http://localhost:3001/api/config  # Node.js 后端
```

访问 `http://localhost:5173` 进入管理面板。

---

## Windows 部署

### 方式 1：一键启动（推荐）

```bat
start.bat
```

### 方式 2：批处理脚本

```bat
scripts\windows\quickstart.bat     # 快速启动
scripts\windows\launcher.bat       # 交互式菜单
scripts\windows\module_status.bat  # 查看模块状态
scripts\windows\module_check.bat   # 模块健康检查
scripts\windows\doctor.bat         # 系统诊断
scripts\windows\dashboard.bat      # 启动数据看板
```

---

## macOS/Linux 脚本

```bash
# 启动数据看板
./scripts/unix/dashboard.sh 8091

# 恢复售前模块
./scripts/unix/recover_presales.sh

# macOS 开机自启（launchd）
./scripts/macos/install_service.sh install
./scripts/macos/install_service.sh uninstall
```

---

## 模块化部署

按业务模块分离部署：

| 模块 | 职责 | 启动命令 |
|------|------|---------|
| **presales** | 售前（消息自动回复、报价） | `python -m src.cli module --action start --target presales` |
| **operations** | 运营（调价、上下架） | `python -m src.cli module --action start --target operations` |
| **aftersales** | 售后（订单处理） | `python -m src.cli module --action start --target aftersales` |

### 模块管理命令

```bash
python -m src.cli module --action status --target all
python -m src.cli module --action stop --target all
python -m src.cli module --action recover --target presales
python -m src.cli module --action logs --target all --tail-lines 100
python -m src.cli module --action cookie-health
```

---

## 生产环境加固

### 反向代理（Nginx）

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:5173;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
    }

    location /api/ {
        proxy_pass http://localhost:3001;
    }

    location /py/ {
        proxy_pass http://localhost:8091;
    }
}
```

### 自动备份

```bash
./scripts/backup_data.sh

# cron 定时备份（每天凌晨 2 点）
0 2 * * * /path/to/xianyu-openclaw/scripts/backup_data.sh
```

### 监控告警

```bash
python -m src.cli automation --action setup \
  --enable-feishu \
  --feishu-webhook "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx"
```

---

## 数据库优化

SQLite 配置（已默认启用）：
- WAL 模式（并发写入优化）
- busy_timeout=5000ms（避免锁等待）

---

## 故障排查

### 服务无法启动

```bash
# Docker 方式
docker compose logs --tail 50
docker compose down && docker compose up -d

# 本地方式
# 检查端口占用
lsof -ti:8091 -ti:3001 -ti:5173 | xargs kill -9
```

### Cookie 失效

在管理面板「店铺管理」页面点击「自动获取」重新获取 Cookie。

或命令行检查：
```bash
python -m src.cli doctor --strict
```

---

## 更新升级

```bash
git pull origin main
# Docker 方式
docker compose down && docker compose up -d --build
# 本地方式
./start.sh
```

---

## 获取帮助

- [QUICKSTART.md](../QUICKSTART.md) - 快速开始
- [USER_GUIDE.md](../USER_GUIDE.md) - 用户指南
- [GitHub Issues](https://github.com/G3niusYukki/xianyu-openclaw/issues) - 问题反馈

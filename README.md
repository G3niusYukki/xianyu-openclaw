# 闲鱼自动化工具 (Xianyu OpenClaw)

基于 [OpenClaw](https://github.com/openclaw/openclaw) 的闲鱼自动化运营工具。通过自然语言对话操作闲鱼：发布商品、擦亮、调价、数据分析、多账号管理。

**v4.0.0**: 深度集成 OpenClaw — 浏览器自动化由 OpenClaw Gateway 统一管理，用 AI 对话替代传统 Web 界面，Docker 一键部署。

[![Release](https://img.shields.io/github/v/release/G3niusYukki/xianyu-openclaw?style=flat-square)](https://github.com/G3niusYukki/xianyu-openclaw/releases/latest)
[![License](https://img.shields.io/github/license/G3niusYukki/xianyu-openclaw?style=flat-square)](LICENSE)

---

## 工作原理

```
用户（自然语言对话）
    |
    v
OpenClaw Gateway（AI Agent + Web UI）
    |
    v
闲鱼 Skills（5 个技能模块）
    |
    v
Python CLI（业务逻辑 + 数据库）
    |
    v
OpenClaw Managed Browser（headless Chromium via CDP）
    |
    v
闲鱼网站（goofish.com）
```

你只需要在浏览器打开 OpenClaw 界面，用中文告诉它你想做什么：

- "帮我发布一个 iPhone 15 Pro，价格 5999，95新"
- "擦亮所有商品"
- "今天运营数据怎么样"
- "把那个 MacBook 降到 8000"

OpenClaw 的 AI Agent 会理解你的意图，自动调用对应的技能完成操作。

---

## 快速开始

### 前置要求

- Docker 和 Docker Compose
- 一个 AI API Key（Anthropic / OpenAI / DeepSeek 任选一个）
- 闲鱼账号 Cookie

### 1. 克隆项目

```bash
git clone https://github.com/G3niusYukki/xianyu-openclaw.git
cd xianyu-openclaw
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入：
- AI Provider API Key（`ANTHROPIC_API_KEY` 或 `OPENAI_API_KEY` 等）
- `OPENCLAW_GATEWAY_TOKEN`（自定义一个密码）
- `AUTH_PASSWORD`（Web UI 登录密码）
- `XIANYU_COOKIE_1`（闲鱼 Cookie）

### 3. 一键启动

```bash
docker compose up -d
```

### 4. 打开使用

浏览器访问：

```
http://localhost:8080
```

用你设置的 `AUTH_USERNAME` / `AUTH_PASSWORD` 登录，即可开始对话。

---

## 技能列表

| 技能 | 功能 | 示例指令 |
|------|------|---------|
| xianyu-publish | 发布商品 | "帮我发布一个 AirPods Pro，价格 800" |
| xianyu-manage | 擦亮/调价/上下架 | "擦亮所有商品"、"把 iPhone 降到 4000" |
| xianyu-content | AI 文案生成 | "帮我写一个 MacBook 的标题和描述" |
| xianyu-metrics | 数据分析 | "今天运营数据怎么样"、"最近一周浏览量趋势" |
| xianyu-accounts | 账号管理 | "我的账号还正常吗"、"帮我刷新 Cookie" |

---

## 项目结构

```
xianyu-openclaw/
├── skills/                      # OpenClaw 技能（SKILL.md 格式）
│   ├── xianyu-publish/          # 商品发布技能
│   ├── xianyu-manage/           # 商品管理技能
│   ├── xianyu-content/          # AI 文案生成技能
│   ├── xianyu-metrics/          # 数据分析技能
│   └── xianyu-accounts/         # 账号管理技能
├── src/                         # Python 业务逻辑
│   ├── cli.py                   # CLI 入口（供 Agent 调用）
│   ├── core/                    # 核心模块
│   │   ├── browser_client.py    # OpenClaw Gateway 浏览器客户端
│   │   ├── config.py            # 配置管理
│   │   ├── crypto.py            # Cookie 加密
│   │   ├── logger.py            # 日志
│   │   └── startup_checks.py    # 启动检查
│   └── modules/                 # 业务模块
│       ├── listing/             # 商品发布
│       ├── operations/          # 运营操作
│       ├── analytics/           # 数据分析
│       ├── accounts/            # 账号管理
│       ├── content/             # AI 内容生成
│       └── media/               # 图片处理
├── config/                      # 配置文件
│   ├── config.example.yaml      # 应用配置模板
│   └── openclaw.example.json    # OpenClaw 配置模板
├── scripts/
│   └── init.sh                  # Docker 初始化脚本
├── docker-compose.yml           # Docker 编排
├── requirements.txt             # Python 依赖
├── .env.example                 # 环境变量模板
├── USER_GUIDE.md                # 使用说明书
└── README.md
```

---

## 获取闲鱼 Cookie

1. 用 Chrome 打开 https://www.goofish.com 并登录
2. 按 F12 打开开发者工具
3. 切换到 Network 标签
4. 刷新页面，点击任意请求
5. 在 Request Headers 中找到 Cookie 行，全部复制
6. 粘贴到 `.env` 文件的 `XIANYU_COOKIE_1`

> Cookie 有效期通常 7-30 天，过期后需要重新获取。

---

## 常用命令

```bash
# 启动
docker compose up -d

# 查看日志
docker compose logs -f

# 停止
docker compose down

# 重建（更新镜像后）
docker compose pull && docker compose up -d
```

---

## 与 OpenClaw 的关系

本项目是 OpenClaw 的一组 **Skills**（技能扩展）。OpenClaw 提供：

- AI Agent 对话引擎
- 浏览器自动化（Managed Chromium via CDP）
- Web UI
- Gateway API

本项目提供：

- 闲鱼业务逻辑（发布、擦亮、调价等）
- 数据分析和报表
- 多账号管理
- Cookie 加密存储

当 OpenClaw 更新时（新的 AI 模型支持、浏览器引擎升级、新的 tool 能力），只需要 `docker compose pull` 即可获得更新，闲鱼业务逻辑不受影响。

---

## 更新日志

### v4.0.0 (2026-02-23) - OpenClaw 深度集成

- 浏览器自动化从 Playwright 迁移到 OpenClaw Gateway Browser API
- 删除 Streamlit/FastAPI Web 界面，改用 OpenClaw 自带 AI 对话 UI
- 所有 Skills 重写为 OpenClaw 标准 SKILL.md 格式
- 新增 CLI 入口 (`src/cli.py`) 供 Agent 调用
- Docker 一键部署使用 `coollabsio/openclaw` 官方镜像
- 可跟随 OpenClaw 社区更新获得新能力

### v3.0.0 (2026-02-23) - 生产可用性改造

- Playwright 实现替代空壳 HTTP API
- 安全加固（CORS、速率限制、Cookie 加密）
- Docker 容器化、启动健康检查

---

## License

MIT License - 详见 [LICENSE](LICENSE)

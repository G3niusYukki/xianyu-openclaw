<p align="center">
  <img src="https://img.shields.io/badge/🐟-闲鱼_OpenClaw-FF6A00?style=for-the-badge&labelColor=1a1a2e" alt="闲鱼 OpenClaw" />
</p>

<h1 align="center">xianyu-openclaw</h1>

<p align="center">
  <strong>用对话代替点击，AI 帮你打理闲鱼店铺。</strong>
</p>

<p align="center">
  <a href="https://github.com/G3niusYukki/xianyu-openclaw/releases/latest"><img src="https://img.shields.io/github/v/release/G3niusYukki/xianyu-openclaw?style=flat-square&color=FF6A00" alt="Release" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" alt="License" /></a>
  <a href="https://github.com/G3niusYukki/xianyu-openclaw/actions"><img src="https://img.shields.io/github/actions/workflow/status/G3niusYukki/xianyu-openclaw/ci.yml?style=flat-square&label=CI" alt="CI" /></a>
  <a href="https://github.com/G3niusYukki/xianyu-openclaw/stargazers"><img src="https://img.shields.io/github/stars/G3niusYukki/xianyu-openclaw?style=flat-square" alt="Stars" /></a>
  <a href="https://github.com/G3niusYukki/xianyu-openclaw/issues"><img src="https://img.shields.io/github/issues/G3niusYukki/xianyu-openclaw?style=flat-square" alt="Issues" /></a>
</p>

<p align="center">
  <a href="#快速开始">快速开始</a> •
  <a href="#功能特性">功能特性</a> •
  <a href="#系统架构">系统架构</a> •
  <a href="#技能列表">技能列表</a> •
  <a href="USER_GUIDE.md">零基础使用指南</a> •
  <a href="CONTRIBUTING.md">参与贡献</a>
</p>

---

## 4.1.0 更新摘要（2026-02-27）

- 完成全量历史质量清理：`ruff check src tests` 通过，测试体系与现有架构对齐。
- 修复关键运行时缺陷：调度器 BrowserClient 注入、监控 await 修复、分析周报表缺失修复。
- 落地增强版合规护栏：支持 `warn/block` 双模式、规则自动重载、发布与运营链路审计日志。
- 统一技能路线：以 `SKILL.md + CLI` 为唯一执行路径，旧 `skills/xianyu_*` Python 包标记为废弃兼容层。

## 为什么做这个？

经营闲鱼店铺，每天都在重复同样的事：发商品、写标题、擦亮、调价、看数据。一天下来光点按钮就要花好几个小时。

**xianyu-openclaw 把这一切变成了对话：**

```
你: 帮我发布一个 iPhone 15 Pro，价格 5999，95新
AI: ✅ 已发布！标题：【自用出】iPhone 15 Pro 256G 原色钛金属 95新
    链接：https://www.goofish.com/item/xxx

你: 擦亮所有商品
AI: ✅ 已擦亮 23 件商品

你: 今天运营数据怎么样？
AI: 📊 今日浏览 1,247 | 想要 89 | 成交 12 | 营收 ¥38,700
```

基于 [OpenClaw](https://github.com/openclaw/openclaw) 开源 AI Agent 框架构建。OpenClaw 升级时，你的闲鱼工具也跟着升级。

---

<h2 id="功能特性">功能特性</h2>

| | 功能 | 说明 |
|---|------|------|
| 🤖 | **自然语言操控** | 用中文跟 AI 对话，告别繁琐的界面操作 |
| 📦 | **智能发布** | AI 自动生成标题、描述、标签，针对闲鱼 SEO 优化 |
| ✨ | **一键擦亮** | 一句话批量擦亮全部商品，模拟人工随机间隔 |
| 💰 | **价格管理** | 单个调价、批量调价、智能定价策略 |
| 📊 | **数据分析** | 每日报告、趋势分析、CSV 导出 |
| 👥 | **多账号管理** | 同时管理多个闲鱼账号，Cookie 加密存储 |
| 🔒 | **安全优先** | AES 加密 Cookie、参数化 SQL、请求限速 |
| 🐳 | **一键部署** | `docker compose up -d` 搞定一切 |
| 🔌 | **插件化架构** | 5 个独立 OpenClaw 技能模块，易于扩展 |

---

<h2 id="快速开始">快速开始</h2>

### 准备工作

- [Docker](https://docs.docker.com/get-docker/)（20.10+）
- AI API 密钥 — [Anthropic](https://console.anthropic.com/)（推荐）/ [OpenAI](https://platform.openai.com/) / [DeepSeek](https://platform.deepseek.com/)（最便宜）
- 闲鱼账号 Cookie（[获取方法](#获取闲鱼-cookie)）

### 三步启动

```bash
# 1. 克隆
git clone https://github.com/G3niusYukki/xianyu-openclaw.git
cd xianyu-openclaw

# 2. 配置
cp .env.example .env
# 编辑 .env，填入 AI 密钥、闲鱼 Cookie 和密码

# 3. 启动
docker compose up -d
```

打开 **http://localhost:8080** ，开始跟你的闲鱼 AI 助手对话。

---

<h2 id="系统架构">系统架构</h2>

```
┌─────────────────────────────────────────────────┐
│               用户（对话界面）                     │
│            http://localhost:8080                 │
└──────────────────────┬──────────────────────────┘
                       │ 自然语言
                       ▼
┌──────────────────────────────────────────────────┐
│              OpenClaw Gateway                     │
│      AI Agent  ·  技能路由  ·  Web UI             │
│                  :18789                           │
└──────┬──────────────┬──────────────┬─────────────┘
       │              │              │
       ▼              ▼              ▼
  ┌─────────┐  ┌───────────┐  ┌───────────┐
  │  商品   │  │   运营    │  │   数据    │  … 共 5 个技能
  │  发布   │  │   管理    │  │   分析    │
  └────┬────┘  └─────┬─────┘  └─────┬─────┘
       │             │              │
       ▼             ▼              ▼
  ┌──────────────────────────────────────────┐
  │        Python CLI（src/cli.py）           │
  │   发布服务 · 运营服务 · 分析服务 · 账号服务  │
  └──────────────────┬───────────────────────┘
                     │ HTTP
                     ▼
  ┌──────────────────────────────────────────┐
  │    OpenClaw 托管浏览器（CDP 协议）         │
  │        headless Chromium :18791          │
  └──────────────────┬───────────────────────┘
                     │
                     ▼
              goofish.com 🐟
```

**v4 之前**: 用户 → Streamlit 界面 → FastAPI → Playwright → Chromium
**v4 之后**: 用户 → OpenClaw 对话 → 技能 → CLI → Gateway 浏览器 API → 托管 Chromium

---

<h2 id="技能列表">技能列表</h2>

每个技能是一个独立的 [OpenClaw Skill](https://docs.openclaw.ai/skills/)，通过 `SKILL.md` 定义：

| 技能 | 功能 | 对话示例 |
|------|------|---------|
| `xianyu-publish` | 发布商品，AI 自动生成文案 | "发布一个 AirPods Pro，800 元" |
| `xianyu-manage` | 擦亮 / 调价 / 下架 / 上架 | "擦亮所有商品" |
| `xianyu-content` | 生成 SEO 标题和描述 | "帮我写个 MacBook 的标题" |
| `xianyu-metrics` | 仪表盘、日报、趋势图 | "这周浏览量趋势" |
| `xianyu-accounts` | 健康检查、Cookie 刷新 | "Cookie 还有效吗" |

### CLI 接口

技能通过 CLI 调用 Python 后端，所有命令输出结构化 JSON：

```bash
python -m src.cli publish  --title "..." --price 5999 --tags 95新 国行
python -m src.cli polish   --all --max 50
python -m src.cli price    --id item_123 --price 4999
python -m src.cli delist   --id item_123
python -m src.cli relist   --id item_123
python -m src.cli analytics --action dashboard
python -m src.cli accounts  --action list
```

---

<h2 id="获取闲鱼-cookie">获取闲鱼 Cookie</h2>

<details>
<summary><strong>展开查看详细步骤</strong></summary>

1. 用 Chrome 打开 **https://www.goofish.com** 并登录
2. 按 **F12** 打开开发者工具
3. 切换到 **Network（网络）** 标签
4. 按 **F5** 刷新页面
5. 点击左侧任意一个请求
6. 在右侧 **Request Headers** 中找到 `Cookie:` 一行
7. 全部复制
8. 粘贴到 `.env` 文件的 `XIANYU_COOKIE_1=...`

> Cookie 有效期通常 7–30 天，过期后工具会提醒你更新。

</details>

---

## 配置说明

## 合规边界

- 工具只支持闲鱼站内合规交易，不应发布违法、侵权、仿冒或导流到站外的信息。
- 默认启用最小合规护栏：内容禁词拦截、发布频率限制、批量擦亮冷却、审计日志记录。
- 规则文件为 `config/rules.yaml`，支持 `mode: block|warn`。`block` 会拒绝执行，`warn` 仅告警并继续执行。
- 命中规则会记录审计事件：`COMPLIANCE_BLOCK` 或 `COMPLIANCE_WARN`，并支持规则文件自动重载。

<details>
<summary><strong><code>.env</code> 环境变量</strong></summary>

| 变量名 | 必填 | 说明 |
|--------|------|------|
| `ANTHROPIC_API_KEY` | 三选一 | Anthropic API 密钥 |
| `OPENAI_API_KEY` | 三选一 | OpenAI API 密钥 |
| `DEEPSEEK_API_KEY` | 三选一 | DeepSeek API 密钥（最便宜） |
| `OPENCLAW_GATEWAY_TOKEN` | 是 | Gateway 认证令牌（随便设一个） |
| `AUTH_PASSWORD` | 是 | Web 界面登录密码 |
| `XIANYU_COOKIE_1` | 是 | 闲鱼会话 Cookie |
| `XIANYU_COOKIE_2` | 否 | 第二个账号的 Cookie |
| `ENCRYPTION_KEY` | 否 | Cookie 加密密钥（留空自动生成） |

</details>

<details>
<summary><strong>OpenClaw 配置（<code>config/openclaw.example.json</code>）</strong></summary>

```json
{
  "browser": {
    "enabled": true,
    "defaultProfile": "openclaw",
    "headless": true,
    "noSandbox": true
  }
}
```

</details>

---

## 项目结构

```
xianyu-openclaw/
├── skills/                      # 5 个 OpenClaw 技能（SKILL.md 格式）
│   ├── xianyu-publish/          # 商品发布
│   ├── xianyu-manage/           # 运营管理
│   ├── xianyu-content/          # AI 文案生成
│   ├── xianyu-metrics/          # 数据分析
│   └── xianyu-accounts/         # 账号管理
├── src/
│   ├── cli.py                   # CLI 入口（Agent ↔ 服务层）
│   ├── core/
│   │   ├── browser_client.py    # OpenClaw Gateway 浏览器 HTTP 客户端
│   │   ├── config.py            # YAML 配置加载
│   │   ├── crypto.py            # AES Cookie 加密
│   │   ├── error_handler.py     # 统一错误处理
│   │   ├── logger.py            # 结构化日志（loguru）
│   │   └── startup_checks.py    # 启动健康检查
│   └── modules/
│       ├── listing/             # 商品发布服务
│       ├── operations/          # 擦亮、调价、下架
│       ├── analytics/           # 数据分析（SQLite）
│       ├── accounts/            # 多账号与 Cookie 管理
│       ├── content/             # AI 内容生成
│       └── media/               # 图片处理（Pillow）
├── config/                      # 配置模板
├── scripts/init.sh              # Docker 容器 Python 环境初始化
├── docker-compose.yml           # 一键部署
├── requirements.txt             # Python 依赖
└── .env.example                 # 环境变量模板
```

---

## 本地开发

```bash
git clone https://github.com/G3niusYukki/xianyu-openclaw.git
cd xianyu-openclaw
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# CLI
python -m src.cli --help

# 测试
pytest tests/

# 代码检查
ruff check src/
```

---

## 与 OpenClaw 的关系

本项目是 [OpenClaw](https://github.com/openclaw/openclaw) AI Agent 框架的一组**技能插件**：

| 层级 | 提供方 |
|------|--------|
| AI Agent 和对话界面 | OpenClaw |
| 浏览器自动化（CDP） | OpenClaw |
| Gateway API | OpenClaw |
| **闲鱼业务逻辑** | **本项目** |
| **数据分析和报表** | **本项目** |
| **多账号管理** | **本项目** |

当 OpenClaw 发布更新（新 AI 模型、浏览器引擎升级、新工具能力），只需要：

```bash
docker compose pull && docker compose up -d
```

闲鱼业务逻辑不受影响。

---

## 路线图

- [ ] 定时自动擦亮（cron 调度）
- [ ] 基于数据分析的智能定价建议
- [ ] 竞品监控
- [ ] Telegram / 微信通知推送
- [ ] 闲鱼消息自动回复
- [ ] 多语言支持

---

## 参与贡献

欢迎贡献代码！请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 安全问题

发现漏洞？请私下报告 — 详见 [SECURITY.md](SECURITY.md)。

## 开源许可

[MIT](LICENSE) — 随便用，随便改，拿去卖鱼也行。🐟

---

<p align="center">
  <sub>用 🐟 和 ☕ 构建 by <a href="https://github.com/G3niusYukki">@G3niusYukki</a></sub>
</p>

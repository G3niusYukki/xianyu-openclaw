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

## 4.8.0 更新摘要（2026-02-27）

- **Lite 运行时**：支持 Playwright 本地浏览器，无需 OpenClaw Gateway 即可运行（`runtime: lite`）。
- **模块化启动**：`module` 命令支持按模块独立启动（售前/运营/售后），后台运行与状态管理。
- **飞书告警通知**：Workflow 启动/心跳/SLA 告警与恢复消息推送到飞书机器人。
- **自检增强**：`doctor --strict` 严格模式，支持 `skip-gateway`/`skip-quote` 跳过特定检查。
- **自动化配置**：`automation` 命令一键配置轮询参数与飞书 webhook。
- **Windows 一键脚本**：新增 16 个 `.bat` 脚本，支持 launcher 菜单、lite 快速启动、模块管理。
- **报价 KPI 修复**：被合规拦截的报价不计入成功，新增 `quote_blocked_by_policy` 追溯字段。

## 4.7.0 更新摘要（2026-02-27）

- **两阶段报价工作流**：询价消息先发快速确认（1-3s 内），再异步发送精确报价，保证首响 SLA。
- **报价多源容灾**：成本源优先级 API → 热缓存 → 本地成本表 → 兜底模板，熔断与半开恢复，报价快照追溯。
- **合规跟进引擎**：已读未回场景的自动跟进，支持每日上限、冷却间隔、静默时段、DND 退订、审计回放。
- **零门槛诊断**：`python -m src.cli doctor` 一键检查 Python/Docker/配置/端口/依赖，输出修复建议。
- **CLI 增强**：新增 `followup` 命令管理跟进策略与 DND 列表。

## 4.6.0 更新摘要（2026-02-27）

- 一站式部署向导升级：网关 AI 与业务文案 AI 分离配置，自动生成 token 与启动后健康检查。
- 修复部署目录错配：`/data/workspace` 与 `/data/.openclaw` 挂载增强，避免状态目录分裂。
- 新增国产模型 API 接入：DeepSeek、阿里百炼、火山方舟、MiniMax、智谱（OpenAI 兼容模式）。
- `ContentService` 支持 `AI_PROVIDER/AI_API_KEY/AI_BASE_URL/AI_MODEL` 统一配置链路。
- 文档补齐首启配对与网关鉴权故障排查，降低首次部署失败率。

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
| 💬 | **消息自动回复 + 自动报价** | 询价识别、缺参补问、结构化报价、失败降级与合规回复 |
| ⚡ | **两阶段报价工作流** | 首响 1-3s 快速确认 + 异步精确报价，保证 SLA |
| 🔄 | **报价多源容灾** | API → 热缓存 → 成本表 → 兜底模板，熔断与追溯 |
| 📢 | **合规跟进引擎** | 已读未回自动跟进，频次上限、静默时段、DND 退订 |
| 🛡️ | **合规策略中心** | 账号级/会话级分级规则、发送前拦截、审计回放 |
| 📦 | **订单履约闭环（MVP）** | 下单状态映射、虚拟/实物交付动作、售后模板、人工接管与追溯 |
| ⚙️ | **常驻 Workflow Worker** | 7x24 轮询处理、幂等去重、崩溃恢复、人工接管跳过 |
| 📈 | **运营 SLA 监控** | 首响 P95 / 报价成功率 / 报价回退率采集与阈值告警 |
| 🧪 | **增长实验与漏斗** | A/B 分流、策略版本管理、漏斗统计、显著性检验 |
| 💸 | **AI 降本治理** | `always/auto/minimal`、任务级开关、预算与缓存、调用成本统计 |
| 📊 | **数据分析** | 每日报告、趋势分析、CSV 导出 |
| 👥 | **多账号管理** | 同时管理多个闲鱼账号，Cookie 加密存储 |
| 🔒 | **安全优先** | AES 加密 Cookie、参数化 SQL、请求限速 |
| 🐳 | **一键部署** | `docker compose up -d` 搞定一切 |
| 🔌 | **插件化架构** | 5 个独立 OpenClaw 技能模块，易于扩展 |

---

<h2 id="快速开始">快速开始</h2>

### 准备工作

- [Docker](https://docs.docker.com/get-docker/)（20.10+）
- 网关 AI Key（必填，支持 Anthropic / OpenAI / Moonshot(Kimi) / MiniMax / ZAI）
- 业务文案 AI Key（可选，支持 DeepSeek / 阿里百炼 / 火山方舟 / MiniMax / 智谱）
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

### 一键部署向导（推荐）

如果你不想手动编辑 `.env`，可以直接运行交互式向导。向导会分开配置「网关模型」和「业务文案模型」，并做启动后健康检查：

```bash
python3 -m src.setup_wizard
# 或
./scripts/one_click_deploy.sh
```

---

### 后台数据可视化

项目内置了轻量后台页面（本地 Web）：

```bash
python3 -m src.dashboard_server --port 8091
```

打开 **http://localhost:8091** 可查看：
- 总操作数 / 今日操作 / 在售商品等核心指标
- 近 30 天趋势图
- 最近操作日志
- 商品表现 Top 列表

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
python -m src.cli messages  --action auto-reply --limit 20 --dry-run
python -m src.cli messages  --action auto-workflow --dry-run
python -m src.cli messages  --action workflow-stats --window-minutes 60
python -m src.cli orders    --action upsert --order-id o1 --status 已付款 --session-id s1
python -m src.cli orders    --action deliver --order-id o1 --item-type virtual
python -m src.cli orders    --action trace --order-id o1
python -m src.cli compliance --action check --content "加我微信聊" --account-id account_1 --session-id s1
python -m src.cli compliance --action replay --blocked-only --limit 20
python -m src.cli growth    --action assign --experiment-id exp_reply --subject-id s1 --variants A,B
python -m src.cli growth    --action funnel --days 7 --bucket day
python -m src.cli ai        --action cost-stats
python -m src.cli doctor    --strict
python -m src.cli followup  --action check --session-id s1
python -m src.cli followup  --action dnd-add --session-id s1 --reason "user_reject"
python -m src.cli followup  --action audit --limit 20
python -m src.cli automation --action setup --enable-feishu --feishu-webhook "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
python -m src.cli automation --action status
python -m src.cli automation --action test-feishu
python -m src.cli module --action check  --target all --strict
python -m src.cli module --action status --target all --window-minutes 60
python -m src.cli module --action start  --target presales   --mode daemon --limit 20 --interval 5
python -m src.cli module --action start  --target operations --mode daemon --init-default-tasks --interval 30
python -m src.cli module --action start  --target aftersales --mode daemon --limit 20 --interval 15 --issue-type delay
python -m src.cli module --action start  --target all --mode daemon --background
python -m src.cli module --action stop   --target all
python -m src.cli module --action logs   --target all --tail-lines 80
python -m src.dashboard_server --port 8091
```

### 消息自动回复策略（虚拟商品 + 快递自动报价）

`messages` 配置支持“意图规则 + 关键词兼容”两层策略，默认已内置常见虚拟商品场景：

```yaml
messages:
  enabled: true
  fast_reply_enabled: true
  reply_target_seconds: 3.0
  reuse_message_page: true
  first_reply_delay_seconds: [0.25, 0.9]
  inter_reply_delay_seconds: [0.4, 1.2]
  send_confirm_delay_seconds: [0.15, 0.35]
  quote_intent_keywords: ["报价", "多少钱", "运费", "寄到"]
  quote_missing_template: "为了给您准确报价，请补充：{fields}。"
  quote_failed_template: "报价服务暂时繁忙，我先帮您转人工确认，确保价格准确。"
  reply_prefix: "【自动回复】"
  default_reply: "您好，宝贝在的，感兴趣可以直接拍下。"
  virtual_default_reply: "在的，这是虚拟商品，拍下后会尽快在聊天内给你处理结果。"
  virtual_product_keywords: ["虚拟", "卡密", "激活码", "兑换码", "CDK", "代下单", "代充", "代订"]
  intent_rules:
    - name: "card_code_delivery"
      priority: 10
      keywords: ["卡密", "兑换码", "激活码", "CDK", "授权码"]
      reply: "这是虚拟商品，付款后会通过平台聊天发卡密/兑换信息，请按商品说明使用。"
    - name: "online_fulfillment"
      priority: 20
      keywords: ["代下单", "代拍", "代充", "代购", "代订"]
      reply: "支持代下单服务，请把具体需求、数量和时效发我，我确认后马上安排。"
  workflow:
    db_path: "data/workflow.db"
    poll_interval_seconds: 5
    scan_limit: 20
    claim_limit: 10
    lease_seconds: 60
    max_attempts: 3
    backoff_seconds: 2
    sla:
      window_minutes: 60
      min_samples: 5
      reply_p95_threshold_ms: 3000
      quote_success_rate_threshold: 0.98

quote:
  enabled: true
  mode: "hybrid"
  ttl_seconds: 90
  max_stale_seconds: 300
  timeout_ms: 3000
  retry_times: 2
  circuit_fail_threshold: 3
  circuit_open_seconds: 30
  providers:
    remote:
      enabled: false
```

### 分级合规策略（账号级 + 会话级）

策略文件默认路径：`config/compliance_policies.yaml`。支持 `global -> accounts -> sessions` 覆盖。

- `global.stop_words`: 高风险词默认阻断（如站外导流）。
- `global.blacklist`: 命中直接拦截。
- `rate_limit.account/session`: 账号级和会话级限流。
- 所有外发前检查均写入审计库：`data/compliance.db`，可通过 `compliance --action replay` 回放。

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
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `MOONSHOT_API_KEY` / `MINIMAX_API_KEY` / `ZAI_API_KEY` | 五选一 | 网关启动所需 AI Key（至少一个） |
| `AI_PROVIDER` | 否 | 业务文案模型供应商（如 `deepseek` / `aliyun_bailian` / `volcengine_ark`） |
| `AI_API_KEY` | 否 | 业务文案模型 API Key |
| `AI_BASE_URL` | 否 | 业务文案模型 Base URL（OpenAI 兼容） |
| `AI_MODEL` | 否 | 业务文案模型名 |
| `DEEPSEEK_API_KEY` / `DASHSCOPE_API_KEY` / `ARK_API_KEY` / `ZHIPU_API_KEY` | 否 | 国产模型供应商专用 Key（可按需填写） |
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
│       ├── media/               # 图片处理（Pillow）
│       ├── messages/            # 自动回复与询价分流
│       ├── quote/               # 自动报价引擎与 provider 适配层
│       ├── followup/            # 合规跟进引擎（已读未回场景）
│       └── orders/              # 订单履约服务
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

若首次访问出现 `pairing required`：

```bash
docker compose exec -it openclaw-gateway openclaw devices list
docker compose exec -it openclaw-gateway openclaw devices approve <requestId>
```

闲鱼业务逻辑不受影响。

---

## 路线图

- [ ] 定时自动擦亮（cron 调度）
- [ ] 基于数据分析的智能定价建议
- [ ] 竞品监控
- [ ] Telegram / 微信通知推送
- [x] 闲鱼消息自动回复
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

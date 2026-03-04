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

## 项目进度看板（2026-03-02）

> 当前阶段：**模块化重构 + 小白部署体验收口**

- **总体进度：78%**
- **可运行主线：已打通**（询价回复 / 催付 / Cookie 自动续期 / WS 重连 / 回归自检）
- **本周重点：全本地、零代码、Mac/Windows 统一部署体验**

### 功能状态（业务视角）

| 功能 | 状态 | 说明 |
|---|---|---|
| 回复询价 | ✅ 已完成 | 支持意图识别、缺参追问、模板化回复 |
| 催付 | ✅ 已完成 | 支持待支付提醒与多阶段触达 |
| 自动续期 | ✅ 已完成 | Cookie 自动抓取、预校验、热更新、重连恢复 |
| 自动改价执行 | 🟡 进行中 | 策略可用，正式执行链路收口中 |
| 订单履约（虚拟商品） | 🟡 进行中 | 流程可跑，回调幂等/补偿待封板 |
| 售后自动化 | 🟡 进行中 | 规则边界已定，工单路由待上线 |
| 新手引导 UI | 🟡 进行中 | 方案已出，前端实现与验收中 |
| 一键部署（Mac/Win） | ✅ 已完成 | Windows EXE 图形化向导已发布 |

### 本期硬约束（企业级执行）

1. **全本地运行**（不依赖云端业务服务）
2. **零代码部署**（不懂代码用户可独立完成首启）
3. **新手引导完整**（首次安装、任务式引导、诊断闭环）
4. **超边界转人工**（电话沟通、转账退款、纠纷仲裁）

---

## 6.2.0 更新摘要（2026-03-04）

- **报价 Mock 门禁（生产保护）**：
  - `doctor --strict` / 启动检查新增 gate，生产环境若检测到 `quote.providers.remote.allow_mock=true` 将直接阻断启动
  - 确保生产环境不会误用 mock 报价数据
- **订单回调幂等（external_event_id）**：
  - 回调支持按 `external_event_id` 去重，重复推送可安全回放
  - 新增迁移 `database/migrations/20260304_add_order_callback_dedup.sql`
  - 新增回放脚本 `scripts/replay_external_event_id.py`
- **并发加固**：
  - 改价执行 `PriceExecutionService` 使用 CAS 门控避免重复执行
  - Workflow claim/complete/fail 增加 CAS gate，减少并发重入/竞态
  - Lite 去重写入改为原子插入，避免并发 unique 竞态
- **发布证据包**：
  - 新增 `docs/release/evidence/` 发布门禁证据包
  - 新增 `docs/reviews/xianyu-deep-audit-2026-03-03/` 架构审计文档
  - 新增 `docs/qa/minimal-e2e-gate-template.md` 最小E2E闭环模板

## 6.1.0 更新摘要（2026-03-03）

- **Windows 一键部署工具**：
  - 新增图形化部署向导（`src/windows_launcher.py`），支持打包为 Windows EXE
  - 分步配置：Docker 检测 → AI 服务选择 → 认证设置 → Cookie 粘贴 → 一键部署
  - 零命令行操作，完全小白友好
  - 构建脚本：`scripts\windows\build_exe.bat` 一键生成 EXE

## 6.0.0 更新摘要（2026-03-02）

- **闲管家开放平台接入**：
  - 新增统一签名与 API 客户端，支持商品改价、订单改价、物流发货、快递公司查询。
  - `OperationsService.update_price(...)` 现支持"闲管家 API 优先，DOM 自动回退"。
  - `OrderFulfillmentService.deliver(...)` 现支持实物订单自动物流发货，失败自动降级为人工发货任务。
- **CLI 发货升级**：
  - `orders --action deliver` 新增物流单号、快递公司、寄件信息和闲管家凭证参数，可直接走物流发货。
- **发布级稳定性修复**：
  - 修复 `MediaService.add_watermark()` 在 `watermark: null` 配置下导致 CI 测试失败的问题。

## 5.3.0 更新摘要（2026-03-02）

- **Lite 直连模式**：新增 `python -m src.lite` 轻量运行时，支持直连 Goofish WebSocket 收发消息、双层去重、自动回复与自动报价。
- **报价地理匹配升级**：
  - 新增省市解析与三级模糊匹配，支持省/市混合输入。
  - 成本表结果新增 `source_excel` 与 `matched_route`，便于追溯命中来源。
  - 新增自适应 Excel 导入器，支持列名变体识别与快递公司自动识别。
- **真实报价表兼容修复**：
  - 修复自治区名称在导入时被截断的问题（如 `广西壮族自治区` 现在会正确归一为 `广西`）。
  - 修复纯城市级线路表对"市 -> 省"查询的命中能力。
- **消息/运行时增强**：
  - 新增规则优先的信息抽取、禁寄安全校验、会话级人工接管状态存储。
  - WS 事件等待逻辑更稳，避免等待任务悬挂。
- **Dashboard 上传修复**：修复 Python 3.13+/3.14 下 multipart 解析，上传附件能正确读取文件内容。

## 5.2.0 更新摘要（2026-03-01）

- **Cookie 健康监控**：定时探测 Cookie 有效性，失效立即飞书告警，恢复后通知
  - `doctor --strict` 新增在线 Cookie 有效性诊断
  - `module --action cookie-health` 手动检查
- **macOS 开机自启**：launchd 守护进程，系统重启/崩溃自动恢复
  - `scripts/macos/install_service.sh install` 一键安装
- **SQLite WAL 模式**：WorkflowStore 和 DashboardRepository 启用 WAL + busy_timeout，提升并发写入稳定性
- **数据自动备份**：`scripts/backup_data.sh`，支持 7 天自动轮转
- **Dashboard /healthz 端点**：返回系统健康状态 JSON，供外部监控探测

## 5.1.0 更新摘要（2026-02-28）

- **售前会话流程优化**：
  - 对齐业务模型：报价 → 选择快递 → 下单（不支付）→ 卖家改价 → 买家支付 → 自动兑换码
  - 移除选择快递后的地址/电话收集分支，替换为结账引导回复
  - 新增会话上下文记忆，用于后续报价解析（origin/destination/weight/courier choice）
- **新增配置项**：
  - `force_non_empty_reply`：确保回复不为空
  - `non_empty_reply_fallback`：空回复时的后备内容
  - `context_memory_enabled`：启用会话上下文记忆
  - `context_memory_ttl_seconds`：上下文记忆 TTL
  - `courier_lock_template`：快递锁定回复模板

## 5.0.0 更新摘要（2026-02-28）

- **售前运行时强化**：
  - 新增 `module recover` 动作，一键停止→清理→重启模块
  - 新增平台启动脚本（macOS/Linux/Windows）
  - 强化运行时/浏览器解析检查和 doctor 覆盖
- **Dashboard 改进**：
  - 更强的状态/风险/恢复信号处理
  - 更清晰的模板说明和 Cookie 诊断反馈
  - 新增 Cookie 导入域名过滤，避免无效字段
- **报价模板优化**：
  - 标准化的首次响应格式，询价收集更高效
  - 报价模板接入实际回复渲染路径
  - 支持 legacy template 占位符别名（`origin_province`, `dest_province`, `billing_weight` 等）
- **认证稳定性增强**：
  - 新增 `auth_hold_until_cookie_update` 配置项
  - 优先使用环境变量 `XIANYU_COOKIE_1` 避免 WS 认证振荡
  - 认证失败后停止激进重试，等待 Cookie 更新
- **测试端点对齐**：
  - Dashboard `/api/test-reply` 与实际生产流程保持一致

## 4.9.0 更新摘要（2026-02-28）

- **严格标准格式回复**：对非标准买家消息强制标准格式回复，支持问候语触发
- **WS-first 运行时强化**：
  - WS 就绪内省 (`is_ready`)
  - `transport=ws` 保持 WS-only（无 DOM 回退）
  - DOM 回退仅保留给 `transport=auto`
- **Cookie 健壮性增强**：更安全的 cookie 解析，支持多种输入格式
- **AI Provider Key 安全解析**：避免跨 provider key 误用
- **报价回复规范化**：统一报价模板，ETA 以天显示

## 4.8.0 更新摘要（2026-02-27）

- **Lite 运行时**：支持 Playwright 本地浏览器，无需 OpenClaw Gateway 即可运行（`runtime: lite`）。
- **模块化启动**：`module` 命令支持按模块独立启动（售前/运营/售后），后台运行与状态管理。
- **飞书告警通知**：Workflow 启动/心跳/SLA 告警与恢复消息推送到飞书机器人。
- **自检增强**：`doctor --strict` 严格模式，支持 `skip-gateway`/`skip-quote` 跳过特定检查。
- **自动化配置**：`automation` 命令一键配置轮询参数与飞书 webhook。
- **Windows 一键脚本**：新增 16 个 `.bat` 脚本，支持 launcher 菜单、lite 快速启动、模块管理。
- **报价 KPI 修复**：被合规拦截的报价不计入成功，新增 `quote_blocked_by_policy` 追溯字段。
- **CI 收敛**：CI workflow 改为聚焦真实阻断问题（导入/重复定义/运行错误），避免纯样式噪音导致发布阻塞。

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
| 🛡️ | **合规策略中心** | 账号级/会话级分级规则、发送前拦截、审计回放 |
| 📦 | **订单履约闭环（MVP）** | 下单状态映射、虚拟/实物交付动作、售后模板、人工接管与追溯 |
| ⚙️ | **常驻 Workflow Worker** | 7x24 轮询处理、幂等去重、崩溃恢复、人工接管跳过 |
| 📈 | **运营 SLA 监控** | 首响 P95 / 报价成功率 / 报价回退率采集与阈值告警 |
| 🧪 | **增长实验与漏斗** | A/B 分流、策略版本管理、漏斗统计、显著性检验 |
| 💸 | **AI 降本治理** | `always/auto/minimal`、任务级开关、预算与缓存、调用成本统计 |
| 🔔 | **飞书告警通知** | Workflow 启动/心跳/SLA 告警与恢复消息推送 |
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

Windows 可执行：

```bat
scripts\windows\setup_windows.bat
# 一键：安装依赖 + 严格自检 + 启动容器
scripts\windows\quickstart.bat
```

### Windows 一键部署工具（EXE）

不想装 Python？直接下载 EXE：

1. 从 [Releases](https://github.com/G3niusYukki/xianyu-openclaw/releases/latest) 下载 `xianyu-openclaw-launcher.zip`
2. 解压到任意位置
3. 双击 `xianyu-openclaw-launcher.exe`
4. 按向导步骤填写 AI 密钥、Cookie 等信息
5. 点击"生成配置并启动"

> 前提：需要先安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)。向导会自动检测并引导安装。

自行构建 EXE：

```bat
scripts\windows\build_exe.bat
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
python -m src.cli module --action recover --target presales --stop-timeout 6
python -m src.cli module --action logs   --target all --tail-lines 80
python -m src.dashboard_server --port 8091
```

Windows 可直接按模块启动：

```bat
scripts\windows\launcher.bat
scripts\windows\lite_quickstart.bat
scripts\windows\module_check.bat
scripts\windows\module_status.bat
scripts\windows\start_all_lite.bat
scripts\windows\start_presales.bat daemon 20 5
scripts\windows\start_operations.bat daemon 30
scripts\windows\start_aftersales.bat daemon 20 15 delay
scripts\windows\module_recover.bat presales
```

macOS/Linux 可用轻量脚本：

```bash
scripts/unix/dashboard.sh 8091
scripts/unix/start_all_lite.sh
scripts/unix/recover_presales.sh
```

### 消息自动回复策略（虚拟商品 + 快递自动报价）

`messages` 配置支持“意图规则 + 关键词兼容”两层策略，默认已内置常见虚拟商品场景：

```yaml
messages:
  enabled: true
  transport: "ws"   # dom | ws | auto
  ws:
    base_url: "wss://wss-goofish.dingtalk.com/"
    heartbeat_interval_seconds: 15
    reconnect_delay_seconds: 3.0
  fast_reply_enabled: true
  reply_target_seconds: 3.0
  reuse_message_page: true
  first_reply_delay_seconds: [0.25, 0.9]
  inter_reply_delay_seconds: [0.4, 1.2]
  send_confirm_delay_seconds: [0.15, 0.35]
  quote_intent_keywords: ["报价", "多少钱", "运费", "寄到"]
  quote_missing_template: "询价格式：xx省 - xx省 - 重量（kg）\n长宽高（单位cm）"
  quote_reply_all_couriers: true
  quote_reply_max_couriers: 10
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
    poll_interval_seconds: 1.0
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
> 也可直接用项目内置插件包：打开 `http://127.0.0.1:8091/cookie`，点击“下载内置插件包”，加载 `Get-cookies.txt-LOCALLY/src` 后导出并一键导入。

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
│       └── quote/               # 自动报价引擎与 provider 适配层
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

> **总览**：项目已进入 **v6.0 企业级稳定期**，当前重点为「零代码部署体验」与「全链路自动化闭环」

---

### 📊 整体进度

```
核心功能 ████████████████████░░░░░ 78%
稳定性   ████████████████████████░░ 92%
易用性   ████████████████░░░░░░░░░░ 65%
扩展性   ████████████████░░░░░░░░░░ 60%
```

---

### 🎯 Phase 1：基础能力建设（已完成 ✅）

> 时间线：2025-Q4 ~ 2026-02

| 功能模块 | 状态 | 负责能力 | 完成度 |
|---------|------|---------|-------|
| 商品发布 | ✅ | 智能标题生成、SEO 优化、图片处理 | 100% |
| 一键擦亮 | ✅ | 批量操作、随机间隔模拟人工 | 100% |
| 价格管理 | ✅ | 单品/批量调价、策略引擎 | 100% |
| 消息自动回复 | ✅ | 意图识别、模板回复、缺参追问 | 100% |
| 多账号管理 | ✅ | Cookie 加密存储、健康检查 | 100% |
| 数据分析 | ✅ | 日报、趋势图、CSV 导出 | 100% |
| Docker 一键部署 | ✅ | docker-compose 全栈部署 | 100% |

**里程碑**：v1.0 ~ v3.0 基础功能全链路打通

---

### 🚀 Phase 2：智能化升级（已完成 ✅）

> 时间线：2026-02

| 功能模块 | 状态 | 负责能力 | 完成度 |
|---------|------|---------|-------|
| 自动报价引擎 | ✅ | 多源容灾、熔断恢复、报价快照 | 100% |
| 合规策略中心 | ✅ | 账号级/会话级分级规则、审计回放 | 100% |
| Workflow Worker | ✅ | 7x24 轮询、幂等去重、崩溃恢复 | 100% |
| SLA 监控 | ✅ | 首响 P95、报价成功率、阈值告警 | 100% |
| 飞书告警 | ✅ | 启动/心跳/SLA 告警推送 | 100% |
| AI 降本治理 | ✅ | 调用策略、预算控制、缓存优化 | 100% |
| 增长实验 | ✅ | A/B 分流、漏斗统计、显著性检验 | 100% |

**里程碑**：v4.0 ~ v4.9 智能化闭环

---

### 🔧 Phase 3：企业级稳定性（已完成 ✅）

> 时间线：2026-02 ~ 2026-03-01

| 功能模块 | 状态 | 负责能力 | 完成度 |
|---------|------|---------|-------|
| Cookie 健康监控 | ✅ | 定时探测、飞书告警、恢复通知 | 100% |
| macOS 开机自启 | ✅ | launchd 守护进程、崩溃自动恢复 | 100% |
| SQLite WAL 模式 | ✅ | 并发写入稳定性提升 | 100% |
| 数据自动备份 | ✅ | 7 天轮转、定时备份脚本 | 100% |
| 两阶段报价 | ✅ | 快速确认 + 异步精确报价 | 100% |
| 合规跟进引擎 | ✅ | 已读未回自动跟进、DND 退订 | 100% |
| Lite 直连模式 | ✅ | 无需 Gateway，本地浏览器直连 | 100% |
| 模块化启动 | ✅ | 售前/运营/售后独立运行 | 100% |
| 国产模型接入 | ✅ | DeepSeek/阿里百炼/火山/MiniMax/智谱 | 100% |

**里程碑**：v5.0 ~ v5.3 生产就绪

---

### 🏁 Phase 4：零代码体验收口（进行中 🟡）

> 时间线：2026-03-02 ~ 2026-03-15（预计）

| 功能模块 | 状态 | 负责能力 | 预计完成 |
|---------|------|---------|---------|
| 自动改价执行 | 🟡 进行中 | 闲管家 API 优先、DOM 自动回退 | 2026-03-05 |
| 订单履约（虚拟商品） | 🟡 进行中 | 回调幂等、补偿机制封板 | 2026-03-08 |
| 售后自动化 | 🟡 进行中 | 工单路由、规则引擎上线 | 2026-03-10 |
| 新手引导 UI | 🟡 进行中 | 首次安装引导、任务式教程 | 2026-03-12 |
| 一键部署（Mac/Win） | ✅ 已完成 | Windows EXE 图形化向导 + 双端打包 | 2026-03-03 |

**里程碑**：v6.0 小白用户零门槛部署

**硬约束**：
1. 全本地运行（不依赖云端业务服务）
2. 零代码部署（不懂代码用户可独立完成首启）
3. 新手引导完整（首次安装、任务式引导、诊断闭环）
4. 超边界转人工（电话沟通、转账退款、纠纷仲裁）

---

### 🌟 Phase 5：高级自动化（计划中 📋）

> 时间线：2026-03-16 ~ 2026-Q2

| 功能模块 | 状态 | 负责能力 | 优先级 |
|---------|------|---------|-------|
| 定时自动擦亮 | 📋 计划中 | cron 调度、智能时段选择 | P0 |
| 智能定价建议 | 📋 计划中 | 基于数据分析的动态定价 | P0 |
| 竞品监控 | 📋 计划中 | 价格追踪、关键词监控 | P1 |
| Telegram 通知 | 📋 计划中 | 消息推送、远程控制 | P1 |
| 微信通知 | 📋 计划中 | 企业微信/公众号推送 | P2 |
| 多语言支持 | 📋 计划中 | 英文/日文界面 | P2 |
| 库存同步 | 📋 计划中 | 多平台库存联动 | P1 |
| 批量导入 | 📋 计划中 | Excel/CSV 商品批量上架 | P1 |

**里程碑**：v7.0 全自动化运营

---

### 🚀 Phase 6：生态扩展（远期规划 🔮）

> 时间线：2026-Q3+

| 功能模块 | 状态 | 负责能力 | 优先级 |
|---------|------|---------|-------|
| Web 管理后台 | 🔮 远期 | 可视化配置、数据看板 | P1 |
| REST API | 🔮 远期 | 开放 API 供第三方集成 | P1 |
| 插件市场 | 🔮 远期 | 社区贡献技能、模板共享 | P2 |
| 移动端适配 | 🔮 远期 | 响应式 Web、小程序 | P2 |
| 多平台支持 | 🔮 远期 | 转转、拼多多二手等 | P3 |
| AI 客服增强 | 🔮 远期 | 多轮对话、情感分析 | P2 |

**里程碑**：v8.0+ 平台化生态

---

### 📈 能力分配矩阵

| 能力域 | 核心模块 | 当前状态 | 下一步 |
|--------|---------|---------|-------|
| **商品运营** | 发布/擦亮/调价 | ✅ 成熟 | 智能定价 |
| **客服自动化** | 回复/报价/跟进 | ✅ 成熟 | 多轮对话 |
| **订单履约** | 状态映射/交付 | 🟡 收口中 | 全流程闭环 |
| **数据分析** | 日报/趋势/漏斗 | ✅ 成熟 | BI 可视化 |
| **安全合规** | 禁词/限流/审计 | ✅ 成熟 | 风控增强 |
| **部署运维** | Docker/脚本 | 🟡 收口中 | 一键安装包 |
| **通知推送** | 飞书告警 | ✅ 可用 | 多渠道扩展 |

---

### 🎖️ 贡献指南

| 难度 | 适合人群 | 推荐任务 |
|------|---------|---------|
| 🟢 入门 | 新手 | 文档完善、测试用例、UI 优化 |
| 🟡 中级 | 有经验 | 新功能开发、性能优化、API 封装 |
| 🔴 高级 | 专家 | 架构重构、核心算法、安全加固 |

欢迎参与贡献！详见 [CONTRIBUTING.md](CONTRIBUTING.md)

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

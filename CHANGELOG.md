# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `src/modules/quote/route.py`：地理路由标准化组件，支持省/市/自治区别名与后缀容错。
- `quote` 配置新增熔断参数：`circuit_fail_threshold`、`circuit_open_seconds`。
- 自动报价新增测试：路由标准化缓存命中、远程 provider 熔断打开后自动降级。

### Changed
- `QuoteRequest.cache_key()` 升级为分层缓存 key：`origin + destination + courier + weight_bucket + service_level`。
- `AutoQuoteEngine` 增强：
  - 请求前路由标准化（统一 cache key 与 provider 入参）
  - 远程 provider 失败计数与熔断窗口
  - fallback 失败分类（`timeout/transient/unavailable/provider_error`）
  - 回退结果追加标准化路由可观测字段

## [4.4.0] - 2026-02-27

### Added
- `src/modules/messages/workflow.py`：
  - `WorkflowState` + `SessionStateMachine` 状态迁移规则
  - `WorkflowStore`（SQLite 持久化）：会话任务、迁移日志、幂等作业队列、SLA 事件、告警事件
  - `WorkflowWorker`：常驻轮询、幂等去重、失败指数退避、过期租约恢复
- `MessagesService.process_session(...)`，统一单会话处理路径，供批处理和 worker 复用。
- CLI 新增 `messages` 动作：
  - `auto-workflow`（单次或 daemon）
  - `workflow-stats`（工作流与 SLA 汇总）
- 新增测试 `tests/test_workflow.py`，覆盖状态迁移防护、作业去重与重试、worker 流程与人工接管跳过。

### Changed
- `src/modules/messages/service.py`：`auto_reply_unread` 改为复用 `process_session`，减少重复逻辑并对齐 worker 行为。
- `config/config.example.yaml`、`src/core/config_models.py`、`src/core/config.py`：新增 `messages.workflow` 配置段与默认值支持。
- `README.md` 更新为 4.4.0，补充 workflow worker、SLA 指标与新 CLI 用法。

## [4.3.0] - 2026-02-27

### Added
- `src/modules/quote/` 自动报价模块：
  - `models.py`：`QuoteRequest` / `QuoteResult`
  - `providers.py`：`IQuoteProvider`、`RuleTableQuoteProvider`、`RemoteQuoteProvider(mock)`
  - `cache.py`：`TTL + stale-while-revalidate` 缓存
  - `engine.py`：`AutoQuoteEngine`（provider 重试、失败回退、缓存刷新、审计日志）
- 消息自动回复新增询价分流：
  - 识别询价意图后自动解析寄件地/收件地/重量/时效
  - 缺参时生成补充提问模板
  - 字段完整时返回结构化报价文案（含费用拆分和有效期）
- 消息链路新增快速回复指标：
  - `target_reply_seconds`
  - `within_target_count` / `within_target_rate`
  - `quote_latency_ms` / `quote_success_rate` / `quote_fallback_rate`
- 新增测试 `tests/test_quote_engine.py`，覆盖规则报价、远程失败回退、缓存命中。

### Changed
- `src/modules/messages/service.py`：
  - 支持复用消息页（降低批量回复页面开关开销）
  - 新增 `reply_to_session(..., page_id=...)` 复用调用路径
  - `auto_reply_unread` 接入自动报价、缺参补问、合规降级回复
  - `dry-run` 模式跳过随机等待，提升测试与验收效率
- 配置模型与样例新增 `quote` 配置段与 `messages.fast_reply_*` 参数。
- `README.md` 更新为 4.3.0，补充自动报价与快速回复配置示例。
- `src/__init__.py` 版本号更新为 `4.3.0`。

## [4.2.1] - 2026-02-27

### Added
- `src/modules/messages/reply_engine.py` — 通用自动回复策略引擎，支持意图规则（关键词/正则/优先级）与虚拟商品场景兜底回复
- `messages` 配置新增 `virtual_default_reply`、`virtual_product_keywords`、`intent_rules`
- 新增测试覆盖：虚拟商品卡密咨询、代下单咨询的自动回复命中逻辑

### Changed
- `src/modules/messages/service.py` 自动回复逻辑由单一关键词匹配升级为策略引擎驱动，保留原 `keyword_replies` 兼容路径
- `config/config.example.yaml` 增加虚拟商品/卡密/代下单策略配置示例，便于按品类快速扩展
- `README.md` 更新消息自动回复策略说明，新增可直接复用的规则化配置模板

## [4.2.0] - 2026-02-27

### Added
- `src/setup_wizard.py` — 交互式一键部署向导，支持逐步输入 API Key、Cookie、认证信息并生成 `.env`
- `scripts/one_click_deploy.sh` — 一键部署脚本封装，优先使用 `.venv/bin/python`
- `src/dashboard_server.py` — 轻量运营后台可视化服务（HTTP + Chart.js），提供实时指标与图表
- `src/modules/messages/service.py` — 闲鱼消息自动回复服务，支持关键词模板与批量未读处理
- CLI 新命令 `messages`（`list-unread` / `reply` / `auto-reply`）
- 新增测试：`tests/test_setup_wizard.py`、`tests/test_dashboard_server.py`、消息模块相关单测

### Changed
- `README.md` / `USER_GUIDE.md` 增加一键部署与后台可视化使用说明
- `config/config.example.yaml` / `src/core/config*.py` 新增 `messages` 配置模型与默认项
- `src/main.py` / `src/modules/__init__.py` 接入消息模块加载与导出

## [4.1.0] - 2026-02-27

### Added
- `src/core/compliance.py` — 合规规则引擎，支持内容审查、频率限制与规则热重载
- `config/rules.yaml` — 合规规则配置（`warn/block` 模式、发布间隔、批量冷却、禁词词表）
- `tests/test_compliance.py`、`tests/test_service_container.py` — 合规与容器核心行为单测

### Changed
- **Compliance**: 发布/运营/内容链路接入增强合规决策，新增 `COMPLIANCE_BLOCK` / `COMPLIANCE_WARN` 审计事件
- **Scheduler**: 擦亮/发布任务显式创建并注入 `BrowserClient`，连接失败返回结构化错误码
- **Monitor**: 健康检查告警调用改为 `await`，并修复回调字段引用错误
- **Analytics**: 周报统计不再依赖缺失表；`new_listings` 统计口径从分组数修正为总数
- **Accounts**: 账号 Cookie 字段统一为 `cookie_encrypted`，读写与脱敏逻辑统一
- **Skills/Test alignment**: 废弃 legacy `skills/xianyu_*` Python 包运行路径，测试改为校验 `SKILL.md + CLI` 契约
- **Quality gates**: 修复并启用全量 `pytest.ini` 配置，测试与 lint 门槛可真实执行

### Fixed
- `ServiceContainer` 单例集合类型错误（`_singletons`）与 `clear()` 清理不完整问题
- 发布流程中“分类/成色选择”空操作问题
- 批量擦亮结果中随机伪商品 ID 与失败统计失真问题
- 媒体格式映射大小写问题（`png/webp`）
- 监控与错误处理中的 Python 3.14 兼容性警告（协程判断方式）

## [4.0.0] - 2026-02-23

### Added
- `BrowserClient` — OpenClaw Gateway browser HTTP client replacing direct Playwright calls
- `src/cli.py` — CLI entry point with 7 subcommands for agent invocation
- 5 OpenClaw Skills in standard `SKILL.md` format (publish, manage, content, metrics, accounts)
- `scripts/init.sh` — Docker container Python environment bootstrap
- `config/openclaw.example.json` — OpenClaw Gateway configuration template
- `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`
- GitHub Actions CI workflow
- Issue and PR templates

### Changed
- **Architecture**: migrated from Playwright + Streamlit to OpenClaw-native Skill ecosystem
- **Deployment**: single `docker compose up -d` using `coollabsio/openclaw` image
- **UI**: replaced Streamlit/FastAPI web interface with OpenClaw AI chat UI
- **Dependencies**: removed playwright, streamlit, fastapi, uvicorn; kept httpx, aiosqlite, cryptography

### Removed
- `web/` directory (Streamlit + FastAPI + React frontend)
- `Dockerfile` (using OpenClaw official image)
- `install.sh`, `install.bat`, `start.sh`, `start.bat`
- `openclaw_controller.py` (replaced by `browser_client.py`)
- Skills Python code (`skill.py`, `registry.py`, `openclaw_integration.py`)

## [3.0.0] - 2026-02-23

### Added
- Playwright-based browser automation (replacing non-functional HTTP API stubs)
- AES cookie encryption (`src/core/crypto.py`)
- Rate limiting middleware
- Docker containerization (`Dockerfile` + `docker-compose.yml`)
- Startup health checks (`src/core/startup_checks.py`)

### Fixed
- SQL injection vulnerability in analytics service
- CORS configuration (was `allow_origins=["*"]`)
- Silent mock data returns when controller unavailable (now raises `BrowserError`)

### Changed
- CSS selectors updated for Xianyu SPA (text-based, placeholder, role matching)

## [2.1.0] - 2026-02-22

### Added
- Task management API
- Release checklist documentation

## [2.0.0] - 2026-02-22

### Added
- Streamlit web interface
- React frontend with Ant Design
- FastAPI backend with REST endpoints
- One-click install scripts (Windows + macOS/Linux)

## [1.0.0] - 2026-02-21

### Added
- Initial project structure
- Core modules: config, logger, error handler
- Business modules: listing, operations, analytics, accounts, content, media
- OpenClaw skill stubs
- Multi-account support
- AI content generation (DeepSeek/OpenAI)

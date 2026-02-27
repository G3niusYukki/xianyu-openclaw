# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

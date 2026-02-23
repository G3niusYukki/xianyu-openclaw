# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

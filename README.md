<p align="center">
  <img src="https://img.shields.io/badge/🐟-Xianyu_OpenClaw-FF6A00?style=for-the-badge&labelColor=1a1a2e" alt="Xianyu OpenClaw" />
</p>

<h1 align="center">xianyu-openclaw</h1>

<p align="center">
  <strong>AI-powered Xianyu (闲鱼) automation — talk to your store, not click through it.</strong>
</p>

<p align="center">
  <a href="https://github.com/G3niusYukki/xianyu-openclaw/releases/latest"><img src="https://img.shields.io/github/v/release/G3niusYukki/xianyu-openclaw?style=flat-square&color=FF6A00" alt="Release" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/G3niusYukki/xianyu-openclaw?style=flat-square" alt="License" /></a>
  <a href="https://github.com/G3niusYukki/xianyu-openclaw/actions"><img src="https://img.shields.io/github/actions/workflow/status/G3niusYukki/xianyu-openclaw/ci.yml?style=flat-square&label=CI" alt="CI" /></a>
  <a href="https://github.com/G3niusYukki/xianyu-openclaw/stargazers"><img src="https://img.shields.io/github/stars/G3niusYukki/xianyu-openclaw?style=flat-square" alt="Stars" /></a>
  <a href="https://github.com/G3niusYukki/xianyu-openclaw/issues"><img src="https://img.shields.io/github/issues/G3niusYukki/xianyu-openclaw?style=flat-square" alt="Issues" /></a>
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> •
  <a href="#features">Features</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#skills">Skills</a> •
  <a href="USER_GUIDE.md">中文使用指南</a> •
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

---

## Why?

Running a Xianyu (闲鱼, aka Goofish) store means repeating the same tedious tasks every day: publish listings, write SEO titles, polish (refresh) items, adjust prices, check analytics. That's hours of clicking.

**xianyu-openclaw** turns all of that into a conversation:

```
You: 帮我发布一个 iPhone 15 Pro，价格 5999，95新
 AI: ✅ 已发布！标题：【自用出】iPhone 15 Pro 256G 原色钛金属 95新
     链接：https://www.goofish.com/item/xxx

You: 擦亮所有商品
 AI: ✅ 已擦亮 23 件商品

You: 今天运营数据怎么样？
 AI: 📊 今日浏览 1,247 | 想要 89 | 成交 12 | 营收 ¥38,700
```

Built on [OpenClaw](https://github.com/openclaw/openclaw) — an open-source AI agent framework with native browser control. When OpenClaw upgrades, your Xianyu toolkit upgrades with it.

---

## Features

| | Feature | Description |
|---|---------|-------------|
| 🤖 | **Natural language control** | Talk to your store in Chinese. No menus, no clicking. |
| 📦 | **Smart publishing** | AI-generated titles, descriptions & tags optimized for Xianyu SEO |
| ✨ | **Batch polish** | One command to refresh all listings, with human-like random delays |
| 💰 | **Price management** | Adjust prices, bulk repricing strategies |
| 📊 | **Analytics dashboard** | Daily reports, trend analysis, data export (CSV) |
| 👥 | **Multi-account** | Manage multiple Xianyu accounts with encrypted cookie storage |
| 🔒 | **Security first** | AES-encrypted cookies, parameterized SQL, rate limiting |
| 🐳 | **One-command deploy** | `docker compose up -d` — that's it |
| 🔌 | **Plugin architecture** | 5 modular OpenClaw Skills, easy to extend |

---

<h2 id="quickstart">Quickstart</h2>

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (20.10+)
- An AI API key — [Anthropic](https://console.anthropic.com/) (recommended), [OpenAI](https://platform.openai.com/), or [DeepSeek](https://platform.deepseek.com/) (cheapest)
- A Xianyu (Goofish) account cookie ([how to get it](#get-cookie))

### 3 steps to launch

```bash
# 1. Clone
git clone https://github.com/G3niusYukki/xianyu-openclaw.git
cd xianyu-openclaw

# 2. Configure
cp .env.example .env
# Edit .env — fill in your API key, cookie, and passwords

# 3. Launch
docker compose up -d
```

Open **http://localhost:8080** and start talking to your Xianyu AI assistant.

---

<h2 id="architecture">Architecture</h2>

```
┌─────────────────────────────────────────────────┐
│                   User (Chat UI)                │
│            http://localhost:8080                 │
└──────────────────────┬──────────────────────────┘
                       │ natural language
                       ▼
┌──────────────────────────────────────────────────┐
│              OpenClaw Gateway                     │
│    AI Agent  ·  Skill Router  ·  Web UI           │
│                  :18789                           │
└──────┬──────────────┬──────────────┬─────────────┘
       │              │              │
       ▼              ▼              ▼
  ┌─────────┐  ┌───────────┐  ┌───────────┐
  │ xianyu- │  │  xianyu-  │  │  xianyu-  │  ... 5 Skills
  │ publish │  │  manage   │  │  metrics  │
  └────┬────┘  └─────┬─────┘  └─────┬─────┘
       │             │              │
       ▼             ▼              ▼
  ┌──────────────────────────────────────────┐
  │          Python CLI  (src/cli.py)        │
  │   ListingService · OperationsService     │
  │   AnalyticsService · AccountsService     │
  └──────────────────┬───────────────────────┘
                     │ HTTP
                     ▼
  ┌──────────────────────────────────────────┐
  │     OpenClaw Managed Browser (CDP)       │
  │          headless Chromium :18791        │
  └──────────────────┬───────────────────────┘
                     │
                     ▼
              goofish.com 🐟
```

**Before v4**: User → Streamlit → FastAPI → Playwright → Chromium
**After v4**: User → OpenClaw Chat → Skill → CLI → Gateway Browser API → Managed Chromium

---

<h2 id="skills">Skills</h2>

Each skill is a self-contained [OpenClaw Skill](https://docs.openclaw.ai/skills/) with a `SKILL.md` descriptor:

| Skill | What it does | Example prompt |
|-------|-------------|----------------|
| `xianyu-publish` | Publish new listings with AI-generated copy | "发布一个 AirPods Pro，800 元" |
| `xianyu-manage` | Polish / reprice / delist / relist | "擦亮所有商品" |
| `xianyu-content` | Generate SEO-optimized titles & descriptions | "帮我写个 MacBook 的标题" |
| `xianyu-metrics` | Dashboard, daily reports, trend charts | "这周浏览量趋势" |
| `xianyu-accounts` | Health checks, cookie validation & refresh | "Cookie 还有效吗" |

### CLI interface

Skills call the Python backend via a structured CLI:

```bash
python -m src.cli publish  --title "..." --price 5999 --tags 95新 国行
python -m src.cli polish   --all --max 50
python -m src.cli price    --id item_123 --price 4999
python -m src.cli delist   --id item_123
python -m src.cli relist   --id item_123
python -m src.cli analytics --action dashboard
python -m src.cli accounts  --action list
```

All commands output structured JSON for agent parsing.

---

<h2 id="get-cookie">Getting Your Xianyu Cookie</h2>

<details>
<summary><strong>Click to expand step-by-step guide</strong></summary>

1. Open **https://www.goofish.com** in Chrome and log in
2. Press **F12** to open DevTools
3. Go to the **Network** tab
4. Refresh the page (**F5**)
5. Click any request in the list
6. Find `Cookie:` in **Request Headers**
7. Copy the entire value
8. Paste into `.env` as `XIANYU_COOKIE_1=...`

> Cookies expire every 7–30 days. The tool will warn you when they're about to expire.

</details>

---

## Configuration

<details>
<summary><strong><code>.env</code> variables</strong></summary>

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | One AI key required | Anthropic API key |
| `OPENAI_API_KEY` | | OpenAI API key |
| `DEEPSEEK_API_KEY` | | DeepSeek API key (cheapest) |
| `OPENCLAW_GATEWAY_TOKEN` | Yes | Gateway auth token (set anything) |
| `AUTH_PASSWORD` | Yes | Web UI login password |
| `XIANYU_COOKIE_1` | Yes | Xianyu session cookie |
| `XIANYU_COOKIE_2` | | Second account cookie |
| `ENCRYPTION_KEY` | | Cookie encryption passphrase (auto-generated if empty) |

</details>

<details>
<summary><strong>OpenClaw config (<code>config/openclaw.example.json</code>)</strong></summary>

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

## Project Structure

```
xianyu-openclaw/
├── skills/                      # 5 OpenClaw Skills (SKILL.md format)
│   ├── xianyu-publish/
│   ├── xianyu-manage/
│   ├── xianyu-content/
│   ├── xianyu-metrics/
│   └── xianyu-accounts/
├── src/
│   ├── cli.py                   # CLI entry point (agent ↔ services)
│   ├── core/
│   │   ├── browser_client.py    # OpenClaw Gateway browser HTTP client
│   │   ├── config.py            # YAML config loader
│   │   ├── crypto.py            # AES cookie encryption
│   │   ├── error_handler.py     # Centralized error handling
│   │   ├── logger.py            # Structured logging (loguru)
│   │   └── startup_checks.py    # Boot-time health checks
│   └── modules/
│       ├── listing/             # Publish & manage listings
│       ├── operations/          # Polish, reprice, delist
│       ├── analytics/           # SQLite-backed analytics
│       ├── accounts/            # Multi-account & cookie mgmt
│       ├── content/             # AI content generation
│       └── media/               # Image processing (Pillow)
├── config/                      # Config templates
├── scripts/init.sh              # Docker Python env bootstrap
├── docker-compose.yml           # One-command deployment
├── requirements.txt             # Minimal Python deps
└── .env.example                 # Environment template
```

---

## Development

```bash
# Clone and install deps locally (for development without Docker)
git clone https://github.com/G3niusYukki/xianyu-openclaw.git
cd xianyu-openclaw
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run CLI directly
python -m src.cli --help

# Run tests
pytest tests/

# Lint
ruff check src/
```

---

## Relationship with OpenClaw

This project is a set of **Skills** (plugins) for the [OpenClaw](https://github.com/openclaw/openclaw) AI agent framework:

| Layer | Provided by |
|-------|------------|
| AI Agent & Chat UI | OpenClaw |
| Browser automation (CDP) | OpenClaw |
| Gateway API | OpenClaw |
| **Xianyu business logic** | **This project** |
| **Analytics & reporting** | **This project** |
| **Multi-account management** | **This project** |

When OpenClaw releases updates (new AI models, browser engine upgrades, new tools), just run:

```bash
docker compose pull && docker compose up -d
```

Your Xianyu business logic stays untouched.

---

## Roadmap

- [ ] Scheduled auto-polish (cron-based)
- [ ] Price optimization suggestions based on analytics
- [ ] Competitor monitoring
- [ ] Telegram / WeChat notification bot
- [ ] Xianyu message auto-reply
- [ ] Multi-language support

---

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Security

Found a vulnerability? Please report it privately — see [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) — use it, fork it, sell fish with it. 🐟

---

<p align="center">
  <sub>Built with 🐟 and ☕ by <a href="https://github.com/G3niusYukki">@G3niusYukki</a></sub>
</p>

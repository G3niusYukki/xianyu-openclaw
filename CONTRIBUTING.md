# Contributing to xianyu-openclaw

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/G3niusYukki/xianyu-openclaw.git
cd xianyu-openclaw
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Project Layout

```
src/
├── cli.py              # CLI entry point — all agent commands
├── core/               # Framework: config, logging, browser client, crypto
└── modules/            # Business logic: listing, operations, analytics, accounts
skills/                 # OpenClaw SKILL.md files (one per directory)
```

Note:
- `skills/xianyu_*` Python packages are deprecated compatibility stubs.
- Use `skills/*/SKILL.md + src/cli.py` as the only supported skill execution path.

## How to Contribute

### Bug Reports

Open an [issue](https://github.com/G3niusYukki/xianyu-openclaw/issues/new?template=bug_report.md) with:
- What you expected
- What actually happened
- Steps to reproduce
- Logs (`docker compose logs`)

### Feature Requests

Open an [issue](https://github.com/G3niusYukki/xianyu-openclaw/issues/new?template=feature_request.md) describing the use case.

### Pull Requests

1. Fork the repo
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Make your changes
4. Run linting: `ruff check src/`
5. If your change affects publishing/operations, also verify `config/rules.yaml` compatibility behavior.
6. Commit with a clear message: `git commit -m "feat: add price optimization"`
7. Push to your fork and open a PR

### Commit Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/):

| Prefix | When to use |
|--------|-------------|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `docs:` | Documentation only |
| `refactor:` | Code restructuring (no behavior change) |
| `test:` | Adding or updating tests |
| `chore:` | Build, CI, dependency updates |

### Adding a New Skill

1. Create `skills/your-skill/SKILL.md` following the [OpenClaw Skill format](https://docs.openclaw.ai/skills/)
2. Add corresponding CLI command in `src/cli.py`
3. Add service logic in `src/modules/`
4. Update the skill table in `README.md`

## Code Style

- Python 3.10+
- Type hints everywhere
- Use `async/await` for I/O operations
- `loguru` for logging (not `print`)
- Structured JSON output from CLI commands

## Need Help?

Open an issue or start a [discussion](https://github.com/G3niusYukki/xianyu-openclaw/discussions).

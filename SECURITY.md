# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 4.x     | ✅ Active |
| < 4.0   | ❌ EOL    |

## Reporting a Vulnerability

**Do NOT open a public issue for security vulnerabilities.**

Please report security issues by emailing the maintainer or using [GitHub's private vulnerability reporting](https://github.com/G3niusYukki/xianyu-openclaw/security/advisories/new).

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will respond within 48 hours and provide a fix timeline.

## Security Measures

This project implements:

- **AES-encrypted cookie storage** (`src/core/crypto.py`) — Xianyu cookies are encrypted at rest using Fernet symmetric encryption
- **Parameterized SQL** — All database queries use parameterized statements to prevent SQL injection
- **Rate limiting** — Configurable delays between operations to avoid platform detection
- **No credential logging** — Cookies and API keys are never written to logs
- **Environment-based secrets** — All sensitive values are loaded from environment variables, not config files

#!/usr/bin/env bash
set -euo pipefail

if [[ -x ".venv/bin/python" ]]; then
  exec .venv/bin/python -m src.setup_wizard
fi

if command -v python3 >/dev/null 2>&1; then
  exec python3 -m src.setup_wizard
fi

exec python -m src.setup_wizard

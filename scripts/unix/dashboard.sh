#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-8091}"
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
PY_BIN="$ROOT_DIR/.venv/bin/python"

if [[ ! -x "$PY_BIN" ]]; then
  echo "[ERROR] Python not found at $PY_BIN"
  echo "Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

cd "$ROOT_DIR"
exec "$PY_BIN" -m src.dashboard_server --port "$PORT"

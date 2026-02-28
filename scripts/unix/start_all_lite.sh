#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
PY_BIN="$ROOT_DIR/.venv/bin/python"

if [[ ! -x "$PY_BIN" ]]; then
  echo "[ERROR] Python not found at $PY_BIN"
  exit 1
fi

cd "$ROOT_DIR"
exec "$PY_BIN" -m src.cli module --action start --target all --mode daemon --background --interval 5 --limit 20 --claim-limit 10 --issue-type delay --init-default-tasks

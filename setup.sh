#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="${XY_VENV_DIR:-.venv312}"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "[ENV_MISMATCH] $PYTHON_BIN not found. Install Python 3.12 first." >&2
    exit 2
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment: $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    echo "Installing dependencies from requirements.txt..."
    "$VENV_DIR/bin/pip" install -r requirements.txt
else
    echo "requirements.txt not found!" >&2
    exit 1
fi

echo "Setup complete: $VENV_DIR"
echo "Run tests via: scripts/qa/lock_test_env.sh -q"

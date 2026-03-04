#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

IMAGE="node:20-alpine"
CONTAINER_WORKDIR="/workspace/server"

if ! command -v docker >/dev/null 2>&1; then
  echo "[gate] docker not found in PATH" >&2
  exit 127
fi

cd "${SERVER_DIR}"

echo "[gate] running webhook signature + idempotency tests in Docker (${IMAGE})"

docker run --rm \
  -v "${SERVER_DIR}:${CONTAINER_WORKDIR}" \
  -w "${CONTAINER_WORKDIR}" \
  -e NODE_ENV=test \
  -e STRIPE_SECRET_KEY=sk_test_dummy \
  -e STRIPE_WEBHOOK_SECRET=whsec_test_dummy \
  "${IMAGE}" \
  sh -lc 'npm ci && npm test -- --runInBand tests/payment.webhook.spec.js'

echo "[gate] PASS: duplicate callback is idempotent and bad signature is rejected"

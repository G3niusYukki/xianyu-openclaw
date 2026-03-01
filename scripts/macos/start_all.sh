#!/bin/bash
# 闲鱼 OpenClaw — macOS 统一启动脚本
# launchd 的 ProgramArguments 指向此脚本
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

# 激活虚拟环境
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# 加载 .env
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

echo "[start_all] $(date '+%Y-%m-%d %H:%M:%S') Starting xianyu-openclaw..."

# 1. 启动 Docker Compose（如果未运行且 docker 可用）
if command -v docker &>/dev/null && [ -f "docker-compose.yml" ]; then
    CONTAINER_NAME="${CONTAINER_NAME:-xianyu-openclaw}"
    if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "[start_all] Starting Docker Compose..."
        docker compose up -d 2>&1 || echo "[start_all] Docker compose start failed, continuing..."

        # 等待 Gateway 就绪
        echo "[start_all] Waiting for Gateway..."
        for i in $(seq 1 30); do
            if curl -sf "http://127.0.0.1:${OPENCLAW_WEB_PORT:-8080}/healthz" &>/dev/null; then
                echo "[start_all] Gateway ready."
                break
            fi
            sleep 2
        done
    else
        echo "[start_all] Docker container already running."
    fi
fi

# 2. 健康检查
echo "[start_all] Running doctor check..."
python -m src.cli doctor --skip-gateway --skip-quote 2>&1 || true

# 3. 启动所有模块守护进程
echo "[start_all] Starting all module daemons..."
python -m src.cli module --action start --target all --mode daemon --background 2>&1 || true

# 4. 启动 Dashboard
echo "[start_all] Starting dashboard..."
python -m src.dashboard_server --port "${DASHBOARD_PORT:-8091}" &
DASHBOARD_PID=$!
echo "[start_all] Dashboard PID: $DASHBOARD_PID"

# 5. 等待子进程
echo "[start_all] All services started. Waiting..."
wait $DASHBOARD_PID 2>/dev/null || true

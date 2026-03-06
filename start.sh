#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
fail()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

echo ""
echo "========================================="
echo "  闲鱼管家 - 一键启动"
echo "========================================="
echo ""

# 1. 检查 Python
if ! command -v python3 &>/dev/null; then
  fail "未找到 python3，请先安装 Python 3.10+"
fi

PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
info "Python 版本: $PY_VER"

# 2. 检查 Node.js
if ! command -v node &>/dev/null; then
  fail "未找到 node，请先安装 Node.js 18+"
fi

NODE_VER=$(node -v)
info "Node.js 版本: $NODE_VER"

# 3. 创建 .env（如不存在）
if [ ! -f ".env" ]; then
  if [ -f ".env.example" ]; then
    cp .env.example .env
    warn ".env 文件不存在，已从 .env.example 创建。请编辑 .env 填入实际配置。"
  else
    fail "未找到 .env 和 .env.example"
  fi
else
  info ".env 已存在"
fi

# 4. 创建 Python 虚拟环境并安装依赖
if [ ! -d ".venv" ]; then
  info "创建 Python 虚拟环境..."
  python3 -m venv .venv
fi

source .venv/bin/activate
info "Python 虚拟环境已激活"

if [ ! -f ".venv/.deps_installed" ] || [ requirements.txt -nt ".venv/.deps_installed" ]; then
  info "安装 Python 依赖..."
  pip install -q -r requirements.txt
  touch .venv/.deps_installed
  info "Python 依赖安装完成"
else
  info "Python 依赖已是最新"
fi

# 5. 安装 Node.js 依赖
if [ ! -d "server/node_modules" ]; then
  info "安装 Node.js 后端依赖..."
  (cd server && npm install --silent)
fi

if [ ! -d "client/node_modules" ]; then
  info "安装 React 前端依赖..."
  (cd client && npm install --silent)
fi

info "所有依赖就绪"

# 6. 启动服务
echo ""
echo "========================================="
echo "  启动所有服务"
echo "========================================="
echo ""

cleanup() {
  echo ""
  warn "正在停止所有服务..."
  kill $PY_PID 2>/dev/null || true
  kill $NODE_PID 2>/dev/null || true
  kill $CLIENT_PID 2>/dev/null || true
  wait 2>/dev/null || true
  info "所有服务已停止"
}
trap cleanup EXIT INT TERM

# Python 后端
info "启动 Python 后端 (端口 8091)..."
python3 -m src.dashboard_server --port 8091 &
PY_PID=$!

# Node.js 后端
info "启动 Node.js 后端 (端口 3001)..."
(cd server && node src/app.js) &
NODE_PID=$!

# React 前端
info "启动 React 前端 (端口 5173)..."
(cd client && npx vite --host) &
CLIENT_PID=$!

sleep 2
echo ""
echo "========================================="
echo "  所有服务已启动"
echo "========================================="
echo ""
info "管理面板:    http://localhost:5173"
info "Node 后端:   http://localhost:3001"
info "Python 后端: http://localhost:8091"
echo ""
info "按 Ctrl+C 停止所有服务"
echo ""

wait

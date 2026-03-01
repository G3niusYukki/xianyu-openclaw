#!/bin/bash
# 闲鱼 OpenClaw — macOS launchd 服务管理
# 用法: ./install_service.sh [install|uninstall|status]
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PLIST_NAME="com.xianyu-openclaw"
PLIST_SOURCE="$SCRIPT_DIR/${PLIST_NAME}.plist"
PLIST_TARGET="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

usage() {
    echo "Usage: $0 [install|uninstall|status]"
    echo ""
    echo "  install    Install and start the launchd service"
    echo "  uninstall  Stop and remove the launchd service"
    echo "  status     Check service status"
    exit 1
}

install_service() {
    echo "Installing xianyu-openclaw service..."

    # 生成 plist 文件（替换项目路径占位符）
    sed "s|__PROJECT_ROOT__|${PROJECT_ROOT}|g" "$PLIST_SOURCE" > "$PLIST_TARGET"
    echo "  Created: $PLIST_TARGET"

    # 加载服务
    launchctl load "$PLIST_TARGET" 2>/dev/null || true
    echo "  Service loaded."

    # 启动服务
    launchctl start "$PLIST_NAME" 2>/dev/null || true
    echo "  Service started."
    echo ""
    echo "✅ xianyu-openclaw service installed and started."
    echo "   Logs: $PROJECT_ROOT/logs/launchd_stdout.log"
    echo "   Errors: $PROJECT_ROOT/logs/launchd_stderr.log"
}

uninstall_service() {
    echo "Uninstalling xianyu-openclaw service..."

    launchctl stop "$PLIST_NAME" 2>/dev/null || true
    launchctl unload "$PLIST_TARGET" 2>/dev/null || true

    if [ -f "$PLIST_TARGET" ]; then
        rm "$PLIST_TARGET"
        echo "  Removed: $PLIST_TARGET"
    fi

    echo "✅ xianyu-openclaw service uninstalled."
}

check_status() {
    echo "Checking xianyu-openclaw service status..."
    echo ""

    if [ ! -f "$PLIST_TARGET" ]; then
        echo "  ❌ Service not installed."
        return
    fi

    if launchctl list | grep -q "$PLIST_NAME"; then
        echo "  ✅ Service is loaded."
        launchctl list "$PLIST_NAME" 2>/dev/null || true
    else
        echo "  ⚠️ Service plist exists but not loaded."
    fi

    echo ""
    echo "Recent logs:"
    tail -5 "$PROJECT_ROOT/logs/launchd_stdout.log" 2>/dev/null || echo "  (no logs yet)"
}

case "${1:-}" in
    install)   install_service ;;
    uninstall) uninstall_service ;;
    status)    check_status ;;
    *)         usage ;;
esac

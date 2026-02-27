#!/bin/bash
# OpenClaw 自定义初始化脚本
# 在 Gateway 启动前运行，安装 Python 环境和项目依赖

set -e

# OpenClaw 新镜像默认使用 /data/workspace；旧布局仍可能是 /home/node/.openclaw/workspace
WORKSPACE="/data/workspace"
if [ ! -d "$WORKSPACE" ]; then
    WORKSPACE="/home/node/.openclaw/workspace"
fi

echo "[init] Installing Python environment for xianyu-openclaw..."

# 安装 Python 3 和 pip（如果不存在）
if ! command -v python3 &>/dev/null; then
    echo "[init] Installing Python 3..."
    apt-get update -qq && apt-get install -y -qq python3 python3-pip python3-venv >/dev/null 2>&1
fi

# 创建虚拟环境（如果不存在）
VENV_PATH="$WORKSPACE/.venv"
if [ ! -d "$VENV_PATH" ]; then
    echo "[init] Creating Python virtual environment..."
    python3 -m venv "$VENV_PATH"
fi

# 安装依赖
if [ -f "$WORKSPACE/requirements.txt" ]; then
    echo "[init] Installing Python dependencies..."
    "$VENV_PATH/bin/pip" install -q -r "$WORKSPACE/requirements.txt"
fi

# 确保 python -m src.cli 可以使用 venv 中的 python
# 在 PATH 中添加 venv/bin
export PATH="$VENV_PATH/bin:$PATH"

# 创建数据目录
mkdir -p "$WORKSPACE/data" "$WORKSPACE/data/processed_images" "$WORKSPACE/logs"

# 不在此处创建 openclaw.json，避免与镜像入口脚本的状态目录(/data/.openclaw)冲突

# 创建一个 wrapper 脚本使 skills 中的 python 命令使用 venv
WRAPPER="$WORKSPACE/.venv/bin/python-wrapper"
cat > "$WRAPPER" << EOWRAP
#!/bin/bash
export PATH="$VENV_PATH/bin:\$PATH"
cd "$WORKSPACE"
exec "$VENV_PATH/bin/python" "\$@"
EOWRAP
chmod +x "$WRAPPER"

# 创建符号链接使 skills 中的 "python" 指向 venv
ln -sf "$VENV_PATH/bin/python" /usr/local/bin/python 2>/dev/null || true

echo "[init] Python environment ready."
echo "[init] Python: $(python3 --version)"
echo "[init] Workspace: $WORKSPACE"

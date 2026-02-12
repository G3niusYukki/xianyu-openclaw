#!/bin/bash

# 闲鱼自动化工具 - macOS一键安装脚本

set -e

echo "=========================================="
echo "🦞 闲鱼自动化工具 - 安装向导"
echo "=========================================="
echo ""

# 检查Python版本
echo "📋 检查Python版本..."
if ! command -v python3 &> /dev/null; then
    echo "❌ 未检测到Python3，请先安装Python 3.10或更高版本"
    echo "   下载地址: https://www.python.org/downloads/"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo "✅ 检测到Python版本: $PYTHON_VERSION"

# 检查Node.js版本
echo ""
echo "📋 检查Node.js版本..."
if ! command -v node &> /dev/null; then
    echo "❌ 未检测到Node.js，请先安装Node.js 18或更高版本"
    echo "   下载地址: https://nodejs.org/"
    exit 1
fi

NODE_VERSION=$(node --version)
echo "✅ 检测到Node.js版本: $NODE_VERSION"

# 创建虚拟环境
echo ""
echo "🔧 创建Python虚拟环境..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ 虚拟环境创建成功"
else
    echo "⚠️  虚拟环境已存在"
fi

# 激活虚拟环境
source venv/bin/activate

# 升级pip
echo ""
echo "🔧 升级pip..."
pip install --upgrade pip -q

# 安装Python依赖
echo ""
echo "📦 安装Python依赖..."
pip install -r requirements.txt -q
echo "✅ Python依赖安装完成"

# 复制配置文件
echo ""
echo "📋 初始化配置文件..."
if [ ! -f "config/config.yaml" ]; then
    cp config/config.example.yaml config/config.yaml
    echo "✅ 配置文件已创建: config/config.yaml"
else
    echo "⚠️  配置文件已存在"
fi

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "✅ 环境变量文件已创建: .env"
else
    echo "⚠️  环境变量文件已存在"
fi

# 安装前端依赖
echo ""
echo "📦 安装前端依赖..."
cd web/frontend
if [ ! -d "node_modules" ]; then
    npm install -q
    echo "✅ 前端依赖安装完成"
else
    echo "⚠️  前端依赖已存在"
fi
cd ../..

# 创建数据目录
echo ""
echo "📁 创建数据目录..."
mkdir -p data/processed_images
mkdir -p logs
echo "✅ 数据目录创建完成"

# 构建前端
echo ""
echo "🔨 构建前端..."
cd web/frontend
npm run build
cd ../..
echo "✅ 前端构建完成"

echo ""
echo "=========================================="
echo "✅ 安装完成！"
echo "=========================================="
echo ""
echo "📝 后续步骤:"
echo "1. 编辑配置文件: vim config/config.yaml"
echo "2. 编辑环境变量: vim .env"
echo "3. 获取闲鱼Cookie（参考README.md）"
echo ""
echo "🚀 启动方式:"
echo "   方式1: ./start.sh"
echo "   方式2: source venv/bin/activate && streamlit run web/app.py"
echo ""

#!/bin/bash
# 代码格式化脚本
# Code Format Script

set -e

echo "======================================"
echo "代码格式化"
echo "Code Format"
echo "======================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 运行Black格式化
echo -e "${YELLOW}运行Black格式化...${NC}"
if command -v black &> /dev/null; then
    black src/ tests/
    echo -e "${GREEN}✓ Black格式化完成${NC}"
else
    echo -e "${YELLOW}⚠ Black未安装，跳过格式化${NC}"
fi
echo ""

# 运行isort导入排序
echo -e "${YELLOW}运行isort导入排序...${NC}"
if command -v isort &> /dev/null; then
    isort src/ tests/
    echo -e "${GREEN}✓ isort导入排序完成${NC}"
elif command -v ruff &> /dev/null; then
    ruff check src/ tests/ --select I --fix
    echo -e "${GREEN}✓ Ruff导入排序完成${NC}"
else
    echo -e "${YELLOW}⚠ isort和ruff未安装，跳过导入排序${NC}"
fi
echo ""

# 运行ruff自动修复
echo -e "${YELLOW}运行Ruff自动修复...${NC}"
if command -v ruff &> /dev/null; then
    ruff check src/ tests/ --fix
    echo -e "${GREEN}✓ Ruff自动修复完成${NC}"
else
    echo -e "${YELLOW}⚠ Ruff未安装，跳过自动修复${NC}"
fi
echo ""

echo "======================================"
echo -e "${GREEN}代码格式化完成！✓${NC}"
echo "======================================"

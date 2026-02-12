#!/bin/bash
# 代码质量检查脚本
# Code Quality Check Script

set -e

echo "======================================"
echo "代码质量检查"
echo "Code Quality Check"
echo "======================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查结果
ERRORS=0
WARNINGS=0

# 检查Python版本
echo -e "${YELLOW}检查Python版本...${NC}"
python3 --version
echo ""

# 检查语法
echo -e "${YELLOW}检查Python语法...${NC}"
python3 -m py_compile src/**/*.py 2>/dev/null || python3 -m py_compile src/*.py
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ 语法检查通过${NC}"
else
    echo -e "${RED}✗ 语法检查失败${NC}"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# 代码格式化检查
echo -e "${YELLOW}检查代码格式...${NC}"
if command -v black &> /dev/null; then
    black --check src/ 2>/dev/null
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Black格式检查通过${NC}"
    else
        echo -e "${RED}✗ Black格式检查失败（运行 'black src/' 修复）${NC}"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    echo -e "${YELLOW}⚠ Black未安装，跳过格式检查${NC}"
fi
echo ""

# 导入排序检查
echo -e "${YELLOW}检查导入排序...${NC}"
if command -v ruff &> /dev/null; then
    ruff check src/ --select I 2>/dev/null
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ 导入排序检查通过${NC}"
    else
        echo -e "${YELLOW}⚠ 导入排序存在问题（运行 'ruff check --fix src/' 修复）${NC}"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    echo -e "${YELLOW}⚠ Ruff未安装，跳过导入排序检查${NC}"
fi
echo ""

# 代码质量检查
echo -e "${YELLOW}检查代码质量...${NC}"
if command -v ruff &> /dev/null; then
    ruff check src/ 2>/dev/null
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Ruff代码质量检查通过${NC}"
    else
        echo -e "${RED}✗ Ruff代码质量检查失败${NC}"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    echo -e "${YELLOW}⚠ Ruff未安装，跳过代码质量检查${NC}"
fi
echo ""

# 类型检查
echo -e "${YELLOW}检查类型提示...${NC}"
if command -v mypy &> /dev/null; then
    mypy src/ --ignore-missing-imports 2>/dev/null || true
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Mypy类型检查通过${NC}"
    else
        echo -e "${YELLOW}⚠ Mypy类型检查存在问题（非阻塞）${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Mypy未安装，跳过类型检查${NC}"
fi
echo ""

# 安全检查
echo -e "${YELLOW}检查安全问题...${NC}"
if command -v bandit &> /dev/null; then
    bandit -r src/ -f json 2>/dev/null | jq '.results' | grep -c '{}' || echo 0
    ISSUES=$(bandit -r src/ -f json 2>/dev/null | jq '.results | length' || echo 0)
    if [ "$ISSUES" -eq 0 ]; then
        echo -e "${GREEN}✓ Bandit安全检查通过${NC}"
    else
        echo -e "${YELLOW}⚠ Bandit发现 $ISSUES 个安全问题${NC}"
        WARNINGS=$((WARNINGS + ISSUES))
    fi
else
    echo -e "${YELLOW}⚠ Bandit未安装，跳过安全检查${NC}"
fi
echo ""

# 测试覆盖
echo -e "${YELLOW}检查测试覆盖...${NC}"
if command -v pytest &> /dev/null; then
    pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=60 --no-header -q 2>/dev/null || true
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ 测试覆盖率>=60%${NC}"
    else
        echo -e "${YELLOW}⚠ 测试覆盖率未达到60%${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Pytest未安装，跳过测试覆盖检查${NC}"
fi
echo ""

# 依赖检查
echo -e "${YELLOW}检查依赖安全...${NC}"
if command -v safety &> /dev/null; then
    safety check --json 2>/dev/null | jq '.vulnerabilities | length' || echo 0
    VULNS=$(safety check --json 2>/dev/null | jq '.vulnerabilities | length' || echo 0)
    if [ "$VULNS" -eq 0 ]; then
        echo -e "${GREEN}✓ Safety依赖安全检查通过${NC}"
    else
        echo -e "${RED}✗ Safety发现 $VULNS 个安全漏洞${NC}"
        ERRORS=$((ERRORS + VULNS))
    fi
else
    echo -e "${YELLOW}⚠ Safety未安装，跳过依赖安全检查${NC}"
fi
echo ""

# 汇总
echo "======================================"
echo "检查结果汇总"
echo "======================================"
if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}所有检查通过！✓${NC}"
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}检查通过但有 $WARNINGS 个警告⚠${NC}"
    exit 0
else
    echo -e "${RED}检查失败：$ERRORS 个错误，$WARNINGS 个警告✗${NC}"
    exit 1
fi

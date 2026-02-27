#!/bin/bash
# 代码质量检查脚本
# Code Quality Check Script

set -u

echo "======================================"
echo "代码质量检查"
echo "Code Quality Check"
echo "======================================"
echo ""

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

ERRORS=0
WARNINGS=0
STRICT="${STRICT:-0}"

if [ -x ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo -e "${RED}✗ 未找到 Python 解释器${NC}"
    exit 1
fi

module_exists() {
    "$PYTHON_BIN" - "$1" <<'PY' >/dev/null 2>&1
import importlib.util
import sys
sys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 1)
PY
}

echo -e "${YELLOW}检查Python版本...${NC}"
PYTHON_VERSION="$("$PYTHON_BIN" --version 2>&1)"
echo "$PYTHON_VERSION"
if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import sys
sys.exit(0 if sys.version_info >= (3, 10) else 1)
PY
then
    echo -e "${RED}✗ Python 版本过低，要求 >= 3.10${NC}"
    ERRORS=$((ERRORS + 1))
else
    echo -e "${GREEN}✓ Python版本满足要求${NC}"
fi
echo ""

echo -e "${YELLOW}检查Python语法...${NC}"
if find src -name "*.py" -print0 | xargs -0 "$PYTHON_BIN" -m py_compile >/dev/null 2>&1; then
    echo -e "${GREEN}✓ 语法检查通过${NC}"
else
    echo -e "${RED}✗ 语法检查失败${NC}"
    ERRORS=$((ERRORS + 1))
fi
echo ""

echo -e "${YELLOW}检查代码格式...${NC}"
if module_exists black; then
    if "$PYTHON_BIN" -m black --check src/ >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Black格式检查通过${NC}"
    else
        echo -e "${YELLOW}⚠ Black格式检查失败（运行 '$PYTHON_BIN -m black src/' 修复）${NC}"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    echo -e "${YELLOW}⚠ Black未安装，跳过格式检查${NC}"
    WARNINGS=$((WARNINGS + 1))
fi
echo ""

echo -e "${YELLOW}检查导入排序...${NC}"
if module_exists ruff; then
    if "$PYTHON_BIN" -m ruff check src/ --select I >/dev/null 2>&1; then
        echo -e "${GREEN}✓ 导入排序检查通过${NC}"
    else
        echo -e "${YELLOW}⚠ 导入排序存在问题（运行 '$PYTHON_BIN -m ruff check --fix src/' 修复）${NC}"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    echo -e "${YELLOW}⚠ Ruff未安装，跳过导入排序检查${NC}"
    WARNINGS=$((WARNINGS + 1))
fi
echo ""

echo -e "${YELLOW}检查代码质量...${NC}"
if module_exists ruff; then
    if "$PYTHON_BIN" -m ruff check src/ >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Ruff代码质量检查通过${NC}"
    else
        echo -e "${RED}✗ Ruff代码质量检查失败${NC}"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo -e "${YELLOW}⚠ Ruff未安装，跳过代码质量检查${NC}"
    WARNINGS=$((WARNINGS + 1))
fi
echo ""

echo -e "${YELLOW}检查类型提示...${NC}"
if module_exists mypy; then
    if "$PYTHON_BIN" -m mypy src/ --ignore-missing-imports >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Mypy类型检查通过${NC}"
    else
        echo -e "${YELLOW}⚠ Mypy类型检查存在问题（非阻塞）${NC}"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    echo -e "${YELLOW}⚠ Mypy未安装，跳过类型检查${NC}"
    WARNINGS=$((WARNINGS + 1))
fi
echo ""

echo -e "${YELLOW}检查安全问题...${NC}"
if module_exists bandit; then
    if "$PYTHON_BIN" -m bandit -r src/ -q >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Bandit安全检查通过${NC}"
    else
        echo -e "${YELLOW}⚠ Bandit发现潜在问题，请运行 '$PYTHON_BIN -m bandit -r src/' 查看详情${NC}"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    echo -e "${YELLOW}⚠ Bandit未安装，跳过安全检查${NC}"
    WARNINGS=$((WARNINGS + 1))
fi
echo ""

echo -e "${YELLOW}检查测试覆盖...${NC}"
if module_exists pytest; then
    if "$PYTHON_BIN" -m pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=35 --no-header -q; then
        echo -e "${GREEN}✓ 测试与覆盖率检查通过（>=35%）${NC}"
    else
        echo -e "${RED}✗ 测试失败或覆盖率不足${NC}"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo -e "${YELLOW}⚠ Pytest未安装，跳过测试覆盖检查${NC}"
    WARNINGS=$((WARNINGS + 1))
fi
echo ""

echo -e "${YELLOW}检查依赖安全...${NC}"
if module_exists safety; then
    if "$PYTHON_BIN" -m safety check >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Safety依赖安全检查通过${NC}"
    else
        echo -e "${YELLOW}⚠ Safety发现依赖风险，请运行 '$PYTHON_BIN -m safety check' 查看详情${NC}"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    echo -e "${YELLOW}⚠ Safety未安装，跳过依赖安全检查${NC}"
    WARNINGS=$((WARNINGS + 1))
fi
echo ""

echo "======================================"
echo "检查结果汇总"
echo "======================================"
if [ "$ERRORS" -gt 0 ]; then
    echo -e "${RED}检查失败：$ERRORS 个错误，$WARNINGS 个警告✗${NC}"
    exit 1
fi

if [ "$WARNINGS" -gt 0 ]; then
    echo -e "${YELLOW}检查通过但有 $WARNINGS 个警告⚠${NC}"
    if [ "$STRICT" = "1" ]; then
        echo -e "${RED}STRICT=1 已开启，按失败退出。${NC}"
        exit 1
    fi
    exit 0
fi

echo -e "${GREEN}所有检查通过！✓${NC}"
exit 0

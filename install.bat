@echo off
REM 闲鱼自动化工具 - Windows一键安装脚本

chcp 65001 >nul
echo ==========================================
echo 🦞 闲鱼自动化工具 - 安装向导
echo ==========================================
echo.

REM 检查Python版本
echo 📋 检查Python版本...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 未检测到Python，请先安装Python 3.10或更高版本
    echo    下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo ✅ 检测到Python版本: %PYTHON_VERSION%

REM 检查Node.js版本
echo.
echo 📋 检查Node.js版本...
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 未检测到Node.js，请先安装Node.js 18或更高版本
    echo    下载地址: https://nodejs.org/
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('node --version') do set NODE_VERSION=%%i
echo ✅ 检测到Node.js版本: %NODE_VERSION%

REM 创建虚拟环境
echo.
echo 🔧 创建Python虚拟环境...
if not exist "venv" (
    python -m venv venv
    echo ✅ 虚拟环境创建成功
) else (
    echo ⚠️  虚拟环境已存在
)

REM 激活虚拟环境
call venv\Scripts\activate.bat

REM 升级pip
echo.
echo 🔧 升级pip...
python -m pip install --upgrade pip -q

REM 安装Python依赖
echo.
echo 📦 安装Python依赖...
pip install -r requirements.txt -q
echo ✅ Python依赖安装完成

REM 复制配置文件
echo.
echo 📋 初始化配置文件...
if not exist "config\config.yaml" (
    copy config\config.example.yaml config\config.yaml >nul
    echo ✅ 配置文件已创建: config\config.yaml
) else (
    echo ⚠️  配置文件已存在
)

if not exist ".env" (
    copy .env.example .env >nul
    echo ✅ 环境变量文件已创建: .env
) else (
    echo ⚠️  环境变量文件已存在
)

REM 安装前端依赖
echo.
echo 📦 安装前端依赖...
cd web\frontend
if not exist "node_modules" (
    call npm install -q
    echo ✅ 前端依赖安装完成
) else (
    echo ⚠️  前端依赖已存在
)
cd ..\..

REM 创建数据目录
echo.
echo 📁 创建数据目录...
if not exist "data\processed_images" mkdir data\processed_images
if not exist "logs" mkdir logs
echo ✅ 数据目录创建完成

REM 构建前端
echo.
echo 🔨 构建前端...
cd web\frontend
call npm run build
cd ..\..
echo ✅ 前端构建完成

echo.
echo ==========================================
echo ✅ 安装完成！
echo ==========================================
echo.
echo 📝 后续步骤:
echo 1. 编辑配置文件: notepad config\config.yaml
echo 2. 编辑环境变量: notepad .env
echo 3. 获取闲鱼Cookie（参考README.md）
echo.
echo 🚀 启动方式:
echo    方式1: 双击 start.bat
echo    方式2: venv\Scripts\activate.bat && streamlit run web\app.py
echo.
pause

@echo off
setlocal enabledelayedexpansion

:: ===========================================
:: Xianyu Automation - Configuration Wizard
:: ===========================================

:: Get project root directory
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%..\.."
set "PROJECT_DIR=%CD%"

echo.
echo ===========================================
echo    Configuration Wizard
echo ===========================================
echo.
echo This wizard will create .env configuration
echo Only 2 items required:
echo   1. AI Service API Key
echo   2. Xianyu Cookie
echo.
pause

:: Initialize variables
set "AI_KEY="
set "COOKIE="
set "AI_PROVIDER=deepseek"
set "AI_MODEL=deepseek-chat"
set "AI_BASE_URL=https://api.deepseek.com/v1"

cls
echo.
echo ===========================================
echo    Step 1/2: Configure AI Service
echo ===========================================
echo.
echo Select AI Provider:
echo.
echo  [1] DeepSeek (Recommended)
echo  [2] Aliyun Bailian
echo  [3] OpenAI
echo  [4] Custom OpenAI-compatible API
echo.
set /p provider="Select (1-4): "

if "!provider!"=="1" (
    set "AI_PROVIDER=deepseek"
    set "AI_MODEL=deepseek-chat"
    set "AI_BASE_URL=https://api.deepseek.com/v1"
    echo.
    echo [Selected] DeepSeek
echo    Get API Key: https://platform.deepseek.com/
)

if "!provider!"=="2" (
    set "AI_PROVIDER=aliyun_bailian"
    set "AI_MODEL=qwen-plus-latest"
    set "AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1"
    echo.
    echo [Selected] Aliyun Bailian
echo    Get API Key: https://dashscope.console.aliyun.com/
)

if "!provider!"=="3" (
    set "AI_PROVIDER=openai"
    set "AI_MODEL=gpt-4o-mini"
    set "AI_BASE_URL=https://api.openai.com/v1"
    echo.
    echo [Selected] OpenAI
echo    Get API Key: https://platform.openai.com/
)

if "!provider!"=="4" (
    echo.
    echo [Selected] Custom API
    echo.
    set /p AI_BASE_URL="Enter Base URL (e.g., https://api.example.com/v1): "
    set /p AI_MODEL="Enter Model Name (e.g., gpt-3.5-turbo): "
    set "AI_PROVIDER=custom"
)

echo.
set /p AI_KEY="Enter API Key: "

if "!AI_KEY!"=="" (
    echo [ERROR] API Key cannot be empty
    pause
    exit /b 1
)

cls
echo.
echo ===========================================
echo    Step 2/2: Configure Xianyu Cookie
echo ===========================================
echo.
echo How to get Cookie:
echo  1. Open browser and visit https://www.goofish.com
echo  2. Login to your Xianyu account
echo  3. Press F12 to open Developer Tools -> Network tab
echo  4. Refresh page, click any request
echo  5. Find Cookie in Request Headers, copy full content
echo.
echo Select input method:
echo  [1] Paste Cookie (single line)
echo  [2] Skip for now, configure later in Dashboard
echo.
set /p cookie_choice="Select (1-2): "

set "COOKIE="
if "!cookie_choice!"=="1" (
    echo.
    echo Paste Cookie content (then press Enter):
    set /p COOKIE=""
)

if "!COOKIE!"=="" (
    echo [INFO] Cookie is empty, will use placeholder
    echo You can configure it later in Dashboard at http://localhost:8091
    set "COOKIE=placeholder_configure_in_dashboard"
)

:: Generate config file
cls
echo.
echo ===========================================
echo    Generating configuration...
echo ===========================================
echo.

(
echo # =====================================
echo # Xianyu Automation Configuration
echo # Generated: %date% %time%
echo # =====================================
echo.
echo # ---- AI Service ----
echo AI_PROVIDER=!AI_PROVIDER!
echo AI_API_KEY=!AI_KEY!
echo AI_BASE_URL=!AI_BASE_URL!
echo AI_MODEL=!AI_MODEL!
echo AI_TEMPERATURE=0.7
echo.
echo # ---- Xianyu Account ----
echo XIANYU_COOKIE_1=!COOKIE!
echo.
echo # ---- System ----
echo DATABASE_URL=sqlite:///data/agent.db
echo ENCRYPTION_KEY=auto-generate
echo.
echo # ---- Features ----
echo QUOTE_ENABLED=true
echo MESSAGES_ENABLED=true
echo WORKFLOW_ENABLED=true
) > "%PROJECT_DIR%\.env"

echo [OK] Configuration saved: %PROJECT_DIR%\.env
echo.
echo Summary:
echo   AI Provider: !AI_PROVIDER!
echo   AI Model: !AI_MODEL!
echo   Cookie Length: !COOKIE:~0,20!...
echo.
echo To modify configuration:
echo   1. Run this wizard again
echo   2. Edit .env file directly
echo   3. Use Dashboard web interface
echo.
pause
exit /b 0

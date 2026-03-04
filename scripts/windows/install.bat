@echo off
setlocal enabledelayedexpansion

:: ===========================================
:: Xianyu Automation - One-Click Deploy
:: ===========================================

:: Get project root directory (parent of scripts/windows/)
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%..\.."
set "PROJECT_DIR=%CD%"

echo [INFO] Project directory: %PROJECT_DIR%

echo.
echo ===========================================
echo    Xianyu Automation - Setup
echo ===========================================
echo.

:: Check if already deployed
if exist "%PROJECT_DIR%\.venv\Scripts\python.exe" (
    echo [OK] Environment already deployed
    goto :CHECK_CONFIG
)

echo [*] Starting first-time setup...
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo Please install Python 3.10+ from https://python.org
    echo Make sure to check "Add Python to PATH"
    pause
    exit /b 1
)

for /f "tokens=*" %%a in ('python --version 2^>^&1') do set "PYTHON_VER=%%a"
echo [OK] Found %PYTHON_VER%

:: Create virtual environment
echo.
echo [*] Creating virtual environment...
python -m venv .venv
if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment
    pause
    exit /b 1
)
echo [OK] Virtual environment created

:: Install dependencies
echo.
echo [*] Installing dependencies (this may take a few minutes)...
.venv\Scripts\pip install -r "%PROJECT_DIR%\requirements.txt" -q
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    echo Retrying with updated pip...
    .venv\Scripts\python -m pip install --upgrade pip -q
    .venv\Scripts\pip install -r "%PROJECT_DIR%\requirements.txt"
    if errorlevel 1 (
        echo [ERROR] Installation failed
        pause
        exit /b 1
    )
)
echo [OK] Dependencies installed

:: Create directories
echo.
echo [*] Creating directories...
mkdir data 2>nul
mkdir logs 2>nul
mkdir config 2>nul
echo [OK] Directories created

:CHECK_CONFIG
:: Check config file
if not exist "%PROJECT_DIR%\.env" (
    echo.
    echo [INFO] No configuration found
    echo.
    goto :CREATE_CONFIG
)

echo [OK] Configuration found

echo.
echo ===========================================
echo    Setup Complete!
echo ===========================================
echo.
echo Select action:
echo.
echo  [1] Start Main Menu
echo  [2] Reconfigure
echo  [3] Exit
echo.
set /p choice="Select (1-3): "

if "%choice%"=="1" goto :START_MENU
if "%choice%"=="2" goto :CREATE_CONFIG
exit /b 0

:CREATE_CONFIG
call scripts\windows\simple_config.bat
if errorlevel 1 (
    echo [ERROR] Configuration failed
    pause
    exit /b 1
)

:START_MENU
call scripts\windows\menu.bat
exit /b 0

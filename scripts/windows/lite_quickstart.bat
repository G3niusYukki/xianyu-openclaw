@echo off
setlocal

cd /d %~dp0\..\..

echo [STEP] 1/4 Lite runtime setup
call scripts\windows\lite_setup.bat
if errorlevel 1 (
  echo [ERROR] lite setup failed.
  exit /b 1
)

echo [STEP] 2/4 Module check (all, strict)
call .venv\Scripts\python -m src.cli module --action check --target all --strict
if errorlevel 1 (
  echo [ERROR] module check failed. Please fix blockers first.
  echo [HINT] Common blockers: missing XIANYU_COOKIE_1 / missing API key / browser runtime not ready.
  exit /b 2
)

echo [STEP] 3/4 Start all modules (background)
call scripts\windows\start_all_lite.bat
if errorlevel 1 (
  echo [ERROR] failed to start all modules.
  exit /b 1
)

echo [STEP] 4/4 Verify module status
call scripts\windows\module_status.bat
if errorlevel 1 (
  echo [ERROR] status check failed.
  exit /b 1
)

echo [OK] Lite quickstart completed.
echo [INFO] Use scripts\windows\launcher.bat for daily operations.
exit /b 0


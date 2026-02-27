@echo off
setlocal

cd /d %~dp0\..\..

echo [STEP] 1/4 Setup Python environment
call scripts\windows\setup_windows.bat
if errorlevel 1 (
  echo [ERROR] setup failed.
  exit /b 1
)

echo [STEP] 2/4 Install Playwright
call .venv\Scripts\python -m pip install --upgrade pip
call .venv\Scripts\python -m pip install playwright
if errorlevel 1 (
  echo [ERROR] playwright install failed.
  exit /b 1
)

echo [STEP] 3/4 Install Chromium runtime
call .venv\Scripts\python -m playwright install chromium
if errorlevel 1 (
  echo [ERROR] playwright chromium install failed.
  exit /b 1
)

echo [STEP] 4/4 Force lite runtime
if not exist .env (
  echo OPENCLAW_RUNTIME=lite> .env
) else (
  findstr /B /C:"OPENCLAW_RUNTIME=" .env >nul
  if errorlevel 1 (
    echo OPENCLAW_RUNTIME=lite>> .env
  ) else (
    powershell -NoProfile -Command "(Get-Content .env) -replace '^OPENCLAW_RUNTIME=.*','OPENCLAW_RUNTIME=lite' | Set-Content .env"
  )
)

echo [OK] Lite runtime ready.
echo [INFO] Run scripts\windows\module_check.bat
echo [INFO] Run scripts\windows\start_all_lite.bat
exit /b 0

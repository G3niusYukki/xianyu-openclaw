@echo off
setlocal

cd /d %~dp0\..\..

echo [STEP] 1/3 Setup Python environment
call scripts\windows\setup_windows.bat
if errorlevel 1 (
  echo [ERROR] setup failed.
  exit /b 1
)

echo [STEP] 2/3 Doctor self-check (strict)
call scripts\windows\doctor.bat --strict
if errorlevel 1 (
  echo [ERROR] doctor check failed. Please fix reported issues first.
  exit /b 1
)

where docker >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker not found in PATH. Install Docker Desktop first.
  exit /b 1
)

echo [STEP] 3/3 Start services via docker compose
docker compose up -d
if errorlevel 1 (
  echo [ERROR] docker compose up -d failed.
  exit /b 1
)

echo [OK] Quickstart finished.
echo [INFO] Web UI: http://localhost:8080
echo [INFO] Dashboard: run scripts\windows\dashboard.bat 8091
echo [INFO] Workflow Worker: run scripts\windows\run_worker.bat 20 5
exit /b 0


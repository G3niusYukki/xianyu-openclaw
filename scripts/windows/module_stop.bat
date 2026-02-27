@echo off
setlocal

cd /d %~dp0\..\..

if not exist .venv\Scripts\python.exe (
  echo [ERROR] .venv not found. Run scripts\windows\setup_windows.bat first.
  exit /b 1
)

set TARGET=%~1
set TIMEOUT=6
if not "%~2"=="" set TIMEOUT=%~2

if not "%TARGET%"=="" (
  call .venv\Scripts\python -m src.cli module --action stop --target %TARGET% --stop-timeout %TIMEOUT%
  exit /b %ERRORLEVEL%
)

echo [INFO] Stop all modules
call .venv\Scripts\python -m src.cli module --action stop --target all --stop-timeout %TIMEOUT%
exit /b %ERRORLEVEL%

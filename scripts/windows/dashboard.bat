@echo off
setlocal

cd /d %~dp0\..\..

if not exist .venv\Scripts\python.exe (
  echo [ERROR] .venv not found. Run scripts\windows\setup_windows.bat first.
  exit /b 1
)

set PORT=8091
if not "%~1"=="" set PORT=%~1

call .venv\Scripts\python -m src.dashboard_server --port %PORT%
exit /b %ERRORLEVEL%

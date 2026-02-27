@echo off
setlocal

cd /d %~dp0\..\..

if not exist .venv\Scripts\python.exe (
  echo [ERROR] .venv not found. Run scripts\windows\setup_windows.bat first.
  exit /b 1
)

set WINDOW=1440
if not "%~1"=="" set WINDOW=%~1

call .venv\Scripts\python -m src.cli messages --action workflow-status --window-minutes %WINDOW%
exit /b %ERRORLEVEL%

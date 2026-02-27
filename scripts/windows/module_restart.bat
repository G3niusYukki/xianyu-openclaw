@echo off
setlocal

cd /d %~dp0\..\..

if not exist .venv\Scripts\python.exe (
  echo [ERROR] .venv not found. Run scripts\windows\setup_windows.bat first.
  exit /b 1
)

set TARGET=%~1
if "%TARGET%"=="" set TARGET=presales

set MODE=daemon
set LIMIT=20
set INTERVAL=5
set ISSUE_TYPE=delay

if /I "%TARGET%"=="operations" set INTERVAL=30
if /I "%TARGET%"=="aftersales" set INTERVAL=15

call .venv\Scripts\python -m src.cli module --action restart --target %TARGET% --mode %MODE% --limit %LIMIT% --interval %INTERVAL% --issue-type %ISSUE_TYPE% --init-default-tasks
exit /b %ERRORLEVEL%

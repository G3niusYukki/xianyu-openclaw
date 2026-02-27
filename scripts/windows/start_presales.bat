@echo off
setlocal

cd /d %~dp0\..\..

if not exist .venv\Scripts\python.exe (
  echo [ERROR] .venv not found. Run scripts\windows\setup_windows.bat first.
  exit /b 1
)

set MODE=daemon
if not "%~1"=="" set MODE=%~1

set LIMIT=20
if not "%~2"=="" set LIMIT=%~2

set INTERVAL=5
if not "%~3"=="" set INTERVAL=%~3

call .venv\Scripts\python -m src.cli module --action start --target presales --mode %MODE% --limit %LIMIT% --interval %INTERVAL%
exit /b %ERRORLEVEL%

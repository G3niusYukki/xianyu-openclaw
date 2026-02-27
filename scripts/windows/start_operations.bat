@echo off
setlocal

cd /d %~dp0\..\..

if not exist .venv\Scripts\python.exe (
  echo [ERROR] .venv not found. Run scripts\windows\setup_windows.bat first.
  exit /b 1
)

set MODE=daemon
if not "%~1"=="" set MODE=%~1

set INTERVAL=30
if not "%~2"=="" set INTERVAL=%~2

set BG=--background
if /I "%~3"=="foreground" set BG=

call .venv\Scripts\python -m src.cli module --action start --target operations --mode %MODE% --interval %INTERVAL% --init-default-tasks %BG%
exit /b %ERRORLEVEL%

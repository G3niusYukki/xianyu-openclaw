@echo off
setlocal

cd /d %~dp0\..\..

if not exist .venv\Scripts\python.exe (
  echo [ERROR] .venv not found. Run scripts\windows\setup_windows.bat first.
  exit /b 1
)

set LIMIT=20
if not "%~1"=="" set LIMIT=%~1

set DRY=
if /I "%~2"=="--dry-run" set DRY=--dry-run

call .venv\Scripts\python -m src.cli messages --action auto-workflow --limit %LIMIT% %DRY%
exit /b %ERRORLEVEL%

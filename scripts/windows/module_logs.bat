@echo off
setlocal

cd /d %~dp0\..\..

if not exist .venv\Scripts\python.exe (
  echo [ERROR] .venv not found. Run scripts\windows\setup_windows.bat first.
  exit /b 1
)

set TARGET=%~1
if "%TARGET%"=="" set TARGET=presales

set LINES=80
if not "%~2"=="" set LINES=%~2

call .venv\Scripts\python -m src.cli module --action logs --target %TARGET% --tail-lines %LINES%
exit /b %ERRORLEVEL%

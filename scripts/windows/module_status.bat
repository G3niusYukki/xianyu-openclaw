@echo off
setlocal

cd /d %~dp0\..\..

if not exist .venv\Scripts\python.exe (
  echo [ERROR] .venv not found. Run scripts\windows\setup_windows.bat first.
  exit /b 1
)

set TARGET=%~1
set LIMIT=20
if not "%~2"=="" set LIMIT=%~2
set WINDOW=1440
if not "%~3"=="" set WINDOW=%~3

if not "%TARGET%"=="" (
  call .venv\Scripts\python -m src.cli module --action status --target %TARGET% --limit %LIMIT% --window-minutes %WINDOW%
  exit /b %ERRORLEVEL%
)

echo [INFO] All module status
call .venv\Scripts\python -m src.cli module --action status --target all --limit %LIMIT% --window-minutes %WINDOW%
exit /b %ERRORLEVEL%

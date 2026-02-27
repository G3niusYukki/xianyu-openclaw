@echo off
setlocal

cd /d %~dp0\..\..

if not exist .venv\Scripts\python.exe (
  echo [ERROR] .venv not found. Run scripts\windows\setup_windows.bat first.
  exit /b 1
)

set WEBHOOK=%~1

if "%WEBHOOK%"=="" (
  call .venv\Scripts\python -m src.cli automation --action setup --notify-on-start
) else (
  call .venv\Scripts\python -m src.cli automation --action setup --enable-feishu --feishu-webhook "%WEBHOOK%" --notify-on-start
)

exit /b %ERRORLEVEL%


@echo off
setlocal

cd /d %~dp0\..\..

if not exist .venv\Scripts\python.exe (
  echo [ERROR] .venv not found. Run scripts\windows\setup_windows.bat first.
  exit /b 1
)

if "%~1"=="" (
  echo Usage: scripts\windows\quote_preview.bat "寄到上海 2kg 圆通 报价"
  exit /b 1
)

call .venv\Scripts\python -m src.cli quote --action preview --message "%~1"
exit /b %ERRORLEVEL%

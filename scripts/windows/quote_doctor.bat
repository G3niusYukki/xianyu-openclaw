@echo off
setlocal

cd /d %~dp0\..\..

if not exist .venv\Scripts\python.exe (
  echo [ERROR] .venv not found. Run scripts\windows\setup_windows.bat first.
  exit /b 1
)

call .venv\Scripts\python -m src.cli quote --action doctor
exit /b %ERRORLEVEL%

@echo off
setlocal

set TARGET=%1
if "%TARGET%"=="" set TARGET=presales

if not exist .venv\Scripts\python.exe (
  echo [ERROR] .venv\Scripts\python.exe not found
  echo Run scripts\windows\setup_windows.bat first.
  exit /b 1
)

call .venv\Scripts\python -m src.cli module --action recover --target %TARGET% --stop-timeout 6
endlocal

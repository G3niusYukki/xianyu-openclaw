@echo off
setlocal

cd /d %~dp0\..\..

if not exist .venv\Scripts\python.exe (
  echo [ERROR] .venv not found. Run scripts\windows\setup_windows.bat first.
  exit /b 1
)

set TARGET=%~1
set STRICT_FLAG=
if /I "%~2"=="strict" set STRICT_FLAG=--strict

if not "%TARGET%"=="" (
  call .venv\Scripts\python -m src.cli module --action check --target %TARGET% %STRICT_FLAG%
  exit /b %ERRORLEVEL%
)

echo [INFO] Check presales
call .venv\Scripts\python -m src.cli module --action check --target presales %STRICT_FLAG%
if errorlevel 1 exit /b 1

echo [INFO] Check operations
call .venv\Scripts\python -m src.cli module --action check --target operations %STRICT_FLAG%
if errorlevel 1 exit /b 1

echo [INFO] Check aftersales
call .venv\Scripts\python -m src.cli module --action check --target aftersales %STRICT_FLAG%
exit /b %ERRORLEVEL%

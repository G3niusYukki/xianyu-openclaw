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

echo [INFO] Presales status
call .venv\Scripts\python -m src.cli module --action status --target presales --limit %LIMIT% --window-minutes %WINDOW%
if errorlevel 1 exit /b 1

echo [INFO] Operations status
call .venv\Scripts\python -m src.cli module --action status --target operations --limit %LIMIT%
if errorlevel 1 exit /b 1

echo [INFO] Aftersales status
call .venv\Scripts\python -m src.cli module --action status --target aftersales --limit %LIMIT%
exit /b %ERRORLEVEL%

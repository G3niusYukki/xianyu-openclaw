@echo off
setlocal

cd /d %~dp0\..\..

if not exist .venv\Scripts\python.exe (
  echo [ERROR] .venv not found. Run scripts\windows\lite_setup.bat first.
  exit /b 1
)

echo [INFO] Starting presales (background)
call scripts\windows\start_presales.bat daemon 20 5
if errorlevel 1 exit /b 1

echo [INFO] Starting operations (background)
call scripts\windows\start_operations.bat daemon 30
if errorlevel 1 exit /b 1

echo [INFO] Starting aftersales (background)
call scripts\windows\start_aftersales.bat daemon 20 15 delay
if errorlevel 1 exit /b 1

echo [OK] All modules started in background.
call scripts\windows\module_status.bat
exit /b %ERRORLEVEL%

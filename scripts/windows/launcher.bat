@echo off
setlocal

cd /d %~dp0\..\..

if not exist .venv\Scripts\python.exe (
  echo [ERROR] .venv not found. Run scripts\windows\setup_windows.bat first.
  exit /b 1
)

:menu
echo.
echo ==================================================
echo  Xianyu OpenClaw - Windows Launcher
echo ==================================================
echo  1) Lite setup (runtime=lite + install playwright)
echo  2) Module check (all, strict)
echo  3) Start all modules (lite, background)
echo  4) Start presales only
echo  5) Start operations only
echo  6) Start aftersales only
echo  7) Module status (all)
echo  8) Module logs
echo  9) Stop all modules
echo  0) Exit
echo ==================================================
set CHOICE=
set /p CHOICE=Select:

if "%CHOICE%"=="1" (
  call scripts\windows\lite_setup.bat
  goto after
)
if "%CHOICE%"=="2" (
  call scripts\windows\module_check.bat all strict
  goto after
)
if "%CHOICE%"=="3" (
  call scripts\windows\start_all_lite.bat
  goto after
)
if "%CHOICE%"=="4" (
  call scripts\windows\start_presales.bat daemon 20 5
  goto after
)
if "%CHOICE%"=="5" (
  call scripts\windows\start_operations.bat daemon 30
  goto after
)
if "%CHOICE%"=="6" (
  call scripts\windows\start_aftersales.bat daemon 20 15 delay
  goto after
)
if "%CHOICE%"=="7" (
  call scripts\windows\module_status.bat
  goto after
)
if "%CHOICE%"=="8" (
  set TARGET=presales
  set /p TARGET=Target [presales/operations/aftersales/all] (default presales):
  if "%TARGET%"=="" set TARGET=presales
  set LINES=80
  set /p LINES=Tail lines (default 80):
  if "%LINES%"=="" set LINES=80
  call scripts\windows\module_logs.bat %TARGET% %LINES%
  goto after
)
if "%CHOICE%"=="9" (
  call scripts\windows\module_stop.bat
  goto after
)
if "%CHOICE%"=="0" exit /b 0

echo [WARN] Invalid option.

:after
echo.
pause
goto menu


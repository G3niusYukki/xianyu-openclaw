@echo off
setlocal enabledelayedexpansion

:: ===========================================
:: Xianyu Automation - Windows Standalone
:: ===========================================

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: If no arguments, show interactive menu
if "%~1"=="" goto :MAIN_MENU

:: Parse command
set "CMD=%~1"
shift

if /i "!CMD!"=="setup" goto :DO_SETUP
if /i "!CMD!"=="install" goto :DO_SETUP
if /i "!CMD!"=="config" goto :DO_CONFIG
if /i "!CMD!"=="start" goto :DO_START
if /i "!CMD!"=="stop" goto :DO_STOP
if /i "!CMD!"=="status" goto :DO_STATUS
if /i "!CMD!"=="logs" goto :DO_LOGS
if /i "!CMD!"=="menu" goto :DO_MENU
if /i "!CMD!"=="help" goto :DO_HELP
if /i "!CMD!"=="-h" goto :DO_HELP
if /i "!CMD!"=="--help" goto :DO_HELP
goto :DO_HELP

:: ===========================================
:: Interactive Menu
:: ===========================================

:MAIN_MENU
cls
echo.
echo ===========================================
echo    Xianyu Automation - Main Menu
echo ===========================================
echo.
echo  [1] First Time Setup
echo  [2] Configuration Wizard
echo  [3] Start Services
echo  [4] Management Menu
echo  [5] Help
echo  [0] Exit
echo.
echo ===========================================
set /p choice="Select option (0-5): "

if "!choice!"=="1" goto :DO_SETUP
if "!choice!"=="2" goto :DO_CONFIG
if "!choice!"=="3" goto :START_SUBMENU
if "!choice!"=="4" goto :DO_MENU
if "!choice!"=="5" goto :DO_HELP
if "!choice!"=="0" exit /b 0
goto :MAIN_MENU

:START_SUBMENU
cls
echo.
echo ===========================================
echo    Start Services
echo ===========================================
echo.
echo  [1] Start All Modules
 echo  [2] Start Presales Only
echo  [3] Start Operations Only
echo  [4] Start Aftersales Only
echo  [0] Back to Main Menu
echo.
set /p start_choice="Select option (0-4): "

if "!start_choice!"=="1" (
    call scripts\windows\start_module.bat presales daemon
    call scripts\windows\start_module.bat operations daemon
    call scripts\windows\start_module.bat aftersales daemon
    echo.
    echo Press any key to continue...
    pause >nul
)
if "!start_choice!"=="2" (
    call scripts\windows\start_module.bat presales daemon
    echo.
    echo Press any key to continue...
    pause >nul
)
if "!start_choice!"=="3" (
    call scripts\windows\start_module.bat operations daemon
    echo.
    echo Press any key to continue...
    pause >nul
)
if "!start_choice!"=="4" (
    call scripts\windows\start_module.bat aftersales daemon
    echo.
    echo Press any key to continue...
    pause >nul
)
if "!start_choice!"=="0" goto :MAIN_MENU
goto :MAIN_MENU

:: ===========================================
:: Commands
:: ===========================================

:DO_SETUP
call scripts\windows\install.bat
exit /b %ERRORLEVEL%

:DO_CONFIG
call scripts\windows\simple_config.bat
exit /b %ERRORLEVEL%

:DO_START
set "MODULE=%~1"
if "!MODULE!"=="" set "MODULE=all"
if /i "!MODULE!"=="all" (
    echo Starting all modules...
    call scripts\windows\start_module.bat presales daemon
    call scripts\windows\start_module.bat operations daemon
    call scripts\windows\start_module.bat aftersales daemon
) else (
    call scripts\windows\start_module.bat !MODULE! daemon
)
exit /b %ERRORLEVEL%

:DO_STOP
set "MODULE=%~1"
if "!MODULE!"=="" set "MODULE=all"
call scripts\windows\stop_module.bat !MODULE!
exit /b %ERRORLEVEL%

:DO_STATUS
call scripts\windows\status.bat
exit /b %ERRORLEVEL%

:DO_LOGS
set "MODULE=%~1"
call scripts\windows\view_logs.bat !MODULE!
exit /b %ERRORLEVEL%

:DO_MENU
call scripts\windows\menu.bat
exit /b %ERRORLEVEL%

:DO_HELP
echo.
echo ===========================================
echo    Xianyu Automation - Help
echo ===========================================
echo.
echo Usage: xianyu [command] [options]
echo.
echo Commands:
echo   setup             First time setup
echo   config            Configuration wizard
echo   start [module]    Start modules (presales/operations/aftersales/all)
echo   stop [module]     Stop modules
echo   status            Check status
echo   logs [module]     View logs
echo   menu              Interactive menu
echo.
echo Examples:
echo   xianyu setup                    # First setup
echo   xianyu start all                # Start all
echo   xianyu start presales           # Start presales only
echo   xianyu status                   # Check status
echo.
echo Press any key to continue...
pause >nul
if "%~1"=="" goto :MAIN_MENU
exit /b 0

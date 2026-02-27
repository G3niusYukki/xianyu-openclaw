@echo off
setlocal

cd /d %~dp0\..\..

if not exist .venv\Scripts\python.exe (
  echo [ERROR] .venv not found. Run scripts\windows\setup_windows.bat first.
  exit /b 1
)

if "%~1"=="" (
  echo [ERROR] usage: workflow_transition.bat SESSION_ID STAGE [--force-state]
  exit /b 1
)

if "%~2"=="" (
  echo [ERROR] usage: workflow_transition.bat SESSION_ID STAGE [--force-state]
  exit /b 1
)

set SESSION_ID=%~1
set STAGE=%~2
set FORCE=
if /I "%~3"=="--force-state" set FORCE=--force-state

call .venv\Scripts\python -m src.cli messages --action workflow-transition --session-id %SESSION_ID% --stage %STAGE% %FORCE%
exit /b %ERRORLEVEL%

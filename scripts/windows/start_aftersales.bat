@echo off
setlocal

cd /d %~dp0\..\..

if not exist .venv\Scripts\python.exe (
  echo [ERROR] .venv not found. Run scripts\windows\setup_windows.bat first.
  exit /b 1
)

set MODE=daemon
if not "%~1"=="" set MODE=%~1

set LIMIT=20
if not "%~2"=="" set LIMIT=%~2

set INTERVAL=15
if not "%~3"=="" set INTERVAL=%~3

set ISSUE_TYPE=delay
if not "%~4"=="" set ISSUE_TYPE=%~4

set DRYRUN=
if /I "%~5"=="dry-run" set DRYRUN=--dry-run

set BG=--background
if /I "%~6"=="foreground" set BG=

call .venv\Scripts\python -m src.cli module --action start --target aftersales --mode %MODE% --limit %LIMIT% --interval %INTERVAL% --issue-type %ISSUE_TYPE% %DRYRUN% %BG%
exit /b %ERRORLEVEL%

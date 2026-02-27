@echo off
setlocal

cd /d %~dp0\..\..

if not exist .venv\Scripts\python.exe (
  echo [ERROR] .venv not found. Run scripts\windows\setup_windows.bat first.
  exit /b 1
)

set ORIGIN_CITY=%~1
if "%ORIGIN_CITY%"=="" set ORIGIN_CITY=安徽

set COST_DIR=%~2
if "%COST_DIR%"=="" set COST_DIR=data/quote_costs

call .venv\Scripts\python -m src.cli quote --action setup --mode cost_table_plus_markup --origin-city "%ORIGIN_CITY%" --cost-table-dir "%COST_DIR%" --pricing-profile normal
exit /b %ERRORLEVEL%

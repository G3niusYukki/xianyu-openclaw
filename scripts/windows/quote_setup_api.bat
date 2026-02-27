@echo off
setlocal

cd /d %~dp0\..\..

if not exist .venv\Scripts\python.exe (
  echo [ERROR] .venv not found. Run scripts\windows\setup_windows.bat first.
  exit /b 1
)

if "%~1"=="" (
  echo Usage: scripts\windows\quote_setup_api.bat ^<cost_api_url^> [origin_city] [cost_table_dir]
  exit /b 1
)

set COST_API_URL=%~1
set ORIGIN_CITY=%~2
if "%ORIGIN_CITY%"=="" set ORIGIN_CITY=安徽

set COST_DIR=%~3
if "%COST_DIR%"=="" set COST_DIR=data/quote_costs

call .venv\Scripts\python -m src.cli quote --action setup --mode api_cost_plus_markup --origin-city "%ORIGIN_CITY%" --cost-table-dir "%COST_DIR%" --cost-api-url "%COST_API_URL%" --pricing-profile normal
exit /b %ERRORLEVEL%

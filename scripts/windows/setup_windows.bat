@echo off
setlocal ENABLEDELAYEDEXPANSION

cd /d %~dp0\..\..

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found in PATH.
  exit /b 1
)

if not exist .venv (
  echo [INFO] Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 exit /b 1
)

echo [INFO] Installing dependencies...
call .venv\Scripts\pip install -r requirements.txt
if errorlevel 1 exit /b 1

if not exist .env (
  echo [INFO] Creating .env from .env.example...
  copy .env.example .env >nul
)

if not exist config\config.yaml (
  echo [INFO] Creating config\config.yaml from config\config.example.yaml...
  copy config\config.example.yaml config\config.yaml >nul
)

if not exist data mkdir data
if not exist logs mkdir logs
if not exist data\quote_costs mkdir data\quote_costs
if not exist data\processed_images mkdir data\processed_images

echo [OK] Windows setup finished.
exit /b 0

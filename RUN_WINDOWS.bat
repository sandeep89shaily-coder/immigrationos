@echo off
setlocal
title ImmigrationOS Workspace v0.3 - Development Only
cd /d "%~dp0"
where docker >nul 2>nul
if errorlevel 1 (
  echo Docker not found. Install and start Docker Desktop before continuing.
  pause
  exit /b 1
)
docker info >nul 2>nul
if errorlevel 1 (
  echo Docker Desktop is not running. Please start Docker Desktop.
  pause
  exit /b 1
)
echo Starting ImmigrationOS development stack. Synthetic data only.
docker compose up --build -d
if errorlevel 1 (
  echo Docker startup failed. Run docker compose logs to see the error.
  pause
  exit /b 1
)
docker compose ps
echo.
echo CONSULTANT WORKSPACE: http://localhost:8000/app
echo API docs: http://localhost:8000/docs
echo Keycloak: http://localhost:8080/
echo IMPORTANT: Do not enter real client data in this development system.
start "" "http://localhost:8000/app"
pause

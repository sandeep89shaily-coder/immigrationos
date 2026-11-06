@echo off
setlocal
title ImmigrationOS Foundation - Local Checks
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python is not installed. Install Python 3.11+.
  pause
  exit /b 1
)
py -m pip install -e ".[test]"
if errorlevel 1 (
  echo Dependency installation failed.
  pause
  exit /b 1
)
py -m pytest -q
pause

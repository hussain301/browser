@echo off
title Dola.ai QA Automation — Startup
echo ============================================
echo   Dola.ai QA ^& Account Testing Automation
echo ============================================

:: Check playwright is installed
python -c "import playwright" 2>nul
if %errorlevel% neq 0 (
    echo [Setup] Installing playwright...
    python -m pip install playwright --no-cache-dir
)

:: Install Chromium browser if not already present
echo [Setup] Ensuring Chromium is installed...
python -m playwright install chromium 2>nul

echo.
echo [Starting] Launching application...
python main.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application exited with an error. See above for details.
    pause
)

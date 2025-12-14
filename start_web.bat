@echo off
chcp 65001 > nul 2>&1
cls

:: Перехід в директорію скрипта
cd /d %~dp0

echo =============================================================
echo    ZAPUSK WEB INTERFACE - TeachHub Admin v2.0
echo =============================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo ERROR: venv not found!
    echo Run setup.bat first
    pause
    exit /b 1
)

if not exist "config.env" (
    echo ERROR: config.env not found!
    echo Run setup.bat first
    pause
    exit /b 1
)

if not exist "schedule_bot.db" (
    echo ERROR: Database not found!
    echo Run setup.bat first
    pause
    exit /b 1
)

echo.
echo =============================================================
echo    Starting Web Interface...
echo =============================================================
echo.

REM Check mode
if "%FLASK_ENV%"=="production" (
    echo Mode: PRODUCTION (Waitress)
    echo URL: Check config.env for HOST and PORT settings
) else (
    echo Mode: DEVELOPMENT (Flask dev server)
    echo URL: http://127.0.0.1:5000
)
echo Press Ctrl+C to stop
echo.

venv\Scripts\python.exe run_web.py

pause

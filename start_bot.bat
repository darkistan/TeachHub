@echo off
chcp 65001 > nul
cls
echo =============================================================
echo    ZAPUSK TELEGRAM BOT - TeachHub v2.0
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
echo    Starting Telegram Bot...
echo =============================================================
echo.
echo Press Ctrl+C to stop
echo.

venv\Scripts\python.exe bot.py

pause

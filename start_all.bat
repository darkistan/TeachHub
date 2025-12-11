@echo off
chcp 65001 > nul
cls
echo =============================================================
echo    STARTING FULL SYSTEM - TeachHub v2.0
echo =============================================================
echo.
echo Starting:
echo   1. Telegram Bot
echo   2. Web Interface
echo.
echo Two windows will open - DO NOT CLOSE THEM!
echo.
pause

start "TeachHub - Telegram Bot" cmd /k "start_bot.bat"

timeout /t 3 /nobreak > nul

start "TeachHub - Web Admin" cmd /k "start_web.bat"

cls
echo.
echo =============================================================
echo    SYSTEM STARTED
echo =============================================================
echo.
echo Bot: Running in first window
echo Web: http://127.0.0.1:5000
echo.
echo To stop: Close both windows or press Ctrl+C
echo.

pause

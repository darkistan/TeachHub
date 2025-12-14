@echo off
chcp 65001 > nul
cls
echo =============================================================
echo    GENERATE FLASK SECRET KEY
echo =============================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo ERROR: venv not found!
    echo Run setup.bat first
    pause
    exit /b 1
)

venv\Scripts\python.exe generate_secret_key.py

pause


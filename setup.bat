@echo off
chcp 65001 > nul
cls
echo =============================================================
echo    SETUP Schedule Bot v2.0
echo =============================================================
echo.

python --version > nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found!
    echo Install Python 3.8+ from python.org
    pause
    exit /b 1
)

echo Python found:
python --version
echo.

if exist "venv" (
    echo venv already exists
    set /p RECREATE="Recreate venv? (y/n): "
    if /i "%RECREATE%"=="y" (
        echo Removing old venv...
        rmdir /s /q venv
        echo Creating new venv...
        python -m venv venv
    )
) else (
    echo Creating virtual environment...
    python -m venv venv
)
echo.

echo Installing dependencies...
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
echo.

if not exist "config.env" (
    echo Creating config.env...
    copy config.env.example config.env
    echo.
    echo IMPORTANT: Edit config.env and add:
    echo    - TELEGRAM_BOT_TOKEN from @BotFather
    echo    - ADMIN_USER_ID your Telegram ID
    echo    - ALERTS_API_TOKEN from alerts.in.ua
    echo.
    notepad config.env
)
echo.

if not exist "schedule_bot.db" (
    echo Creating database...
    venv\Scripts\python.exe -c "from database import init_database; init_database(); print('Database created')"
)
echo.

echo Checking database...
venv\Scripts\python.exe check_db_status.py check
echo.

echo =============================================================
echo    SETUP COMPLETE!
echo =============================================================
echo.
echo Next steps:
echo    1. Check config.env (tokens)
echo    2. Run: start_all.bat
echo.

pause

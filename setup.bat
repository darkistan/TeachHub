@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
cls
echo =============================================================
echo    SETUP TeachHub v2.0
echo =============================================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found!
    echo Please install Python 3.8+ from python.org
    echo.
    pause
    exit /b 1
)

echo [OK] Python found:
python --version
echo.

REM Create venv
if exist venv (
    echo [INFO] venv already exists
    set /p RECREATE="Recreate venv? (y/n): "
    if /i "!RECREATE!"=="y" (
        echo [INFO] Removing old venv...
        rmdir /s /q venv 2>nul
        echo [INFO] Creating new venv...
        python -m venv venv
        if errorlevel 1 (
            echo [ERROR] Failed to create venv!
            echo.
            pause
            exit /b 1
        )
        echo [OK] venv created
    ) else (
        echo [INFO] Using existing venv
    )
) else (
    echo [INFO] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv!
        echo.
        pause
        exit /b 1
    )
    echo [OK] venv created
)
echo.

REM Check venv
if not exist venv\Scripts\python.exe (
    echo [ERROR] venv was not created properly!
    echo Please check Python installation.
    echo.
    pause
    exit /b 1
)

REM Upgrade pip
echo [INFO] Upgrading pip...
venv\Scripts\python.exe -m pip install --upgrade pip >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Failed to upgrade pip, continuing anyway...
) else (
    echo [OK] pip upgraded
)
echo.

REM Install dependencies
echo [INFO] Installing dependencies from requirements.txt...
venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies!
    echo Please check requirements.txt file.
    echo.
    pause
    exit /b 1
)
echo [OK] Dependencies installed
echo.

REM Create config.env
if not exist config.env (
    echo [INFO] Creating config.env...
    if exist config.env.example (
        copy config.env.example config.env >nul
        echo [OK] config.env created from config.env.example
    ) else (
        echo [WARNING] config.env.example not found, creating empty config.env
        echo. > config.env
    )
    echo.
    echo [IMPORTANT] Edit config.env and add:
    echo    - TELEGRAM_BOT_TOKEN from BotFather
    echo    - FLASK_SECRET_KEY random string for web admin
    echo    - ALERTS_API_TOKEN from alerts.in.ua
    echo.
    set /p OPENEDITOR="Open config.env in notepad now? (y/n): "
    if /i "!OPENEDITOR!"=="y" (
        notepad config.env
    )
) else (
    echo [INFO] config.env already exists
)
echo.

REM Create database
if not exist schedule_bot.db (
    echo [INFO] Creating database...
    venv\Scripts\python.exe -c "from database import init_database; init_database(); print('[OK] Database created')" 2>&1
    if errorlevel 1 (
        echo [WARNING] Failed to create database!
        echo Database will be created on first run.
    )
) else (
    echo [INFO] Database already exists
)
echo.

echo =============================================================
echo    SETUP COMPLETE!
echo =============================================================
echo.
echo Next steps:
echo    1. Edit config.env and add required tokens
echo    2. Run start_all.bat to start bot and web interface
echo    3. Set password for admin user via web interface
echo.
echo Press any key to exit...
pause >nul

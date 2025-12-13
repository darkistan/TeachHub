@echo off
chcp 65001 > nul
cls
echo =============================================================
echo    ВІДНОВЛЕННЯ ПАРОЛЯ АДМІНІСТРАТОРА - TeachHub
echo =============================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo ERROR: venv not found!
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
echo Цей скрипт дозволяє відновити пароль адміністратора,
echo якщо ви забули пароль після зміни стандартного.
echo.
echo =============================================================
echo.

venv\Scripts\python.exe reset_admin_password.py

echo.
pause


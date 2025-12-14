@echo off
chcp 65001 >nul 2>&1

echo ========================================
echo Cloudflare Tunnel - Видалення служби
echo ========================================
echo.

:: Перевірка адміністративних прав
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ПОМИЛКА] Потрібні адміністративні права!
    echo Запустіть скрипт як адміністратор.
    pause
    exit /b 1
)

:: Перевірка чи встановлена служба
sc query CloudflareTunnel >nul 2>&1
if %errorLevel% neq 0 (
    echo [УВАГА] Служба не встановлена!
    pause
    exit /b 0
)

:: Зупинка служби
echo Зупинка служби...
sc stop CloudflareTunnel
timeout /t 2 >nul

:: Видалення служби
echo Видалення служби...
sc delete CloudflareTunnel
if %errorLevel% equ 0 (
    echo Служба успішно видалена!
) else (
    echo [ПОМИЛКА] Не вдалося видалити службу!
)

:: Видалення batch-файлу служби
set "SCRIPT_DIR=%~dp0"
set "SERVICE_BAT=%SCRIPT_DIR%run_tunnel_service.bat"
if exist "%SERVICE_BAT%" (
    del "%SERVICE_BAT%"
    echo Видалено: run_tunnel_service.bat
)

echo.
pause


@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo ========================================
echo Cloudflare Tunnel - Запуск
echo ========================================
echo.

set "SCRIPT_DIR=%~dp0"
set "TUNNEL_DIR=%SCRIPT_DIR%cloudflared"
set "CONFIG_DIR=%SCRIPT_DIR%config"
set "LOGS_DIR=%SCRIPT_DIR%logs"
set "CLOUDFLARED_EXE=%TUNNEL_DIR%\cloudflared.exe"
set "CONFIG_FILE=%CONFIG_DIR%\config.yaml"
set "LOG_FILE=%LOGS_DIR%\cloudflared.log"

:: Перевірка встановлення
if not exist "%CLOUDFLARED_EXE%" (
    echo [ПОМИЛКА] cloudflared не встановлено!
    echo Запустіть install_tunnel.bat спочатку.
    pause
    exit /b 1
)

if not exist "%CONFIG_FILE%" (
    echo [ПОМИЛКА] Конфігурація не знайдена!
    echo Запустіть install_tunnel.bat спочатку.
    pause
    exit /b 1
)

:: Перевірка чи вже запущено
tasklist /FI "IMAGENAME eq cloudflared.exe" 2>NUL | find /I /N "cloudflared.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo [УВАГА] Тунель вже запущено!
    echo.
    set /p RESTART="Перезапустити? (y/n): "
    if /i not "!RESTART!"=="y" (
        echo Запуск скасовано.
        pause
        exit /b 0
    )
    echo Зупинка поточного процесу...
    taskkill /F /IM cloudflared.exe >nul 2>&1
    timeout /t 2 >nul
    echo.
)

:: Запуск тунелю
echo Запуск Cloudflare Tunnel...
echo Логи зберігаються в: %LOG_FILE%
echo.
echo Для зупинки натисніть Ctrl+C
echo.

"%CLOUDFLARED_EXE%" tunnel --config "%CONFIG_FILE%" run >> "%LOG_FILE%" 2>&1

pause


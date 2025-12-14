@echo off
chcp 65001 >nul 2>&1

echo ========================================
echo Cloudflare Tunnel - Статус
echo ========================================
echo.

:: Перевірка процесу
tasklist /FI "IMAGENAME eq cloudflared.exe" 2>NUL | find /I /N "cloudflared.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo [✓] Тунель запущено
    echo.
    echo Процеси cloudflared:
    tasklist /FI "IMAGENAME eq cloudflared.exe"
) else (
    echo [✗] Тунель не запущено
)

echo.

:: Перевірка конфігурації
set "SCRIPT_DIR=%~dp0"
set "CONFIG_FILE=%SCRIPT_DIR%config\config.yaml"

if exist "%CONFIG_FILE%" (
    echo [✓] Конфігурація знайдена
    echo.
    echo Конфігурація:
    type "%CONFIG_FILE%"
) else (
    echo [✗] Конфігурація не знайдена
)

echo.

:: Перевірка логів
set "LOG_FILE=%SCRIPT_DIR%logs\cloudflared.log"
if exist "%LOG_FILE%" (
    echo Останні 10 рядків логів:
    echo ----------------------------------------
    powershell -Command "Get-Content '%LOG_FILE%' -Tail 10"
) else (
    echo Логи не знайдено
)

echo.
pause


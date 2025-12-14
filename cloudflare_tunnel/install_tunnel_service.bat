@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo ========================================
echo Cloudflare Tunnel - Встановлення служби
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

set "SCRIPT_DIR=%~dp0"
set "TUNNEL_DIR=%SCRIPT_DIR%cloudflared"
set "CONFIG_DIR=%SCRIPT_DIR%config"
set "CLOUDFLARED_EXE=%TUNNEL_DIR%\cloudflared.exe"
set "CONFIG_FILE=%CONFIG_DIR%\config.yaml"

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

:: Перевірка чи вже встановлена служба
sc query CloudflareTunnel >nul 2>&1
if %errorLevel% equ 0 (
    echo [УВАГА] Служба вже встановлена!
    echo.
    set /p REINSTALL="Перевстановити? (y/n): "
    if /i not "!REINSTALL!"=="y" (
        echo Встановлення скасовано.
        pause
        exit /b 0
    )
    echo Видалення старої служби...
    sc stop CloudflareTunnel >nul 2>&1
    timeout /t 2 >nul
    sc delete CloudflareTunnel >nul 2>&1
    timeout /t 1 >nul
    echo.
)

:: Створення batch-файлу для служби
set "SERVICE_BAT=%SCRIPT_DIR%run_tunnel_service.bat"
(
    echo @echo off
    echo cd /d "%SCRIPT_DIR%"
    echo "%CLOUDFLARED_EXE%" tunnel --config "%CONFIG_FILE%" run
) > "%SERVICE_BAT%"

:: Створення служби через sc
echo Створення служби Windows...
sc create CloudflareTunnel ^
    binPath= "\"%SERVICE_BAT%\"" ^
    DisplayName= "Cloudflare Tunnel" ^
    start= auto ^
    obj= "NT AUTHORITY\LocalService"

if %errorLevel% neq 0 (
    echo [ПОМИЛКА] Не вдалося створити службу!
    echo Спробуйте використати NSSM (Non-Sucking Service Manager).
    echo.
    echo Завантажте NSSM: https://nssm.cc/download
    echo Потім запустіть:
    echo   nssm install CloudflareTunnel "%SERVICE_BAT%"
    pause
    exit /b 1
)

:: Запуск служби
echo Запуск служби...
sc start CloudflareTunnel
if %errorLevel% equ 0 (
    echo Служба успішно запущена!
) else (
    echo [ПОМИЛКА] Не вдалося запустити службу!
    echo Перевірте логи Windows Event Viewer.
)

echo.
echo ========================================
echo Встановлення служби завершено!
echo ========================================
echo.
echo Служба буде запускатися автоматично при старті системи.
echo.
echo Управління службою:
echo   Запуск:   sc start CloudflareTunnel
echo   Зупинка:  sc stop CloudflareTunnel
echo   Статус:   sc query CloudflareTunnel
echo.
pause


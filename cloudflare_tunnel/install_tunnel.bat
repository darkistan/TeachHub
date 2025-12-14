@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo ========================================
echo Cloudflare Tunnel - Встановлення
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

:: Встановлення директорій
set "SCRIPT_DIR=%~dp0"
set "TUNNEL_DIR=%SCRIPT_DIR%cloudflared"
set "CONFIG_DIR=%SCRIPT_DIR%config"
set "LOGS_DIR=%SCRIPT_DIR%logs"

if not exist "%TUNNEL_DIR%" mkdir "%TUNNEL_DIR%"
if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"
if not exist "%LOGS_DIR%" mkdir "%LOGS_DIR%"

:: Перевірка чи вже встановлено
if exist "%CONFIG_DIR%\config.yaml" (
    echo [УВАГА] Тунель вже встановлено!
    echo.
    set /p REINSTALL="Перевстановити? (y/n): "
    if /i not "!REINSTALL!"=="y" (
        echo Встановлення скасовано.
        pause
        exit /b 0
    )
    echo.
)

:: Завантаження cloudflared
echo [1/5] Завантаження cloudflared...
set "CLOUDFLARED_URL=https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
set "CLOUDFLARED_EXE=%TUNNEL_DIR%\cloudflared.exe"

if not exist "%CLOUDFLARED_EXE%" (
    echo Завантаження з GitHub...
    powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%CLOUDFLARED_URL%' -OutFile '%CLOUDFLARED_EXE%'}"
    if %errorLevel% neq 0 (
        echo [ПОМИЛКА] Не вдалося завантажити cloudflared!
        pause
        exit /b 1
    )
    echo Завантажено успішно.
) else (
    echo cloudflared вже завантажено.
)
echo.

:: Введення даних
echo [2/5] Введення даних для налаштування...
echo.

set /p TUNNEL_TOKEN="Введіть Tunnel Token з Cloudflare Dashboard: "
if "!TUNNEL_TOKEN!"=="" (
    echo [ПОМИЛКА] Tunnel Token не може бути порожнім!
    pause
    exit /b 1
)

set /p DOMAIN="Введіть домен (наприклад: teachhub.example.com): "
if "!DOMAIN!"=="" (
    echo [ПОМИЛКА] Домен не може бути порожнім!
    pause
    exit /b 1
)

set /p LOCAL_PORT="Введіть локальний порт (за замовчуванням 5000): "
if "!LOCAL_PORT!"=="" set "LOCAL_PORT=5000"

echo.
echo [3/5] Створення конфігурації...

:: Створення config.yaml
set "CONFIG_FILE=%CONFIG_DIR%\config.yaml"
(
    echo tunnel: !TUNNEL_TOKEN!
    echo credentials-file: %CONFIG_DIR%\credentials.json
    echo.
    echo ingress:
    echo   - hostname: !DOMAIN!
    echo     service: http://localhost:!LOCAL_PORT!
    echo   - service: http_status:404
) > "%CONFIG_FILE%"

echo Конфігурація створена: %CONFIG_FILE%
echo.

:: Автентифікація
echo [4/5] Автентифікація в Cloudflare...
"%CLOUDFLARED_EXE%" tunnel login
if %errorLevel% neq 0 (
    echo [ПОМИЛКА] Не вдалося автентифікуватися!
    echo Перевірте Tunnel Token.
    pause
    exit /b 1
)
echo.

:: Створення тунелю
echo [5/5] Створення тунелю...
"%CLOUDFLARED_EXE%" tunnel --config "%CONFIG_FILE%" run
if %errorLevel% neq 0 (
    echo [ПОМИЛКА] Не вдалося створити тунель!
    pause
    exit /b 1
)
echo.

echo ========================================
echo Встановлення завершено успішно!
echo ========================================
echo.
echo Наступні кроки:
echo 1. Налаштуйте Public Hostname в Cloudflare Dashboard
echo 2. Запустіть тунель: start_tunnel.bat
echo 3. Або встановіть як службу: install_tunnel_service.bat
echo.
pause


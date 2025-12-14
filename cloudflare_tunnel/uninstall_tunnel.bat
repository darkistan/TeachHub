@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo ========================================
echo Cloudflare Tunnel - Видалення
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

:: Зупинка тунелю
echo [1/3] Зупинка тунелю...
call "%~dp0stop_tunnel.bat" >nul 2>&1
timeout /t 1 >nul

:: Видалення служби (якщо встановлена)
echo [2/3] Перевірка служби Windows...
sc query CloudflareTunnel >nul 2>&1
if %errorLevel% equ 0 (
    echo Видалення служби CloudflareTunnel...
    sc stop CloudflareTunnel >nul 2>&1
    timeout /t 2 >nul
    sc delete CloudflareTunnel >nul 2>&1
    echo Служба видалена.
) else (
    echo Служба не встановлена.
)

:: Видалення файлів
echo [3/3] Видалення файлів...
set "SCRIPT_DIR=%~dp0"

set /p CONFIRM="Видалити всі файли тунелю? (y/n): "
if /i "!CONFIRM!"=="y" (
    if exist "%SCRIPT_DIR%cloudflared" (
        rmdir /s /q "%SCRIPT_DIR%cloudflared"
        echo Видалено: cloudflared\
    )
    if exist "%SCRIPT_DIR%config" (
        rmdir /s /q "%SCRIPT_DIR%config"
        echo Видалено: config\
    )
    if exist "%SCRIPT_DIR%logs" (
        rmdir /s /q "%SCRIPT_DIR%logs"
        echo Видалено: logs\
    )
    echo.
    echo Всі файли видалено.
) else (
    echo Файли залишено.
)

echo.
echo ========================================
echo Видалення завершено!
echo ========================================
echo.
pause


@echo off
chcp 65001 >nul 2>&1

echo ========================================
echo Cloudflare Tunnel - Зупинка
echo ========================================
echo.

:: Перевірка чи запущено
tasklist /FI "IMAGENAME eq cloudflared.exe" 2>NUL | find /I /N "cloudflared.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo Зупинка Cloudflare Tunnel...
    taskkill /F /IM cloudflared.exe
    if %errorLevel% equ 0 (
        echo Тунель успішно зупинено.
    ) else (
        echo [ПОМИЛКА] Не вдалося зупинити тунель!
    )
) else (
    echo Тунель не запущено.
)

echo.
pause


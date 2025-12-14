@echo off
chcp 65001 >nul 2>&1

echo ========================================
echo Cloudflare Tunnel - Перезапуск
echo ========================================
echo.

call "%~dp0stop_tunnel.bat"
timeout /t 2 >nul
call "%~dp0start_tunnel.bat"


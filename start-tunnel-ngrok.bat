@echo off
title CAD Studio - Fixed Static Link (Ngrok)
chcp 65001 >nul
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-tunnel-ngrok.ps1"

echo.
echo ==============================================================================
echo   Ket noi da dong. Nhan phim bat ky de thoat...
echo ==============================================================================
pause >nul

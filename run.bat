@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: Giai phong port 8765 neu co tien trinh cu dang chay
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :8765 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)

set CAD_ALLOW_REMOTE=1

set "PYCMD=python"
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PYCMD=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
)

echo ===================================================
echo   Mechanical AI Drawing dang mo tai:
echo   http://127.0.0.1:8765/
echo   (Nhan Ctrl+C de dung server)
echo ===================================================
start http://127.0.0.1:8765/
"%PYCMD%" -m uvicorn backend.main:app --host 0.0.0.0 --port 8765 --proxy-headers --forwarded-allow-ips=*
pause


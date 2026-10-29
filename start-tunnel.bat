@echo off
title Cloudflare Tunnel - Mechanical AI Drawing
cd /d "%~dp0"
:: Tat tien trinh tunnel cu neu dang bi treo
taskkill /F /IM cloudflared.exe >nul 2>&1

echo ==============================================================================
echo        KHOI DONG DUONG LINK CHO MAY KHAC TRUY CAP - CAD STUDIO
echo ==============================================================================
echo.

:: Tim dia chi IP mang noi bo (LAN/Wifi)
set "LOCAL_IP="
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4 Address" /c:"IPv4" 2^>nul') do (
    if not defined LOCAL_IP set "LOCAL_IP=%%a"
)
if defined LOCAL_IP set "LOCAL_IP=%LOCAL_IP: =%"

echo   [CACH 1] MAY TINH / DIEN THOAI TRONG CUNG MANG WIFI HOAC LAN:
if defined LOCAL_IP (
    echo       Truy cap truc tiep theo dia chi:
    echo       -^> http://%LOCAL_IP%:8765/
) else (
    echo       Truy cap theo dia chi IP may chu (vi du: http://192.168.1.142:8765/)
)
echo.
echo   [CACH 2] TRUY CAP QUA INTERNET (CLOUDFLARE TUNNEL - KHONG CAN CUNG MANG):
echo       Dang khoi tao link cong khai toan cau (https://...trycloudflare.com)...
echo       Duong link se xuat hien ben duoi sau khoang 3-5 giay.
echo       Ban chi can copy link do gui cho nguoi khac la ho vao duoc!
echo.
echo   * LUU Y: GIU NGUYEN CUA SO NAY (Dong cua so nay se tat link)
echo ==============================================================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-tunnel.ps1"

echo.
echo ==============================================================================
echo   Tunnel da ket thuc hoac bi ngat ket noi. Nhan phim bat ky de thoat...
echo ==============================================================================
pause >nul

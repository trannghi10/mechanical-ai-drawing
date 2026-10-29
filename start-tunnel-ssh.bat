@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ===================================================
echo   Tao duong link HTTPS cong khai qua SSH Tunnel
echo   (Khong can tai bat ky phan mem nao)
echo ===================================================
echo.
echo Dang ket noi tao link cong khai...
echo Khi dong link xuat hien co dang: https://...lhrtunnel.pro hoac tuong tu
echo Hay copy link do de gui cho moi nguoi su dung!
echo.
echo Nhan Ctrl+C de dung tunnel bat cu luc nao.
echo ===================================================
echo.
ssh -o StrictHostKeyChecking=no -R 80:localhost:8765 nokey@localhost.run
pause

Set-Location -LiteralPath $PSScriptRoot

# Giai phong port 8765 neu co tien trinh cu dang chay
$connections = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
if ($connections) {
    foreach ($conn in $connections) {
        try { Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue } catch {}
    }
}

$env:CAD_ALLOW_REMOTE = "1"

Write-Host "===================================================" -ForegroundColor Green
Write-Host "  Mechanical AI Drawing dang mo tai:" -ForegroundColor Cyan
Write-Host "  http://127.0.0.1:8765/" -ForegroundColor Yellow
Write-Host "  (Nhan Ctrl+C de dung server)" -ForegroundColor Gray
Write-Host "===================================================`n" -ForegroundColor Green
$pythonCmd = "python"
$py311 = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
if (Test-Path $py311) { $pythonCmd = $py311 }

Start-Process "http://127.0.0.1:8765/"
& $pythonCmd -m uvicorn backend.main:app --host 0.0.0.0 --port 8765 --proxy-headers --forwarded-allow-ips=*


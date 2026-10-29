$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
# Provider/model are loaded from .env by backend.main.
& python -m backend.services.local_runtime_service
if ($LASTEXITCODE -ne 0) { Write-Warning 'AI chua san sang. Giao dien van cho phep kiem tra yeu cau bang CAD engine.' }
$env:CAD_ALLOW_REMOTE = "1"
Write-Host 'Mo http://127.0.0.1:8765/explorer. Dung Ctrl+C de dung server.'
& python -m uvicorn backend.main:app --host 0.0.0.0 --port 8765 --proxy-headers --forwarded-allow-ips=*

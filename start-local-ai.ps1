$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& python -m backend.services.local_runtime_service
if ($LASTEXITCODE -ne 0) { throw 'Khong khoi dong duoc AI. Xem thong bao phia tren.' }

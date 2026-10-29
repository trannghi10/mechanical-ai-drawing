# Cloudflare / Ngrok Tunnel - Mở đường link công khai cho CAD Studio
$ErrorActionPreference = "Continue"
Set-Location -LiteralPath $PSScriptRoot

# Neu da cau hinh link co dinh vinh vien trong storage\ngrok.env, chuyen sang chay link co dinh
$envFile = Join-Path $PSScriptRoot "storage\ngrok.env"
$authToken = ""
$staticDomain = ""
if (Test-Path $envFile) {
    $lines = Get-Content $envFile -ErrorAction SilentlyContinue
    foreach ($l in $lines) {
        if ($l -match "^\s*NGROK_AUTHTOKEN\s*=\s*(\S+)") { $authToken = $matches[1].Trim() }
        if ($l -match "^\s*NGROK_DOMAIN\s*=\s*(\S+)") { $staticDomain = $matches[1].Trim() }
    }
}
if ($authToken -and $staticDomain) {
    & "$PSScriptRoot\start-tunnel-ngrok.ps1"
    exit
}

$cloudflaredCmd = ""

# 1. Kiểm tra nếu cloudflared đã có trong biến môi trường PATH
if (Get-Command cloudflared -ErrorAction SilentlyContinue) {
    $cloudflaredCmd = "cloudflared"
}

# 2. Kiểm tra trực tiếp tại thư mục gốc dự án (cloudflared.exe hoặc cloudflared-windows-amd64.exe)
if (-not $cloudflaredCmd) {
    $rootFiles = @(
        (Join-Path $PSScriptRoot "cloudflared.exe"),
        (Join-Path $PSScriptRoot "cloudflared-windows-amd64.exe")
    )
    foreach ($rf in $rootFiles) {
        if ((Test-Path $rf) -and ((Get-Item $rf).Length -gt 10MB)) {
            $cloudflaredCmd = $rf
            break
        }
    }
}

# 3. Kiểm tra trong thư mục Downloads của người dùng
if (-not $cloudflaredCmd) {
    $downloadsDir = Join-Path $env:USERPROFILE "Downloads"
    if (Test-Path $downloadsDir) {
        $foundInDownloads = Get-ChildItem -Path $downloadsDir -Filter "cloudflared*.exe" -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Length -gt 10MB } |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1

        if ($foundInDownloads) {
            Write-Host "Tim thay file cloudflared tai: $($foundInDownloads.FullName)" -ForegroundColor Cyan
            $cloudflaredCmd = $foundInDownloads.FullName
        }
    }
}

# 4. Kiểm tra trong storage\tools\cloudflared.exe (phải > 10MB để tránh file hỏng)
$toolsDir = Join-Path $PSScriptRoot "storage\tools"
$toolsExe = Join-Path $toolsDir "cloudflared.exe"
if (-not $cloudflaredCmd) {
    if ((Test-Path $toolsExe) -and ((Get-Item $toolsExe).Length -gt 10MB)) {
        $cloudflaredCmd = $toolsExe
    }
}

# 5. Nếu chưa có, hướng dẫn hoặc thử tải
if (-not $cloudflaredCmd) {
    Write-Host "===================================================" -ForegroundColor Cyan
    Write-Host "  Dang tai cloudflared.exe tu Cloudflare ve may... " -ForegroundColor Yellow
    Write-Host "  (Chua day 35MB, chi can tai 1 lan duy nhat)      " -ForegroundColor Gray
    Write-Host "===================================================" -ForegroundColor Cyan
    $downloadUrl = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    
    try {
        if (-not (Test-Path $toolsDir)) { New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null }
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13
        $targetDl = Join-Path $PSScriptRoot "cloudflared.exe"
        Invoke-WebRequest -Uri $downloadUrl -OutFile $targetDl -UseBasicParsing
        if ((Test-Path $targetDl) -and ((Get-Item $targetDl).Length -gt 10MB)) {
            Write-Host " Da tai xong cloudflared.exe!" -ForegroundColor Green
            $cloudflaredCmd = $targetDl
        }
    } catch {
        # ignore download failure, show manual prompt below
    }
}

if (-not $cloudflaredCmd) {
    Write-Host ""
    Write-Host "[CHU Y] Chua tim thay file cloudflared.exe hop le (>20MB)!" -ForegroundColor Red
    Write-Host "Neu ban da tai ve may (vi du o thu muc Downloads):" -ForegroundColor Yellow
    Write-Host "  1. Copy file vua tai (cloudflared-windows-amd64.exe hoac cloudflared.exe)" -ForegroundColor White
    Write-Host "  2. Dan truc tiep vao thu muc du an: $PSScriptRoot" -ForegroundColor White
    Write-Host "  3. Doi ten thanh cloudflared.exe (neu ten dai)" -ForegroundColor White
    Write-Host "  4. Chay lai file start-tunnel.bat" -ForegroundColor Yellow
    Write-Host ""
    pause
    exit 1
}
# Lay dia chi IP mang noi bo
$localIP = ""
try {
    $localIP = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "Wi-Fi*","Ethernet*","vEthernet*" -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notmatch "^(127\.|169\.254\.)" } |
        Select-Object -ExpandProperty IPAddress -First 1)
} catch {}
if (-not $localIP) { $localIP = "192.168.1.142" }

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  DANG KHOI TAO DUONG LINK CONG KHAI CLOUDFLARE... " -ForegroundColor Yellow
Write-Host "  Dia chi mang noi bo (LAN) : http://$($localIP):8765/" -ForegroundColor Gray
Write-Host "  Vui long doi trong 3-5 giay de lay link...        " -ForegroundColor Gray
Write-Host "===================================================`n" -ForegroundColor Cyan

# Kiem tra va tu dong bat backend neu chua chay
$backendRunning = $false
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $iar = $tcp.BeginConnect("127.0.0.1", 8765, $null, $null)
    $success = $iar.AsyncWaitHandle.WaitOne(800)
    if ($success) { $backendRunning = $true }
    $tcp.Close()
} catch {}

if (-not $backendRunning) {
    Write-Host " [1/2] Dang tu dong khoi dong May chu CAD Studio (Backend)..." -ForegroundColor Yellow
    $pyCmd = "python"
    $localPy = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
    if (Test-Path $localPy) { $pyCmd = $localPy }

    $runBat = Join-Path $PSScriptRoot "run.bat"
    if (Test-Path $runBat) {
        Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$runBat`"" -WindowStyle Minimized
    } else {
        Start-Process -FilePath $pyCmd -ArgumentList "-m uvicorn backend.main:app --host 0.0.0.0 --port 8765 --proxy-headers --forwarded-allow-ips=*" -WindowStyle Minimized
    }
    Start-Sleep -Seconds 2
} else {
    Write-Host " [1/2] May chu CAD Studio da san sang tai cong 8765." -ForegroundColor Green
}
Write-Host " [2/2] Dang lay duong link truc tiep..." -ForegroundColor Yellow

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $cloudflaredCmd
$psi.Arguments = "tunnel --url http://127.0.0.1:8765 --protocol http2"
$psi.UseShellExecute = $false
$psi.RedirectStandardError = $true
$psi.RedirectStandardOutput = $false
$psi.CreateNoWindow = $false

$proc = [System.Diagnostics.Process]::Start($psi)

$urlFound = $false

# Cloudflare in toan bo thong tin tunnel vao StandardError
while (-not $proc.HasExited) {
    $line = $proc.StandardError.ReadLine()
    if ($null -eq $line) {
        Start-Sleep -Milliseconds 100
        continue
    }

    if (-not $urlFound -and $line -match "(https://[a-zA-Z0-9-]+\.trycloudflare\.com)" -and $matches[1] -notmatch "api\.trycloudflare\.com") {
        $urlFound = $true
        $tunnelUrl = $matches[1]

        Clear-Host
        Write-Host ""
        Write-Host "==========================================================================" -ForegroundColor Green
        Write-Host "             DUONG LINK TRUY CAP CAD STUDIO DA SAN SANG!                  " -ForegroundColor Yellow
        Write-Host "==========================================================================" -ForegroundColor Green
        Write-Host ""
        Write-Host " [1] LINK TRUY CAP QUA INTERNET (GUI CHO NGUOI O XA):" -ForegroundColor White
        Write-Host "     ->  $tunnelUrl" -ForegroundColor Cyan
        Write-Host "     * DA TU DONG COPY VAO CLIPBOARD! (Chi can Ctrl + V vao Zalo/Chat)" -ForegroundColor Green
        Write-Host ""
        Write-Host " [2] LINK TRUY CAP TRONG CUNG WIFI / NOI BO (CO DINH VA NHANH NHAT):" -ForegroundColor White
        Write-Host "     ->  http://$($localIP):8765/" -ForegroundColor Yellow
        Write-Host "     * May tinh hoac dien thoai cung bat Wifi nay deu truy cap duoc." -ForegroundColor Gray
        Write-Host ""
        Write-Host "--------------------------------------------------------------------------" -ForegroundColor DarkGray
        Write-Host " * TRANG THAI : DANG HOAT DONG ON DINH (San sang cho nguoi khac truy cap)" -ForegroundColor Green
        Write-Host " * LUU Y     : GIU NGUYEN CUA SO NAY. Khi nao muon tat link thi dong cua so." -ForegroundColor DarkYellow
        Write-Host "==========================================================================" -ForegroundColor Green
        Write-Host ""

        try { Set-Clipboard -Value $tunnelUrl } catch {}
        try {
            $txtPath = Join-Path $PSScriptRoot "DUONG-LINK-HIEN-TAI.txt"
            $linkInfo = @"
==========================================================================
             DUONG LINK TRUY CAP CAD STUDIO DANG HOAT DONG
==========================================================================

[1] LINK INTERNET (GUI CHO NGUOI O XA):
$tunnelUrl

[2] LINK CUNG MANG WIFI (CO DINH, SIEU NHANH):
http://$($localIP):8765/

* Link nay da duoc copy san vao may tinh cua ban.
* Chi can bam Ctrl + V de gui qua Zalo hoac dan vao trinh duyet.
* Giu nguyen cua so start-tunnel dang chay de duy tri ket noi.
==========================================================================
"@
            [System.IO.File]::WriteAllText($txtPath, $linkInfo, [System.Text.Encoding]::UTF8)
        } catch {}
        try { Start-Process $tunnelUrl } catch {}
    } else {
        if (-not $urlFound) {
            # Hien thi tien trinh khoi tao ngan gon
            if ($line -match "INF Registered tunnel connection") {
                Write-Host " [KET NOI ON DINH] $line" -ForegroundColor Green
            } elseif ($line -match "ERR") {
                Write-Host " $line" -ForegroundColor DarkYellow
            }
        }
    }
}

$proc.WaitForExit()


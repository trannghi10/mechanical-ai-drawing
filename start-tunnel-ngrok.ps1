# Ngrok Free Static Domain - Duong link co dinh vinh vien cho CAD Studio
$ErrorActionPreference = "Continue"
Set-Location -LiteralPath $PSScriptRoot

$envFile = Join-Path $PSScriptRoot "storage\ngrok.env"
$toolsDir = Join-Path $PSScriptRoot "storage\tools"
$ngrokExe = Join-Path $toolsDir "ngrok.exe"

if (-not (Test-Path $toolsDir)) {
    New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null
}

# 1. Kiem tra ngrok trong PATH hoac thu muc tools
$ngrokCmd = ""
if (Get-Command ngrok -ErrorAction SilentlyContinue) {
    $ngrokCmd = "ngrok"
} elseif (Test-Path $ngrokExe) {
    $ngrokCmd = $ngrokExe
} elseif (Test-Path (Join-Path $PSScriptRoot "ngrok.exe")) {
    $ngrokCmd = Join-Path $PSScriptRoot "ngrok.exe"
}

# 2. Neu chua co ngrok, huong dan hoac tu dong tai
if (-not $ngrokCmd) {
    Write-Host "==========================================================================" -ForegroundColor Cyan
    Write-Host "     DANG TAI NGROK (CONG CU TAO LINK CO DINH MIEN PHI TRON DOI)...       " -ForegroundColor Yellow
    Write-Host "==========================================================================" -ForegroundColor Cyan
    
    $dlUrl = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip"
    $zipPath = Join-Path $toolsDir "ngrok.zip"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13
        Write-Host " Dang tai ngrok tu trang chu ve may..." -ForegroundColor Gray
        Invoke-WebRequest -Uri $dlUrl -OutFile $zipPath -UseBasicParsing
        if (Test-Path $zipPath) {
            Expand-Archive -Path $zipPath -DestinationPath $toolsDir -Force
            Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
            if (Test-Path $ngrokExe) {
                Write-Host " Da tai va giai nen ngrok.exe thanh cong!" -ForegroundColor Green
                $ngrokCmd = $ngrokExe
            }
        }
    } catch {
        Write-Host " [CHU Y] Khong the tu dong tai ngrok: $_" -ForegroundColor DarkYellow
    }
}

if (-not $ngrokCmd) {
    Write-Host ""
    Write-Host "[HUONG DAN TAI NGROK THU CONG - CHI MAT 30 GIAY]:" -ForegroundColor Yellow
    Write-Host "  1. Truy cap: https://ngrok.com/download" -ForegroundColor White
    Write-Host "  2. Tai file ngrok cho Windows ve may va giai nen file ngrok.exe" -ForegroundColor White
    Write-Host "  3. Copy file ngrok.exe dat vao thu muc: $PSScriptRoot" -ForegroundColor White
    Write-Host "  4. Chay lai file start-tunnel-ngrok.bat" -ForegroundColor Yellow
    Write-Host ""
    pause
    exit 1
}

# 3. Kiem tra file cau hinh ngrok.env (luu Authtoken va Domain co dinh)
$authToken = ""
$staticDomain = ""

if (Test-Path $envFile) {
    $lines = Get-Content $envFile -ErrorAction SilentlyContinue
    foreach ($l in $lines) {
        if ($l -match "^\s*NGROK_AUTHTOKEN\s*=\s*(.*)$") { $authToken = $matches[1].Trim() }
        if ($l -match "^\s*NGROK_DOMAIN\s*=\s*(.*)$") { $staticDomain = $matches[1].Trim() }
    }
}

# Neu chua co authtoken hoac domain, hoi nguoi dung
if (-not $authToken -or -not $staticDomain) {
    Clear-Host
    Write-Host "==========================================================================" -ForegroundColor Green
    Write-Host "       THIET LAP DUONG LINK CO DINH MIEN PHI TRON DOI (NGROK)             " -ForegroundColor Yellow
    Write-Host "==========================================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host " De co 1 duong link co dinh mai mai (vi du: https://cad-studio-nghi.ngrok-free.app)" -ForegroundColor White
    Write-Host " khong bao gio bi doi ten khi tat bat may, ban chi can 1 tai khoan mien phi:" -ForegroundColor White
    Write-Host ""
    Write-Host "   Buoc 1: Mo trinh duyet vao https://dashboard.ngrok.com (Dang nhap bang Google)" -ForegroundColor Cyan
    Write-Host "   Buoc 2: Vao menu 'Your Authtoken' -> Copy ma Token" -ForegroundColor Cyan
    Write-Host "   Buoc 3: Vao menu 'Cloud Edge' -> 'Domains' -> Nhan 'Create Domain' de lay ten mien mien phi" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "--------------------------------------------------------------------------" -ForegroundColor DarkGray
    
    if (-not $authToken) {
        $authToken = Read-Host " -> Dan ma Authtoken cua ban vao day roi Enter"
        $authToken = $authToken.Trim()
    }
    
    if (-not $staticDomain) {
        $staticDomain = Read-Host " -> Nhap ten mien co dinh (vi du: cad-studio-nghi.ngrok-free.app)"
        $staticDomain = $staticDomain.Trim()
        if ($staticDomain -notmatch "\.ngrok-free\.app$" -and $staticDomain -notmatch "\.ngrok\.app$") {
            if ($staticDomain -notmatch "\.") {
                $staticDomain = "$staticDomain.ngrok-free.app"
            }
        }
    }
    
    # Luu vao storage\ngrok.env de lan sau khong can hoi lai
    $content = "NGROK_AUTHTOKEN=$authToken`nNGROK_DOMAIN=$staticDomain`n"
    [System.IO.File]::WriteAllText($envFile, $content, [System.Text.Encoding]::UTF8)
    Write-Host ""
    Write-Host " [OK] Da luu cau hinh vao $envFile! Tu lan sau ban chi can bam dup chuot la chay ngay." -ForegroundColor Green
    Start-Sleep -Seconds 1
}

# 4. Kiem tra va tu dong bat backend neu chua chay
$backendRunning = $false
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $iar = $tcp.BeginConnect("127.0.0.1", 8765, $null, $null)
    $success = $iar.AsyncWaitHandle.WaitOne(800)
    if ($success) { $backendRunning = $true }
    $tcp.Close()
} catch {}

if (-not $backendRunning) {
    Write-Host " Dang tu dong khoi dong May chu CAD Studio (Backend)..." -ForegroundColor Yellow
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
}

# Cau hinh authtoken cho ngrok
& $ngrokCmd config add-authtoken $authToken 2>$null

# 5. Khoi dong tunnel voi domain co dinh
Clear-Host
$fullUrl = "https://$staticDomain"

Write-Host "==========================================================================" -ForegroundColor Green
Write-Host "             DUONG LINK CO DINH CAD STUDIO DA SAN SANG!                   " -ForegroundColor Yellow
Write-Host "==========================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  LINK CO DINH TRUY CAP QUA INTERNET (VINH VIEN KHONG DOI):" -ForegroundColor White
Write-Host "  ->  $fullUrl" -ForegroundColor Cyan
Write-Host ""
Write-Host "  * DA TU DONG COPY VAO CLIPBOARD! (Chi can Ctrl + V vao Zalo/Chat de gui)" -ForegroundColor Green
Write-Host "  * Dang mo trinh duyet..." -ForegroundColor Yellow
Write-Host "  * GIU NGUYEN CUA SO NAY de duy tri ket noi (Dong cua so se tat link)" -ForegroundColor Gray
Write-Host "==========================================================================" -ForegroundColor Green
Write-Host ""

try { Set-Clipboard -Value $fullUrl } catch {}
try {
    $txtPath = Join-Path $PSScriptRoot "DUONG-LINK-HIEN-TAI.txt"
    $linkInfo = @"
==========================================================================
             DUONG LINK CO DINH CAD STUDIO (TRON DOI)
==========================================================================

LINK CO DINH TRUY CAP QUA INTERNET (TRONG & NGOAI CONG TY):
$fullUrl

* Day la DUONG LINK CO DINH VINH VIEN, khong bao gio bi doi ten!
* Link da duoc tu dong copy san vao may cua ban.
* Chi can bam Ctrl + V de gui qua Zalo hoac dan vao trinh duyet.
==========================================================================
"@
    [System.IO.File]::WriteAllText($txtPath, $linkInfo, [System.Text.Encoding]::UTF8)
} catch {}
try { Start-Process $fullUrl } catch {}

# Chay ngrok process
& $ngrokCmd http --domain=$staticDomain 8765

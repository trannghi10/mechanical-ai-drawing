$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path "$PSScriptRoot\..").Path
$taskReport = Join-Path $taskRoot 'storage/postgres-service-recovery.json'
function Write-RecoveryStatus($status, $detail) {
    @{status=$status;detail=$detail;time=[DateTimeOffset]::Now.ToString('o');service='postgresql-x64-18'} |
        ConvertTo-Json | Set-Content -LiteralPath $taskReport -Encoding utf8
}
try {
    $taskIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $taskPrincipal = [Security.Principal.WindowsPrincipal]::new($taskIdentity)
    if (!$taskPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run this script as Administrator; no database files will be changed by this script.'
    }
    $taskService = Get-CimInstance Win32_Service -Filter "Name='postgresql-x64-18'"
    if (!$taskService -or $taskService.PathName -notlike '*PostgreSQL\18\bin\pg_ctl.exe*' -or $taskService.PathName -notlike '*PostgreSQL\18\data*') {
        throw 'Unexpected PostgreSQL service identity; no action taken.'
    }
    Write-RecoveryStatus 'restarting' 'Controlled service restart; no WAL reset, restore or database initialization.'
    $taskController = Get-Service -Name 'postgresql-x64-18'
    if ($taskController.Status -ne 'Stopped') {
        Write-RecoveryStatus 'fast_shutdown_requested' 'Requesting documented pg_ctl fast shutdown; no process kill and no WAL changes.'
        & 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' stop -D 'C:\Program Files\PostgreSQL\18\data' -m fast -w -t 30
        if ($LASTEXITCODE -ne 0) { throw 'Controlled fast shutdown did not complete; no forced termination attempted.' }
        $taskController.WaitForStatus([System.ServiceProcess.ServiceControllerStatus]::Stopped,[TimeSpan]::FromSeconds(45))
    }
    $taskController.Start()
    $taskController.WaitForStatus([System.ServiceProcess.ServiceControllerStatus]::Running,[TimeSpan]::FromSeconds(45))
    for ($taskAttempt=0; $taskAttempt -lt 20; $taskAttempt++) {
        & 'C:\Program Files\PostgreSQL\18\bin\pg_isready.exe' -h 127.0.0.1 -p 5432 -t 2 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-RecoveryStatus 'accepting_connections' 'Service restarted; application must verify pg_is_in_recovery() and metadata integrity.'
            exit 0
        }
        Start-Sleep -Seconds 2
    }
    throw 'PostgreSQL is still rejecting connections after service restart; inspect server logs before further action.'
} catch {
    Write-RecoveryStatus 'failed' $_.Exception.Message
    throw
}

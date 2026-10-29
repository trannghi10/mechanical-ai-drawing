param([ValidateSet('fast','immediate')][string]$ShutdownMode='fast')
$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path "$PSScriptRoot\..").Path
$taskReport=Join-Path $taskRoot 'storage/postgres-service-recovery.json'
try {
    $taskService=Get-CimInstance Win32_Service -Filter "Name='postgresql-x64-18'"
    if($taskService.PathName -notlike '*PostgreSQL\18\data*'){throw 'Unexpected service identity'}
    $taskLog=Join-Path $taskRoot 'storage/postgres-fast-shutdown.log'
    & 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' stop -D 'C:\Program Files\PostgreSQL\18\data' -m $ShutdownMode -w -t 30 *> $taskLog
    if($LASTEXITCODE -ne 0){throw 'pg_ctl fast shutdown failed; see local log; no process kill attempted'}
    Start-Service 'postgresql-x64-18'
    for($taskIndex=0;$taskIndex -lt 20;$taskIndex++){
        & 'C:\Program Files\PostgreSQL\18\bin\pg_isready.exe' -h 127.0.0.1 -p 5432 -t 2 | Out-Null
        if($LASTEXITCODE -eq 0){@{status='accepting_connections';shutdown_mode=$ShutdownMode;detail='Controlled pg_ctl shutdown then service start';time=[DateTimeOffset]::Now.ToString('o')}|ConvertTo-Json|Set-Content $taskReport;exit 0}
        Start-Sleep -Seconds 2
    }
    throw 'Service started but not accepting connections'
} catch {@{status='failed';detail=$_.Exception.Message;time=[DateTimeOffset]::Now.ToString('o')}|ConvertTo-Json|Set-Content $taskReport;throw}

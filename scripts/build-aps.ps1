param([Parameter(Mandatory=$true)][string]$AutoCADManagedDir, [string]$DotnetPath='dotnet', [string]$PackagePath='')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:DOTNET_CLI_HOME = Join-Path $projectRoot 'storage/tools/dotnet-home'
$env:NUGET_PACKAGES = Join-Path $projectRoot 'storage/tools/nuget-packages'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = '1'
$sdkDirectory = (Resolve-Path -LiteralPath $AutoCADManagedDir).Path
foreach ($name in @('AcDbMgd.dll','AcCoreMgd.dll')) {
    if (-not (Test-Path -LiteralPath (Join-Path $sdkDirectory $name))) { throw "Missing official SDK: $name" }
}
if (-not (& $DotnetPath --list-sdks)) { throw 'Install .NET SDK 8 first; the .NET runtime alone cannot build this plugin.' }
$project = Join-Path $projectRoot 'autodesk/MechanicalCad/MechanicalCad.csproj'
$nugetConfig = Join-Path $projectRoot 'autodesk/MechanicalCad/NuGet.Config'
& $DotnetPath build $project -c Release "-p:AutoCADManagedDir=$sdkDirectory" "-p:RestoreConfigFile=$nugetConfig" -p:NuGetAudit=false --ignore-failed-sources
if ($LASTEXITCODE -ne 0) { throw 'AutoCAD plugin build failed.' }
$package = if ($PackagePath) { [System.IO.Path]::GetFullPath($PackagePath) } else { Join-Path $projectRoot 'autodesk/MechanicalCad.zip' }
$dll = Join-Path $projectRoot 'autodesk/MechanicalCad/bin/Release/net8.0-windows/MechanicalCad.dll'
$manifest = Join-Path $projectRoot 'autodesk/MechanicalCad/PackageContents.xml'
# Write fixed package entries directly: no recursive delete or move is needed.
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$stream = [System.IO.File]::Open($package,[System.IO.FileMode]::Create)
try {
    $zip = [System.IO.Compression.ZipArchive]::new($stream,[System.IO.Compression.ZipArchiveMode]::Create)
    try {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip,$dll,'MechanicalCad.bundle/Contents/MechanicalCad.dll') | Out-Null
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip,$manifest,'MechanicalCad.bundle/PackageContents.xml') | Out-Null
    } finally { $zip.Dispose() }
} finally { $stream.Dispose() }
Write-Host "Built $package. Next: python scripts/setup_aps.py register"

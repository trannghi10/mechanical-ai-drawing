param(
    [string]$SdkRoot = "$PSScriptRoot\..\storage\tools\objectarx2027\CDROM1",
    [string]$BuildToolsRoot = "$PSScriptRoot\..\storage\tools\vsbuild2026"
)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path "$PSScriptRoot\..").Path
$taskSdk = (Resolve-Path $SdkRoot).Path
$taskCompiler = Get-ChildItem "$BuildToolsRoot\VC\Tools\MSVC\14.44*\bin\Hostx64\x64\cl.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if (!$taskCompiler) { throw 'MSVC 14.44 x64 is not installed; native adapter has not been built.' }
$taskVcVars = "$BuildToolsRoot\VC\Auxiliary\Build\vcvarsall.bat"
if (!(Test-Path -LiteralPath "$taskSdk\inc\dbdimassoc.h")) { throw 'ObjectARX SDK headers missing.' }
$taskOutput = "$taskRoot\autodesk\NativePointReference\build"
New-Item -ItemType Directory -Path $taskOutput -Force | Out-Null
# A generated batch file keeps paths quoted and avoids changing the caller shell.
$taskBatch = @"
@echo off
call "$taskVcVars" x64 -vcvars_ver=14.44
if errorlevel 1 exit /b %errorlevel%
cl.exe /nologo /LD /MD /EHsc /std:c++17 /DUNICODE /D_UNICODE /DWIN32 /D_WINDOWS /I"$taskSdk\inc" "$taskRoot\autodesk\NativePointReference\NativePointReference.cpp" /Fo"$taskOutput\NativePointReference.obj" /link /LIBPATH:"$taskSdk\lib-x64" acdb26.lib acge26.lib rxapi.lib /OUT:"$taskOutput\MechanicalPointReference.dll"
exit /b %errorlevel%
"@
Set-Content -LiteralPath "$taskOutput\build.cmd" -Value $taskBatch -Encoding ascii
& $env:ComSpec /d /c "`"$taskOutput\build.cmd`""
if ($LASTEXITCODE -ne 0) { throw "Native build failed: $LASTEXITCODE" }
Get-FileHash -LiteralPath "$taskOutput\MechanicalPointReference.dll" -Algorithm SHA256

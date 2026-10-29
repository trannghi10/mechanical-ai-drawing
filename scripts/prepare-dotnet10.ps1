# Portable Microsoft SDK for AutoCAD 2027; no system installation or CAD uploads.
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$projectRoot=Split-Path -Parent $PSScriptRoot
$tools=[System.IO.Path]::GetFullPath((Join-Path $projectRoot 'storage/tools'))
if (-not $tools.StartsWith([System.IO.Path]::GetFullPath((Join-Path $projectRoot 'storage'))+[System.IO.Path]::DirectorySeparatorChar,[System.StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected SDK tools directory' }
New-Item -ItemType Directory -Path $tools -Force | Out-Null
$sdkUrl='https://builds.dotnet.microsoft.com/dotnet/Sdk/10.0.402/dotnet-sdk-10.0.402-win-x64.zip'
$expected='ae4fd528cb7e9f6af6aaf7de36715a69f761f183744f1bb3025d19f5a92447090ec561410e46266c1d10a63781ed6f3de771760bc76c876d87daabc367b898cd'
$archive=Join-Path $tools 'dotnet-sdk-10.0.402-win-x64.zip'
$valid=(Test-Path -LiteralPath $archive) -and ((Get-FileHash -LiteralPath $archive -Algorithm SHA512).Hash -eq $expected)
if (-not $valid) {
    $client=[System.Net.Http.HttpClient]::new()
    $request=[System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Get,$sdkUrl)
    $request.Headers.Range=[System.Net.Http.Headers.RangeHeaderValue]::new(0,0)
    try {
        $response=$client.SendAsync($request,[System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
        if ([int]$response.StatusCode -ne 206) { throw 'Microsoft endpoint did not honor the range request' }
        $size=$response.Content.Headers.ContentRange.Length
    } finally { if ($response) {$response.Dispose()};$request.Dispose();$client.Dispose() }
    $prefix=if (Test-Path -LiteralPath $archive) {(Get-Item -LiteralPath $archive).Length} else {0}
    if ($prefix -ge $size) {$prefix=0}
    $parts=Join-Path $tools 'dotnet10-parts';New-Item -ItemType Directory -Path $parts -Force | Out-Null
    $chunkSize=[long][Math]::Ceiling(($size-$prefix)/16)
    $ranges=for ($index=0;$index -lt 16;$index++) {
        $start=$prefix+$index*$chunkSize
        if ($start -lt $size) {[pscustomobject]@{index=$index;start=$start;end=[Math]::Min($size-1,$start+$chunkSize-1)}}
    }
    $ranges | ForEach-Object -Parallel {
        $ErrorActionPreference='Stop'
        $range=$_;$destination=Join-Path $using:parts ('{0:D3}.part' -f $range.index)
        $length=$range.end-$range.start+1
        if ((Test-Path -LiteralPath $destination) -and (Get-Item -LiteralPath $destination).Length -eq $length) { return }
        $http=[System.Net.Http.HttpClient]::new();$cancel=[System.Threading.CancellationTokenSource]::new(900000)
        $message=[System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Get,$using:sdkUrl)
        $message.Headers.Range=[System.Net.Http.Headers.RangeHeaderValue]::new($range.start,$range.end)
        try {
            $reply=$http.SendAsync($message,[System.Net.Http.HttpCompletionOption]::ResponseHeadersRead,$cancel.Token).GetAwaiter().GetResult()
            if ([int]$reply.StatusCode -ne 206 -or $reply.Content.Headers.ContentRange.From -ne $range.start -or $reply.Content.Headers.ContentRange.To -ne $range.end) { throw 'Invalid SDK range response' }
            $inputStream=$reply.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
            $outputStream=[System.IO.File]::Open($destination,[System.IO.FileMode]::Create)
            try {[void]$inputStream.CopyToAsync($outputStream,1048576,$cancel.Token).GetAwaiter().GetResult()} finally {$outputStream.Dispose();$inputStream.Dispose()}
            if ((Get-Item -LiteralPath $destination).Length -ne $length) {throw 'Incomplete SDK range'}
        } finally {if ($reply) {$reply.Dispose()};$message.Dispose();$http.Dispose();$cancel.Dispose()}
    } -ThrottleLimit 16
    $joined=$archive+'.verified-part'
    $output=[System.IO.File]::Open($joined,[System.IO.FileMode]::Create)
    try {
        if ($prefix -gt 0) {$sdkInputStream=[System.IO.File]::OpenRead($archive);try {$sdkInputStream.CopyTo($output)} finally {$sdkInputStream.Dispose()}}
        foreach ($range in $ranges) {
            $file=Join-Path $parts ('{0:D3}.part' -f $range.index)
            if ((Get-Item -LiteralPath $file).Length -ne $range.end-$range.start+1) {throw 'Missing SDK part'}
            $sdkInputStream=[System.IO.File]::OpenRead($file);try {$sdkInputStream.CopyTo($output)} finally {$sdkInputStream.Dispose()}
        }
    } finally {$output.Dispose()}
    if ((Get-Item -LiteralPath $joined).Length -ne $size -or (Get-FileHash -LiteralPath $joined -Algorithm SHA512).Hash -ne $expected) {throw 'Microsoft SDK SHA-512 mismatch; archive will not be used'}
    Move-Item -LiteralPath $joined -Destination $archive -Force
    foreach ($range in $ranges) {Remove-Item -LiteralPath (Join-Path $parts ('{0:D3}.part' -f $range.index))}
    # Non-recursive removal succeeds only if our part directory is empty.
    if (-not (Get-ChildItem -LiteralPath $parts -Force)) {Remove-Item -LiteralPath $parts}
}
$destination=Join-Path $tools 'dotnet10'
if (-not (Test-Path -LiteralPath (Join-Path $destination 'dotnet.exe'))) {Expand-Archive -LiteralPath $archive -DestinationPath $destination}
& (Join-Path $destination 'dotnet.exe') --list-sdks

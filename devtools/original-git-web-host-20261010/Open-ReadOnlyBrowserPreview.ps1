# Isolated original Git renderer only. No Qt/Conversation/Core/production launch.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$repoRoot = (Resolve-Path (Join-Path $taskRoot '..\..')).Path
$frontendRoot = Join-Path $taskRoot 'frontend'
$nodeExe = (Get-Command node -ErrorAction Stop).Source
$viteEntry = Join-Path $repoRoot 'pet-electron\node_modules\vite\bin\vite.js'
$edgeExe = Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'
foreach ($required in @($viteEntry, $edgeExe, (Join-Path $frontendRoot 'dist\work-panel.html'))) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing preview dependency: $required" }
}
# Verify the six originals without checking out or modifying any Git paths.
Push-Location $repoRoot
try {
    foreach ($relative in @('src/work-panel/main.ts', 'src/work-panel/styles.css', 'src/work-panel/model.ts', 'src/work-panel/types.ts', 'src/work-panel/schedule.ts', 'work-panel.html')) {
        $expected = & git rev-parse ('995c23c7c8d1be62000229d58610d2214f3bb745:pet-electron/renderer/' + $relative)
        if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve original Git blob' }
        $actual = & git hash-object --no-filters (Join-Path $frontendRoot $relative)
        if ($LASTEXITCODE -ne 0 -or $actual -ne $expected) { throw "Original source changed: $relative" }
    }
} finally { Pop-Location }

$outputRoot = Join-Path $taskRoot ('.runtime\browser-review-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
New-Item -ItemType Directory -Path $outputRoot -ErrorAction Stop | Out-Null
# Select a disposable loopback port; Vite strictPort fails closed on a race.
$reservation = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
$reservation.Start()
$previewPort = $reservation.LocalEndpoint.Port
$reservation.Stop()
$previewUrl = "http://127.0.0.1:$previewPort/work-panel.html"
$server = $null
try {
    Push-Location $frontendRoot
    try {
        & $nodeExe '../../../pet-electron/node_modules/typescript/bin/tsc' --project tsconfig.json --noEmit
        if ($LASTEXITCODE -ne 0) { throw 'Preview TypeScript check failed' }
        & $nodeExe $viteEntry build --config vite.config.mjs
        if ($LASTEXITCODE -ne 0) { throw 'Preview build failed' }
    } finally { Pop-Location }
    $server = Start-Process -FilePath $nodeExe -ArgumentList @(('"' + $viteEntry + '"'), 'preview', '--config', 'vite.config.mjs', '--host', '127.0.0.1', '--port', "$previewPort", '--strictPort') -WorkingDirectory $frontendRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $outputRoot 'server.stdout.log') -RedirectStandardError (Join-Path $outputRoot 'server.stderr.log') -PassThru
    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        $server.Refresh()
        if ($server.HasExited) { throw "Preview server exited: $($server.ExitCode); see $outputRoot" }
        try {
            $response = Invoke-WebRequest -UseBasicParsing ($previewUrl + '?view=chat') -TimeoutSec 1
            if ($response.StatusCode -eq 200 -and $response.Content.Contains('Content-Security-Policy')) { $ready = $true; break }
        } catch { Start-Sleep -Milliseconds 250 }
    }
    if (-not $ready) { throw "Preview HTTP readiness failed: $previewUrl" }
    # Fresh disposable browser profile; no sandbox/GPU overrides or user settings.
    $profilePath = Join-Path $outputRoot 'edge-profile'
    $browser = Start-Process -FilePath $edgeExe -ArgumentList @(('--user-data-dir="' + $profilePath + '"'), '--no-first-run', '--no-default-browser-check', '--new-window', ($previewUrl + '?view=chat'), ($previewUrl + '?view=settings'), ($previewUrl + '?view=today')) -PassThru
    $receipt = [ordered]@{ kind = 'SYNTHETIC read-only browser preview'; qtAcceptance = 'UNVERIFIED'; url = $previewUrl; serverPid = $server.Id; browserLaunchPid = $browser.Id; visibleWindow = 'UNVERIFIED'; evidence = $outputRoot }
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        $browser.Refresh()
        if ($browser.HasExited) { break }
        if ($browser.MainWindowHandle -ne 0) { $receipt.visibleWindow = 'HANDLE_OBSERVED'; break }
        Start-Sleep -Milliseconds 250
    }
    $receipt | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $outputRoot 'PreviewLaunch.json')
    $receipt | ConvertTo-Json | Write-Host
    Write-Host 'SYNTHETIC ONLY. Inspect Chat / Settings / Today; open History from Chat.'
    Write-Host 'No Qt gate is passed by this preview. Close the isolated Edge window when done.'
    if ($receipt.visibleWindow -eq 'UNVERIFIED') { Write-Warning 'No visible window handle observed; inspect browser and logs. Do not treat launch PID as visual proof.' }
    Read-Host 'Press Enter to stop this task-owned preview server' | Out-Null
} finally {
    if ($null -ne $server) {
        $server.Refresh()
        if (-not $server.HasExited) { $server.Kill(); $server.WaitForExit() }
    }
}

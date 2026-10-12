# Run in a normal interactive Windows user's PowerShell. Synthetic preview only.
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
if ($env:QTWEBENGINE_DISABLE_SANDBOX -or $env:QTWEBENGINE_CHROMIUM_FLAGS -or $env:QT_QPA_PLATFORM) {
    throw 'Use a normal desktop shell without WebEngine or platform overrides.'
}
$relayStamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
$relayOutput = Join-Path $taskRoot ".runtime\w1-windows-relay-$relayStamp"
New-Item -ItemType Directory -Path $relayOutput | Out-Null
Push-Location $taskRoot
$summaryInputs = @((Join-Path $relayOutput 'smoke\SmokeResult.json'))
try {
    & $taskPython -B w1_preflight.py (Join-Path $relayOutput 'RelayBefore.json')
    if ($LASTEXITCODE -ne 0) { throw 'W1 relay source preflight failed' }
    & $taskPython -B w1_smoke.py --output (Join-Path $relayOutput 'smoke')
    $smokeExit = $LASTEXITCODE
    if ($smokeExit -ne 0) { throw "W1 smoke blocked/failed: exit $smokeExit; retain $relayOutput" }
    $relayResults = @()
    foreach ($dpiScale in @(1, 1.25, 2)) {
        # Four views including History, two viewports. No gate inference.
        $scaleText = $dpiScale.ToString([Globalization.CultureInfo]::InvariantCulture)
        $parityOutput = Join-Path $relayOutput "parity-$scaleText"
        $summaryInputs += (Join-Path $parityOutput 'ParityResult.json')
        & $taskPython -B capture_parity.py --channel msedge --scale $scaleText --output $parityOutput --collect-geometry-drift --smoke-result (Join-Path $relayOutput 'smoke\SmokeResult.json')
        $relayResults += [pscustomobject]@{ scale = $dpiScale; exit = $LASTEXITCODE; receipt = (Join-Path $parityOutput 'ParityResult.json') }
        $relayResults | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $relayOutput 'MatrixExits.json')
    }
    $relayResults | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $relayOutput 'MatrixExits.json')
    Write-Output "Receipts: $relayOutput; parity evidence paths are printed by capture_parity.py. No Gate PASS is inferred."
} finally {
    # Python handles Unicode and keys differing only in case; no ConvertFrom-Json.
    & $taskPython -B summarize_w1.py @summaryInputs --output (Join-Path $relayOutput 'ReadableSummary.json')
    $summaryExit = $LASTEXITCODE
    $integrityExit = 1
    if (Test-Path -LiteralPath (Join-Path $relayOutput 'RelayBefore.json')) {
        & $taskPython -B w1_preflight.py (Join-Path $relayOutput 'RelayAfter.json') --compare (Join-Path $relayOutput 'RelayBefore.json')
        $integrityExit = $LASTEXITCODE
    }
    Pop-Location
}
if ($integrityExit -ne 0) { throw "W1 relay integrity FAIL; preserve $relayOutput" }
if ($summaryExit -ne 0) { throw "W1 FAIL/BLOCKED; inspect $relayOutput\ReadableSummary.json (summary exit $summaryExit)" }

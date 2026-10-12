param(
    [ValidateSet('W3','W5')][string]$Checkpoint = 'W5',
    [ValidateRange(15,1200)][int]$Seconds = 900
)
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
foreach ($key in @('QTWEBENGINE_DISABLE_SANDBOX','QTWEBENGINE_CHROMIUM_FLAGS','QT_QPA_PLATFORM','QTWEBENGINE_REMOTE_DEBUGGING')) {
    if ([Environment]::GetEnvironmentVariable($key)) { throw "Normal desktop environment required; override present: $key" }
}
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
$output = Join-Path $taskRoot ".runtime\native-candidate-$Checkpoint-$stamp"
Push-Location (Join-Path $taskRoot 'frontend')
try {
    & node '../../../pet-electron/node_modules/typescript/bin/tsc' --project tsconfig.json --noEmit
    if ($LASTEXITCODE -ne 0) { throw 'Candidate typecheck failed' }
    & node '../../../pet-electron/node_modules/vite/bin/vite.js' build --config vite.owner.config.mjs
    if ($LASTEXITCODE -ne 0) { throw 'Candidate build failed' }
} finally { Pop-Location }
Write-Output 'SYNTHETIC only: use no private text or files. Close this candidate window to stop its own sidecar. No tray or formal launcher is used.'
& $taskPython -I -B (Join-Path $taskRoot 'candidate_native.py') --output $output --checkpoint $Checkpoint --seconds $Seconds
$nativeExit = $LASTEXITCODE
Write-Output "Native receipt: $output\NativeResult.json; exit=$nativeExit. Bootstrap is not W1 visual/IME/security/human acceptance."
if ($nativeExit -ne 0) { throw "Native candidate BLOCKED/FAIL; retain $output" }

<# One-shot normal-user package relay. Never starts/stops Kuro or activates Web UI. #>
[CmdletBinding()]
param(
    [string]$Wheel,
    [string]$RollbackRun,
    [switch]$AuditOnly
)
$ErrorActionPreference = 'Stop'
$w6Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$w6Formal = Join-Path $w6Root 'envs/kuro-llm310'
$w6Python = Join-Path $w6Formal 'python.exe'
$w6Helper = Join-Path $PSScriptRoot 'w6_package_gate.py'
$w6Utf8 = New-Object System.Text.UTF8Encoding($false)

function Write-W6Json([string]$Path, $Value) {
    if (Test-Path -LiteralPath $Path) { throw "Receipt already exists: $Path" }
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 8), $w6Utf8)
}

function Assert-W6Idle([string]$Output) {
    if (-not ('W6RelayParent' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class W6RelayParent {
 [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
 [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
 [DllImport("ntdll.dll")] static extern int NtQueryInformationProcess(IntPtr h, int kind, IntPtr data, int size, out int returned);
 [StructLayout(LayoutKind.Sequential)] struct Basic {public IntPtr reserved, peb, r1, r2, pid, parent;}
 public static string Read(int pid) {
  var h=OpenProcess(0x1000,false,pid);
  if(h==IntPtr.Zero) return "UNAVAILABLE:"+Marshal.GetLastWin32Error();
  var b=Marshal.AllocHGlobal(Marshal.SizeOf(typeof(Basic)));
  try {int n; int s=NtQueryInformationProcess(h,0,b,Marshal.SizeOf(typeof(Basic)),out n);
   return s==0 ? ((Basic)Marshal.PtrToStructure(b,typeof(Basic))).parent.ToInt64().ToString() : "UNAVAILABLE:"+s;
  } finally {Marshal.FreeHGlobal(b);CloseHandle(h);}
 }
}
'@
    }
    $w6Prefix = $w6Formal.TrimEnd('\') + '\'
    $w6Pet = Join-Path $w6Root 'pet-electron/node_modules/electron/dist/electron.exe'
    $w6Rows = @(Get-Process | ForEach-Object {
        $w6Process = $_
        $w6Path = $null
        try { $w6Path = $w6Process.Path } catch {}
        $w6Exact = $w6Path -and $w6Path.StartsWith($w6Prefix, [StringComparison]::OrdinalIgnoreCase)
        if ($w6Exact -or $w6Process.ProcessName -match '^(python.*|pip.*|QtWebEngineProcess)$' -or $w6Path -eq $w6Pet) {
            $w6Start = $null
            try { $w6Start = $w6Process.StartTime.ToUniversalTime().ToString('o') } catch {}
            [pscustomobject]@{pid=$w6Process.Id; name=$w6Process.ProcessName; path=$w6Path;
                startUtc=$w6Start; parentPid=[W6RelayParent]::Read($w6Process.Id);
                exactFormalEnv=[bool]$w6Exact; identityUnknown=(-not $w6Path -or -not $w6Start)}
        }
    })
    $w6Netstat = @(netstat -ano -p tcp)
    if ($LASTEXITCODE -ne 0) { throw 'Listener survey unavailable; no environment writes' }
    $w6Listeners = @($w6Netstat | Where-Object { $_ -match 'LISTENING' -and $_ -match ':(1188|18890|23456|23567|23568|23569)\s' })
    $w6Survey = @{utc=[DateTime]::UtcNow.ToString('o'); operation='READ_ONLY'; processes=$w6Rows; listeners=$w6Listeners;
        formalCount=@($w6Rows | Where-Object exactFormalEnv).Count;
        unknownCount=@($w6Rows | Where-Object identityUnknown).Count}
    Write-W6Json $Output $w6Survey
    if ($w6Survey.formalCount -ne 0 -or $w6Survey.unknownCount -ne 0) {
        throw 'W6.A BLOCKED: formal consumers or unidentified Python/pip remain. No automatic process termination.'
    }
}

function Invoke-W6Stage([string]$Stage, [string]$Run, [string]$LocalWheel) {
    $w6Arguments = @('-I', '-B', $w6Helper, $Stage, '--run', $Run)
    if ($LocalWheel) { $w6Arguments += @('--wheel', $LocalWheel) }
    & $w6Python @w6Arguments
    $w6Code = $LASTEXITCODE
    Write-W6Json (Join-Path $Run ($Stage + '-process.json')) @{argv=@($w6Python) + $w6Arguments; exit=$w6Code}
    if ($w6Code -ne 0) { throw "$Stage failed, exit=$w6Code. Preserve evidence; no automatic rollback or UI activation." }
}

$w6Run = $null
$w6Lock = $null
try {
    $w6LockPath = Join-Path $PSScriptRoot '.runtime/w6-package-relay.lock'
    $w6Lock = [IO.File]::Open($w6LockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    if ($RollbackRun) {
        if ($Wheel -or $AuditOnly) { throw 'RollbackRun cannot be combined with other options' }
        $w6Run = (Resolve-Path -LiteralPath $RollbackRun).Path
        $w6Allowed = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '.runtime')).TrimEnd('\') + '\'
        if (-not $w6Run.StartsWith($w6Allowed, [StringComparison]::OrdinalIgnoreCase)) { throw 'Rollback evidence must be task-local' }
        Assert-W6Idle (Join-Path $w6Run ('ProcessSurvey-rollback-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ') + '.json'))
        Invoke-W6Stage 'rollback' $w6Run ''
        Write-Output "Rollback completed: $w6Run"
        exit 0
    }
    $w6Run = Join-Path $PSScriptRoot ('.runtime/w6-user-install-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ'))
    New-Item -ItemType Directory -Path $w6Run -ErrorAction Stop | Out-Null
    Write-Output "W6 receipts: $w6Run"
    Assert-W6Idle (Join-Path $w6Run 'ProcessSurvey-before.json')
    if ($AuditOnly) { Write-Output 'Idle survey only; no pip/network/environment write'; exit 0 }
    if ($Wheel) { $Wheel = (Resolve-Path -LiteralPath $Wheel).Path }
    $w6Rollback = "& '" + $PSCommandPath.Replace("'", "''") + "' -RollbackRun '" + $w6Run.Replace("'", "''") + "'"
    Write-W6Json (Join-Path $w6Run 'RollbackPlan.json') @{command=$w6Rollback;
        prerequisites='Idle env, exact installed Addons version/RECORD, unchanged Essentials/shiboken';
        partialInstall='If no valid Addons RECORD exists, stop for manual review; do not delete DLLs or restore whole env';
        scope='Only uninstall newly added PySide6-Addons; never global/conda/VBS/other packages'}
    Invoke-W6Stage 'prepare' $w6Run $Wheel
    Assert-W6Idle (Join-Path $w6Run 'ProcessSurvey-preinstall.json')
    Invoke-W6Stage 'install' $w6Run ''
    Invoke-W6Stage 'verify' $w6Run ''
    Write-Output "W6.B/C prerequisites PASS. W6.D/E/F and native UI remain UNVERIFIED. Return receipts: $w6Run"
    exit 0
} catch {
    if ($w6Run -and (Test-Path -LiteralPath $w6Run)) {
        $w6Failure = Join-Path $w6Run ('RelayFailure-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ') + '.json')
        Write-W6Json $w6Failure @{status='BLOCKED'; error=$_.Exception.Message; productionAdoption=$false}
    }
    Write-Error -ErrorAction Continue $_
    exit 2
} finally {
    if ($null -ne $w6Lock) { $w6Lock.Dispose() }
}

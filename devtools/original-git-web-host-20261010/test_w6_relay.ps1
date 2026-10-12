# Exercise only the parsed idle guard with synthetic process rows. No pip/network.
param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$w6Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$w6Formal = Join-Path $w6Root 'envs/kuro-llm310'
$w6Utf8 = New-Object System.Text.UTF8Encoding($false)
$w6TestOutput = [IO.Path]::GetFullPath($OutputDirectory)
$w6Allowed = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '.runtime')).TrimEnd('\') + '\'
if (-not $w6TestOutput.StartsWith($w6Allowed, [StringComparison]::OrdinalIgnoreCase)) { throw 'Task-local output required' }
New-Item -ItemType Directory -Path $w6TestOutput -ErrorAction Stop | Out-Null
$w6Tokens = $null
$w6Errors = $null
$w6Ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $PSScriptRoot 'Invoke-W6AddonsRelay.ps1'), [ref]$w6Tokens, [ref]$w6Errors)
if ($w6Errors.Count) { throw 'PowerShell syntax failed' }
$w6Functions = $w6Ast.FindAll({param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -in @('Write-W6Json', 'Assert-W6Idle')
}, $true)
if ($w6Functions.Count -ne 2) { throw 'Guard extraction failed' }
. ([scriptblock]::Create(($w6Functions | ForEach-Object { $_.Extent.Text }) -join "`n"))
Add-Type 'public class W6RelayParent { public static string Read(int pid) { return "SYNTHETIC"; } }'
function Get-Process { $script:w6FakeRows }
function netstat { $global:LASTEXITCODE = 0; '  TCP 127.0.0.1:18890 0.0.0.0:0 LISTENING 999' }
$w6Cases = @(
    @{name='formal-python'; path=(Join-Path $w6Formal 'python.exe'); process='python'; blocked=$true},
    @{name='formal-pythonw'; path=(Join-Path $w6Formal 'pythonw.exe'); process='pythonw'; blocked=$true},
    @{name='unknown-python'; path=$null; process='python'; blocked=$true},
    @{name='unknown-pip'; path=$null; process='pip'; blocked=$true},
    @{name='unrelated-voice'; path='C:\synthetic-voice\python.exe'; process='python'; blocked=$false}
)
$w6Results = @()
foreach ($w6Case in $w6Cases) {
    $script:w6FakeRows = @([pscustomobject]@{Id=999; ProcessName=$w6Case.process; Path=$w6Case.path; StartTime=[DateTime]::UtcNow})
    $w6Blocked = $false
    try { Assert-W6Idle (Join-Path $w6TestOutput ($w6Case.name + '.json')) }
    catch {
        if ($_.Exception.Message -notlike 'W6.A BLOCKED:*') { throw }
        $w6Blocked = $true
    }
    if ($w6Blocked -ne $w6Case.blocked) { throw ('Guard regression: ' + $w6Case.name) }
    $w6Results += @{case=$w6Case.name; pass=$true; blocked=$w6Blocked}
}
Write-W6Json (Join-Path $w6TestOutput 'Results.json') @{mode='SYNTHETIC_NO_INSTALL'; tests=5; results=$w6Results}
Write-Output '5 synthetic idle-guard cases PASS; PowerShell AST PASS; no installer executed'

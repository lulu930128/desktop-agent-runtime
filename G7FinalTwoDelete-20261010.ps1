# Only the two user-approved legacy files may be removed. No elevation or ACL changes.
[CmdletBinding()]
param([switch]$VerifyOnly)
$ErrorActionPreference = 'Stop'
$repo = 'C:\project\desktop-agent-runtime'
if ((Get-Location).Provider.Name -ne 'FileSystem' -or
    (Resolve-Path -LiteralPath '.').Path -ne $repo) { throw 'Run from the exact repository root.' }
$allowed = [ordered]@{
    'pet-electron/src/briefing-window.html' = '17507d1d3e06a3450351bf5ffadc5cb479a1cb91678b819d9b409335d28f0c43'
    'pet-electron/src/briefing-preload.js' = 'e6314e5442bc283fce1b459b4505723eff8b6167a2a81640e0d3d3025cbf8ce2'
}
function Assert-RegularGuardedFile([string]$relative, [string]$expected) {
    $target = [IO.Path]::GetFullPath((Join-Path $repo $relative))
    if (-not $target.StartsWith($repo + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Outside checkout.' }
    $item = Get-Item -LiteralPath $target -ErrorAction Stop
    if ($item.PSIsContainer) { throw 'Expected regular file.' }
    $ancestor = $item
    while ($null -ne $ancestor) {
        if ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse point in path.' }
        if ($ancestor -is [IO.FileInfo]) { $ancestor = $ancestor.Directory } else { $ancestor = $ancestor.Parent }
    }
    if ($expected -and (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expected) {
        throw "SHA changed: $relative"
    }
}
Assert-RegularGuardedFile 'envs/kuro-llm310/python.exe' ''
# Read-only: CRC, all 35 ZIP entry hashes, pinned manifest/archive hashes, path
# guards and unchanged production source inventory. Does not extract the archive.
$preflight = @'
from pathlib import Path
import hashlib, json, stat, zipfile
root = Path.cwd()
assert str(root) == r'C:\project\desktop-agent-runtime', 'Wrong checkout'
allowed = {
 'pet-electron/src/briefing-window.html': '17507d1d3e06a3450351bf5ffadc5cb479a1cb91678b819d9b409335d28f0c43',
 'pet-electron/src/briefing-preload.js': 'e6314e5442bc283fce1b459b4505723eff8b6167a2a81640e0d3d3025cbf8ce2',
}
def guarded(relative, allow_missing=False):
 p = root / relative
 assert not Path(relative).is_absolute() and '..' not in Path(relative).parts
 assert p.is_relative_to(root) and p != root
 for q in [p, *p.parents]:
  try: s = q.lstat()
  except FileNotFoundError:
   assert allow_missing, str(q)
   continue
  assert not s.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT, str(q)
 if p.exists(): assert p.is_file(), str(p)
 return p
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
mp = guarded('docs/agent-runs/qt-ui-convergence-20261007/G7DeletionManifest.json')
assert sha(mp) == 'b605a26741ad56004a6fe45c484bcb447a292cc1d0a0b0004ae5e1eac7f5281b', 'Manifest changed'
m = json.loads(mp.read_text(encoding='utf-8-sig'))
assert len(m['files']) == 35 and len({e['path'] for e in m['files']}) == 35
assert m['archive'] == 'g7-source-rollback.zip.bak'
bp = guarded(m['archive'])
assert sha(bp) == '49c39cccbf702eac763bb3b132d9706432ac564fccfc5c83ac1e6c016288c376', 'Backup changed'
remaining = []
with zipfile.ZipFile(bp) as z:
 assert z.testzip() is None, 'ZIP CRC failure'
 for e in m['files']:
  rel = e['path']; p = guarded(rel, allow_missing=True)
  entries = [i for i in z.infolist() if i.filename == rel]
  assert len(entries) == 1, 'Missing/duplicate ZIP entry: ' + rel
  assert hashlib.sha256(z.read(entries[0])).hexdigest() == e['sha256'], 'ZIP bytes changed: ' + rel
  if rel in allowed: assert e['sha256'] == allowed[rel], 'Whitelist mismatch'
  if p.exists():
   assert rel in allowed, 'Unexpected manifest file reappeared: ' + rel
   assert sha(p) == allowed[rel], 'Source changed: ' + rel
   remaining.append(rel)
assert set(allowed).issubset({e['path'] for e in m['files']})
evidence = json.loads(guarded('G7FinalTwoResults-20261010.json').read_text(encoding='utf-8-sig'))
scan = evidence['productionScan']
assert scan['externalConsumerCount'] == 0 and scan['files'] == 323
paths = set(scan['hashes'])
for folder in ['kuro_launcher','kuro_core','pet-electron/src','pet-electron/renderer/src',
               'pet-electron/scripts','Open-LLM-VTuber/local_mcp','Open-LLM-VTuber/src','bridges']:
 for p in (root/folder).rglob('*'):
  if p.suffix in {'.py','.js','.cjs','.mjs','.ts','.html','.json','.yaml','.yml','.toml'} and p.is_file() and '__pycache__' not in p.parts:
   paths.add(p.relative_to(root).as_posix())
paths -= {e['path'] for e in m['files']}
assert paths == set(scan['hashes']), 'Production inventory changed; request a new consumer audit'
for rel, expected in scan['hashes'].items():
 p = guarded(rel)
 assert sha(p) == expected, 'Production bytes changed; request a new consumer audit: ' + rel
print(json.dumps({'preflight':'PASS','manifestCount':35,'absent':35-len(remaining),'remaining':remaining,'zipCrc':'PASS','backupEntriesMatched':35,'productionFilesUnchanged':323}))
'@
$output = $preflight | & (Join-Path $repo 'envs/kuro-llm310/python.exe') -I -B -
if ($LASTEXITCODE -ne 0) { throw 'Read-only preflight failed; nothing removed.' }
$check = ($output -join "`n") | ConvertFrom-Json
if ($check.preflight -cne 'PASS') { throw 'Missing preflight result.' }
$check | ConvertTo-Json -Depth 5
if ($VerifyOnly) { return }
# Validate BOTH existing targets before any removal, then repeat immediately per file.
foreach ($relative in $check.remaining) { Assert-RegularGuardedFile $relative $allowed[$relative] }
foreach ($relative in $allowed.Keys) {
    if ($relative -notin $check.remaining) { continue }
    Assert-RegularGuardedFile $relative $allowed[$relative]
    $target = Join-Path $repo $relative
    try {
        Remove-Item -LiteralPath $target -ErrorAction Stop
        if (Test-Path -LiteralPath $target) { throw 'File remains after removal.' }
        Write-Output "$relative : removed and verified absent"
    } catch {
        [pscustomobject]@{
            path=$relative; status='BLOCKED'; type=$_.Exception.GetType().FullName
            hresult=('0x{0:X8}' -f $_.Exception.HResult); message=$_.Exception.Message
            stack=$_.Exception.StackTrace; existsAfter=(Test-Path -LiteralPath $target)
        } | ConvertTo-Json -Depth 5
        throw 'Stopped. Do not retry with Force, elevation, ACL/owner changes, rename or directory deletion.'
    }
}
$output = $preflight | & (Join-Path $repo 'envs/kuro-llm310/python.exe') -I -B -
if ($LASTEXITCODE -ne 0) { throw 'Post-delete verification failed; no PASS claim.' }
$check = ($output -join "`n") | ConvertFrom-Json
if ($check.absent -ne 35) { throw 'Not all 35 manifest paths are absent.' }
$check | ConvertTo-Json -Depth 5
Write-Output '35/35 physically absent. Regression remains pending; Electron previous FAIL; desktop UNVERIFIED; release NOT ACCEPTED.'

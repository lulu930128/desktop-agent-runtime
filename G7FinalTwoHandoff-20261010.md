# G7 最後兩檔／G8 靜態收尾交接（2026-10-10）

**G7 33/35／BLOCKED；G8 STATIC BLOCKED；release NOT ACCEPTED。** 本輪兩檔各以原權限嘗試一次不帶 `-Force` 的刪除，均在 `System.IO.FileInfo.Delete()` 收到 `System.UnauthorizedAccessException`、`0x80070005`（Win32 Access Denied 5），磁碟複驗仍存在。沒有重試 Python unlink、升權、修改 ACL／owner／flags、改名、清目錄或結束 process。具體限制來源仍未定位，不能直接歸因特定 ACL、DLL 或安全產品。

[本輪完整結果](G7FinalTwoResults-20261010.json) 保存原始 exception/stack、SHA、ZIP CRC、production inventory、開始及結束 integrity。前輪 Python 326／25 suites、Node 83、MCP 14+4、renderer PASS 均為歷史結果；本輪未改 source，依授權不重跑全套。Electron hidden fixture 前輪 renderer 49／GPU 0xC0000135 **FAIL** 未重跑；正式 Windows／Live2D **UNVERIFIED**。

## 核對結果

| 核對面 | 本輪結果 |
| --- | --- |
| 分支／HEAD | main／995c23c7c8d1be62000229d58610d2214f3bb745 |
| Manifest | 原 35 個唯一 path；SHA256 `b605a26741ad56004a6fe45c484bcb447a292cc1d0a0b0004ae5e1eac7f5281b` |
| 備份 | `g7-source-rollback.zip.bak`；SHA256 `49c39cccbf702eac763bb3b132d9706432ac564fccfc5c83ac1e6c016288c376` |
| ZIP | 全 archive CRC 通過；35 個指定 entry 全部唯一，內容 SHA 與 manifest 一致；未解壓 |
| Production consumer | 323 個 source/config/build/policy 檔 bounded scan，manifest cluster 外引用 0；不等於 runtime 驗收 |
| 路徑 | 固定 checkout、regular files、從檔案至磁碟根的所有父目錄無 reparse |

| 唯一刪除白名單 | SHA256 | ZIP CRC32 | 本輪結果 |
| --- | --- | --- | --- |
| `pet-electron/src/briefing-window.html` | `17507d1d3e06a3450351bf5ffadc5cb479a1cb91678b819d9b409335d28f0c43` | `8b83fe20` | 仍存在／0x80070005 |
| `pet-electron/src/briefing-preload.js` | `e6314e5442bc283fce1b459b4505723eff8b6167a2a81640e0d3d3025cbf8ce2` | `49d992c3` | 仍存在／0x80070005 |

## 可直接貼上的 PowerShell

在你自己的**一般使用者 PowerShell** 執行。此命令呼叫本輪已落盤並通過唯讀驗證的 [完整 guarded 腳本](G7FinalTwoDelete-20261010.ps1)：

```powershell
Set-Location -LiteralPath 'C:\project\desktop-agent-runtime'
.\G7FinalTwoDelete-20261010.ps1
```

腳本會先驗證完整 manifest hash、archive hash、ZIP CRC／35 entry hashes、兩個目標 disk hash、path/ancestor guard，以及本輪 323 個 production 檔案 bytes/inventory 未變。全部通過才用 `Remove-Item -LiteralPath <單檔> -ErrorAction Stop`；沒有 `-Force`、遞迴刪除或其他 source 白名單。第一次失敗就停止，已刪除的檔案不會自動還原；可以重新唯讀檢查部分完成狀態。備份保持 ignored 且不變。

只想檢查、不刪除：

```powershell
.\G7FinalTwoDelete-20261010.ps1 -VerifyOnly
```

成功刪除後腳本自動逐一驗證原 manifest **35/35 physical absence**，印出 `absent: 35`、`remaining: []`。`-VerifyOnly` 也可獨立複驗。若任何 source／manifest／backup 改變，腳本拒絕刪除，需重新做 consumer inventory。勿降低 ExecutionPolicy 或其他安全設定來執行；若腳本執行本身被政策阻擋，保留錯誤後停止。

若一般 console 仍是 Access Denied，可選擇以下唯讀 metadata 診斷（不列印檔案內容、credentials 或完整 ACL）：

```powershell
$paths = @(
  '.\pet-electron\src\briefing-window.html',
  '.\pet-electron\src\briefing-preload.js'
)
foreach ($p in $paths) {
  if (Test-Path -LiteralPath $p) {
    Get-Item -LiteralPath $p | Select-Object FullName, Length, Attributes, LastWriteTimeUtc
    Get-Acl -LiteralPath $p | Select-Object Path, Owner, AreAccessRulesProtected
  }
}
```

`Get-Acl` 摘要不能證明 effective DELETE 權限，也不能定位 restricted token／filter／lock。若需要管理員身分或安全設定調整，**先停止、說明原因並另行徵詢**；本交付不授權此類變更。

## 僅在兩檔刪除成功後重跑原靜態回歸

從同一 repo root 逐項執行，任一非零就停止修正；不啟動正式 Qt／Pet／Core／Conversation／Central Voice。

```powershell
$ErrorActionPreference = 'Stop'
$g7 = .\G7FinalTwoDelete-20261010.ps1 -VerifyOnly | ConvertFrom-Json
if ($g7.absent -ne 35) { throw 'G7 still blocked; do not run the regression batch yet' }
.\envs\kuro-llm310\python.exe -B tests/run_qt_convergence.py --group python
if ($LASTEXITCODE -ne 0) { throw 'Python regression failed' }
.\envs\kuro-llm310\python.exe -B tests/run_qt_convergence.py --group node
if ($LASTEXITCODE -ne 0) { throw 'Node regression failed' }
Get-ChildItem -LiteralPath .\pet-electron\src -Filter *.js -File -Recurse | ForEach-Object {
  node --check $_.FullName
  if ($LASTEXITCODE -ne 0) { throw 'Node syntax failed' }
}
npm.cmd --prefix pet-electron run check:renderer
if ($LASTEXITCODE -ne 0) { throw 'Renderer typecheck failed' }
npm.cmd --prefix pet-electron run build:renderer
if ($LASTEXITCODE -ne 0) { throw 'Renderer build failed' }
git -c core.safecrlf=false diff --check
if ($LASTEXITCODE -ne 0) { throw 'Diff check failed' }
```

原 MCP 14+4 focused suites 與 production Python in-memory syntax，沿用各 suite 獨立 process、禁止 socket.connect、disposable TEMP、`-B`：

```powershell
@'
from pathlib import Path
import json, os, subprocess, sys, tempfile
root = Path.cwd()
assert str(root) == r'C:\project\desktop-agent-runtime'
evidence = json.loads((root/'G7FinalTwoResults-20261010.json').read_text(encoding='utf-8-sig'))
sources = [root/p for p in evidence['productionScan']['hashes'] if p.endswith('.py')]
for p in sources:
    compile(p.read_bytes(), str(p), 'exec')
print('Python in-memory compile:', len(sources))
bootstrap = "import socket,unittest,sys; socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(AssertionError('Network prohibited')); result=unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.discover('tests',pattern=sys.argv[1])); sys.exit(not result.wasSuccessful())"
with tempfile.TemporaryDirectory(prefix='.validation-temp-mcp-', dir=root) as tmp:
    env = os.environ.copy()
    env.update(TEMP=tmp, TMP=tmp, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8',
               PYTHONPATH=os.pathsep.join(map(str, [root/'Open-LLM-VTuber/src', root/'Open-LLM-VTuber', root])))
    for pattern in ['test_mcp_m0_identity.py', 'test_mcp_m0_policy.py',
                    'test_tool_catalog_market_routing.py', 'test_tool_policy_omi.py']:
        subprocess.run([sys.executable, '-B', '-c', bootstrap, pattern],
                       cwd=root/'Open-LLM-VTuber', env=env, timeout=90,
                       creationflags=subprocess.CREATE_NO_WINDOW, check=True)
'@ | .\envs\kuro-llm310\python.exe -B -
if ($LASTEXITCODE -ne 0) { throw 'MCP/syntax checks failed' }
.\G7FinalTwoDelete-20261010.ps1 -VerifyOnly
git status --short
```

將新命令輸出、時間、HEAD/dirty digest、35/35 existence 與 WIP integrity 另存成後續結果，再更新 G7/G8 的**當前** checkpoint；保留原 25/35、33/35、Electron FAIL 的歷史證據。只有 source static gate 可據此 PASS。不得重套 `G8FinalizationDocs.patch`。

## 正式 Windows 驗收留給使用者

詳見 [正式人工 checklist](docs/agent-runs/qt-ui-convergence-20261007/G8ManualAcceptance.md)。至少記錄：canonical Qt cold boot／second launch、X/tray/reveal/Quit、自有 child restart/reconnect、無 Pet 的 Qt Chat、Core notification 實際只顯示一次、Live2D 模型可見／拖曳／DPI／多螢幕，以及另外授權後的 audio／mic／camera／screen。

每項保留時間、revision＋dirty digest、PID/instance/root、操作與 PASS/FAIL/UNVERIFIED。保持 Mail／Study 原配置，不使用真 Gmail／Study／private state 作 agent 測試；不操作 Central Voice。本輪只修正證據／交接文件，未 commit/push、reset/clean/checkout 或啟動正式 runtime。

# G7 35/35 physical deletion — Final reviewer acceptance (2026-10-10)

## Gate 判斷

**G7 Physical Legacy Deletion：PASS。**
**G8 完整靜態回歸：BLOCKED（測試執行環境）；正式 Release：NOT ACCEPTED。**

本輪沿使用者在 PowerShell 完成的最後兩檔刪除，獨立讀取磁碟與 Git 狀態，不只採信腳本成功訊息。

### G7 驗證證據

- 原始 [G7DeletionManifest.json](G7DeletionManifest.json) 共列 35 個唯一來源檔，現已逐一檢查 **35/35 不存在**（包含 `pet-electron/src/briefing-window.html`、`pet-electron/src/briefing-preload.js`）。
- Git 目前對最後兩檔均標示 tracked deletion；相關 Electron `main-process` legacy modules 亦均不在磁碟上。
- ignored 回滾來源 `g7-source-rollback.zip.bak` 的 archive SHA-256 為 `49c39cccbf702eac763bb3b132d9706432ac564fccfc5c83ac1e6c016288c376`；ZIP CRC 通過，35 個 manifest 指定 entry 皆唯一且原始 bytes SHA 對應。整個 ZIP **共 75 entries**（含其餘 40 個恢復用 preimages），不誤認整包僅 35 entry。
- 本輪掃描 498 個文字檔、靜態追查 244 個檔案／3,021 條 literal import edges，未發現可以執行的舊 WorkPanel／Reader／Briefing consumer 或第二個 owner。現存少數 deprecated 名詞位於 guard/comment/doc，不能混同 production implementation。
- 對 Qt／Electron 主程式與 Renderer 額外搜尋 `briefing-window`、`work-panel`、`:23568`、`launcherControlRequest`，未見 production call path。

### 刪除後測試（2026-10-10）

| 檢查 | 本輪實際結果 |
| --- | --- |
| Node G3/G5/G6 ownership regression | **20/20 PASS**（0 skip） |
| MCP identity 3、M0 policy 5、market routing 6、OMI policy 4 | **18/18 PASS**（0 skip） |
| Python in-memory syntax | **204 files PASS** |
| Node `--check` | **15 files PASS** |
| Renderer Typecheck | **PASS** |
| `git diff --check` | **PASS** |
| Python full runner | **UNVERIFIED／環境阻擋**：repo-local disposable TEMP 建立被拒；啟動後未得到任何有效 suite 結果，runner exit 1 |
| Node full runner | **UNVERIFIED**：TEMP 前提不成立，未執行 |
| Renderer build | **UNVERIFIED**：需要可寫入檔案的預備作業，本輪未執行 |
| Hidden Electron smoke | **既有 FAIL**：先前 renderer exit 49／GPU `0xC0000135`，本輪未重跑 |
| 正式 Windows Qt／Pet／Voice／notification | **UNVERIFIED**，留待使用者在正常桌面環境驗收 |

先前工作輪次 Python 326/326、Node 83/83、Renderer build PASS 屬於**歷史 source 驗證**，本輪不能重複計入。同時，兩個最近刪除的檔案不再被新程式引用，因此目前未發現由刪除導致的 confirmed regression；仍不等同完整測試通過。

### Data / source integrity

- 本輪 Codex 唯讀測試前後保留：58 modified、34 deleted、76 untracked；1,000 個 Git-visible paths、134 個既有 WIP file hashes、498 個掃描 file hashes、235 個相關 pyc 路徑／雜湊一致。
- 未修改正式程式、正式 DB、私人 handoff/history/memory、中央語音、OS 啟動設定、權限；未 commit／push。
- Git `main` 上目前大量 WIP 是既有階段修復，不可透過 `git reset/clean` 消除。

## 使用者正式桌面／靜態補驗

在允許寫入 disposable TEMP 的一般 PowerShell 中從 repo root 執行；任一非零 exit 都保留錯誤再處理，不能跳過：

```powershell
Set-Location -LiteralPath 'C:\project\desktop-agent-runtime'
.\G7FinalTwoDelete-20261010.ps1 -VerifyOnly
.\envs\kuro-llm310\python.exe -B tests/run_qt_convergence.py --group python
if ($LASTEXITCODE -ne 0) { throw 'Python full regression failed' }
.\envs\kuro-llm310\python.exe -B tests/run_qt_convergence.py --group node
if ($LASTEXITCODE -ne 0) { throw 'Node full regression failed' }
npm.cmd --prefix pet-electron run check:renderer
if ($LASTEXITCODE -ne 0) { throw 'Renderer typecheck failed' }
npm.cmd --prefix pet-electron run build:renderer
if ($LASTEXITCODE -ne 0) { throw 'Renderer build failed' }
git -c core.safecrlf=false diff --check
if ($LASTEXITCODE -ne 0) { throw 'Diff check failed' }
```

實機還要檢查 Qt cold boot、second launch、X/tray/reveal/Quit、Qt Chat 無 Pet、Qt↔Core Today/Schedule、通知 OS 實際顯示、Live2D render/drag/DPI、授權後 voice/mic/camera/screen。先前 Electron hidden fixture FAIL 仍需與真實桌面測試區分、診斷。

**封版規則：G7 已可標 PASS；G8 仍需完成完整回歸、Electron 執行環境診斷與使用者正式桌面驗收，完成前仍不得標 ACCEPTED。**

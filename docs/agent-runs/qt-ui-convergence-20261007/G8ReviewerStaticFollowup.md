# G8 靜態收尾 Reviewer 複查（2026-10-09）

> **2026-10-10 狀態更新：**此頁的 33/35 deletion blocker 已由使用者在 PowerShell 完成，最新實際 35/35 physical PASS 與回歸限制請看 [G7PostDeleteAcceptance-20261010.md](G7PostDeleteAcceptance-20261010.md)。此頁保留當時調查證據。

> **2026-10-10 執行者補記（非新一輪 Reviewer 驗收）**：323 個 production 檔的 bounded static scan 外部 consumer=0；manifest、backup SHA/CRC/35 entries 與最後兩檔 bytes 再核對一致。兩檔各一次原權限刪除仍為 `UnauthorizedAccessException / 0x80070005`，G7 33/35、STATIC BLOCKED。只交付兩檔 guarded PowerShell，不再使用歷史十檔迴圈。見 [本輪交接](../../../G7FinalTwoHandoff-20261010.md)；前輪測試數字及 Electron FAIL 保持歷史證據。

## 結論
**STATIC BLOCKED；正式產品 NOT ACCEPTED。** 本紀錄是 G5→G8 既有 checkpoint 後的第二輪獨立複查，不取代歷史測試或實機驗收。

## 已確認事實
- Canonical Qt、Core、Conversation Runtime、Pet-only 的 G6 source ownership 已具備；本次不重建第二實作路徑。
- G7 原 manifest 35 個實體刪除候選，先前已刪 25，本輪依原 SHA/備份逐檔核對後再刪成功 8 個 Electron `main-process` legacy modules，累計 **33/35**。Reviewer 重新讀取本機專案目錄，確認那 8 個模組已不存在。
- 唯二剩餘：`pet-electron/src/briefing-window.html`、`pet-electron/src/briefing-preload.js`。`Remove-Item` 真正觸發 `System.IO.FileInfo.Delete()` 時回傳 `System.UnauthorizedAccessException`，HResult `0x80070005`。使用 `Remove-Item -Force` 會更早在 `FileSystemInfo.set_Attributes()` 回傳 `ArgumentException`，**不可將這兩種錯誤混為同一根因**。檔案沒有唯讀/reparse flag；尚未找出實際存取限制來源。
- 刪除來源 `g7-source-rollback.zip.bak` 已核對 archive SHA/CRC；原 35 檔備份內容與 manifest hash 一致；既有 88 dirty paths 與上一輪 recorded hashes 無非預期變更。不可執行 git reset/clean。
- G8 本輪**重新**執行 Python 326 tests / 25 suites、Node 83 tests、Renderer typecheck/build，全部 exit 0。另有本輪 MCP policy/identity/routing focused suites 執行通過，精確套件數以新證據檔/命令輸出為準。
- 333 個 production source/config files 的限定掃描，未發現 blocked legacy cluster 外部 production consumer；此結果是靜態掃描，不是 runtime deployment 證明。
- 原隱藏 Electron fixture 的 renderer 49 / GPU 0xC0000135 FAIL。新的最小 Electron 空白 data: 頁也同樣 FAIL，支持 Windows/Electron execution environment 層疑慮；尚未找到具體 DLL/政策/driver root cause。不能改成 PASS 或宣稱真 Live2D 正常。
- 正式 cold boot、tray、通知、Chat/Pet/Voice/device/DPI 及既有 login 行為待使用者實機驗收。Central Voice、正式 DB、OAuth、private data 均未操作。

## 剩餘靜態 blocker
1. 只對上述兩個已在 G7 manifest 的特定檔，在 SHA、repo root path、regular file 及既有備份再次核對一致後嘗試刪除。若原權限下仍拒絕，停止，勿變更 ACL、ownership、registry 或全系統 kill。
2. 刪完要重新列舉實體路徑、掃描 require/import/IPC/route/fallback 並跑回歸；不能只改 JSON `deleted` 欄位。
3. G7DeletionResults / G7Checkpoint / G8Checkpoint / MigrationMatrix 應在確認實體證據後更新；如 Codex sandbox 不能寫入 docs，需使用已授權 guarded Project Workspace 而非在舊報告中假報 PASS。
4. Electron OS 問題與正式桌面實測另列 runtime gate，不得將其混作 source regression failure 或隨意關閉 Windows 安全機制。

## 來源與驗收接力
- `docs/agent-runs/qt-ui-convergence-20261007/G7DeletionManifest.json`
- `docs/agent-runs/qt-ui-convergence-20261007/G7DeletionResults.json`（歷史 25/35，不代表這輪最後狀態）
- `docs/agent-runs/qt-ui-convergence-20261007/G7FollowupDeletionResults.json`（本輪 33/35 的增量檢查記錄）
- `docs/agent-runs/qt-ui-convergence-20261007/G8Checkpoint.md`（前輪）
- `../../../G8FinalizationResults.json`（本輪 machine-readable evidence，STATIC BLOCKED）
- `../../../G8FinalizationHandoff.md`（完整交接／安全補刪命令）
- `docs/agent-runs/qt-ui-convergence-20261007/G8ManualAcceptance.md`

**不 commit/push；未完成 G7 35/35 與正式 Windows 驗收前，不可封版。**

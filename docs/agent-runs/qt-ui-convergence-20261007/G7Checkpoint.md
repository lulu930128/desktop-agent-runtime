# G7 physical deletion checkpoint

> **最新複查（2026-10-10）：G7 35/35 PHYSICAL DELETION PASS。** 原 manifest 35 個檔案皆已在實際磁碟上消失；ZIP 回復備份 SHA／CRC／指定 35 entries 檢查通過，未發現 production 舊路徑 consumer。**本輪 G8 完整 Python／Node regression 及 Renderer build 因 Codex 暫存資料夾寫入拒絕而未完成；正式 Release 仍 NOT ACCEPTED。** 以 [G7 最終 Reviewer 驗收](G7PostDeleteAcceptance-20261010.md) 為當前狀態。以下所有 33/35 或 25/35 是各輪歷史 checkpoint，不再是當前阻礙。

> **本輪複驗（2026-10-10）**：G7 維持 **33/35／BLOCKED**。原 manifest SHA、備份 SHA／全 ZIP CRC、35 個 entry SHA 與兩個現存檔案 SHA 全部吻合；323 個 production source/config/build 檔外部 consumer=0。兩檔各一次不帶 `-Force` 的 `Remove-Item` 均在 `FileInfo.Delete()` 回傳 `UnauthorizedAccessException (0x80070005)`，複驗仍存在。沒有 source 變更，未重跑既有全套回歸。見 [本輪結果](../../../G7FinalTwoResults-20261010.json) 與 [兩檔限定交接](../../../G7FinalTwoHandoff-20261010.md)；下方歷史數字保留，不代表當前狀態。

> **後續更新（2026-10-09）**：G7 原 25/35 是前輪 checkpoint；本輪沿 manifest 另刪除 8 個，現為 **33/35**。其餘 `briefing-window.html`、`briefing-preload.js` 仍在，真正刪除時發生 `UnauthorizedAccessException (0x80070005)`。以 [增量結果](G7FollowupDeletionResults.json) 與 [Reviewer 複查](G8ReviewerStaticFollowup.md) 為當前狀態；下面的原始 25/35 明細是歷史記錄。

日期：2026-10-09。**Consumer cutover 已完成；G7 physical deletion BLOCKED，不能標 PASS。**

## Inventory 與刪除結果

刪除前已保存 [G7DeletionManifest.json](G7DeletionManifest.json)：35 個明確 source/test paths、SHA256、外部 consumer 清單及停止條件。每一檔在刪除時重新驗證 resolved path 在 repo 內、regular file、無 reparse point、SHA256 不變；只逐檔刪除，沒有 recursive source cleanup。

結果：**25 已刪、10 OS access denied**。提升執行已核准，但 Windows 仍拒絕；apply_patch Delete 亦失敗。沒有改 ACL、registry、logon、private userData。實際殘留以 [G7DeletionResults.json](G7DeletionResults.json) 為準。

| 群組 | 原清單數 | 已刪 | 阻擋 |
| --- | ---: | ---: | ---: |
| WorkPanel renderer TS/CSS + HTML | 6 | 6 | 0 |
| Reader HTML/preload | 2 | 2 | 0 |
| Briefing HTML/preload | 2 | 0 | 2 |
| Electron business modules | 8 | 0 | 8 |
| Launcher WorkPanel activation/API/recovery | 3 | 3 | 0 |
| Core legacy Briefing adapter | 1 | 1 | 0 |
| Legacy-only tests/harness | 12 | 12 | 0 |
| 舊 mail_briefing_poller.py（改名既有 producer） | 1 | 1 | 0 |

## Production consumers = 0 的證據

以 manifest 為刪除 cluster，掃描 cluster 外的 kuro_launcher、kuro_core、Electron src/renderer、local_mcp、Conversation Runtime：imports/require、routes、HTML/preload、IPC、config、fallback、bridges 均無舊 owner reference。新增 G8 architecture guard 維持此條件；blocked cluster 內互相 require 不算可達 production consumer。

- G6 main/Vite 僅 Pet entry；舊 routes 回 404，IPC/confirmation/tray/business commands 無 dispatch。
- Qt 移除 Briefing records/builders/readers、WorkPanel activation/recovery/profile/history/memory/policy proxy、send_pet_text 以及舊 task handlers/flags/aliases。
- 刪除 Launcher control host/port/property/settings；canonical :23568 無 server。
- Pet persisted-state schema 移除 Reader/Briefing/window-mode keys；preload no-op legacy bridge 與 renderer history/browser/input-send types 移除。既有 private state 檔沒有讀取／搬移／刪除。
- Pet ai_state 不再覆寫 Qt conversation state。UI mic toggles 統一走 Qt history-bound capture handler。
- Core shadow probe 只保留明確輸入的 bounded Study snapshot inspection，移除 /briefing HTTP probe 與 adapter。
- Mail 原 POST /briefing/snapshot 與 daily_brief GET/fallback 已移除。既有 single poller 改為 mail_poller.py → mail.refresh → bounded status/work handoffs；tool identity/catalog/policy 同步改名，沒有 alias 或新增 owner。Mail producer 的 legacy UI sections、fake empty task placeholders 移除；Mail classification/preferences/rules 與 Core Today policy 保留。
- mail.daily_brief 明確標示 provider query，與 Core Today 分離；不會在 dashboard 缺資料後偷偷 live refresh。
- 套件檢查：Electron package 只有 Electron、TypeScript、Vite、@types/node，皆仍被 Pet build/runtime 使用，沒有可移除的 application-only dependency。
- 歷史 docs/checkpoints/截圖保留；不視為 production consumer 或本輪實機證據。

## 修改檔案（除 manifest 的 35 個刪除候選）

- `kuro_launcher/qt_controller.py`、`qt_app.py`、`config.py`、`mail_poller_runtime.py`；`launcher_qt.py`、`kuro_launcher.settings.yaml`。
- `pet-electron/src/main.js`、`preload.js`、`state.js`；renderer `backend/types.ts`、`text-utils.ts`、`backend-client.ts` 與 Pet command bridge。
- `kuro_core/shadow_probe.py`；`Open-LLM-VTuber/local_mcp/mail_tools_server.py`、新增 `mail_poller.py`；Runtime `mcpp/tool_identity.py`、`tool_catalog_manager.py`、`tool_catalog.json`、`tool_policy.json`。
- Canonical Qt／Mail／Pet／Core tests 與現況 README／AGENTS／architecture／guides；完整本輪 path/hash sets 見 [G8Integrity](G8Integrity.json)。

## 測試與文件

G7 targeted 最終合併結果：Python 132 tests（G6 9、G3 27、G4 15、G5 17、launcher 6、Pet lifecycle 9、Schedule runtime 9、Mail status 16、Mail work 7、poller 9、Core shadow 3、Core contracts 5），各 suite exit 0。G4 初跑仍 mock 已刪方法／驗舊 alias，更新為 canonical Qt entry 後 15/15 PASS。

Node G3/G5/G6：20/20 exit 0；renderer typecheck exit 0。G8 後續增加的 checks、Mail snapshot 與 strict command acknowledgement 見 [G8Checkpoint](G8Checkpoint.md)，不把不同時間測試數混成同一輪。

目前文件已同步 README、AGENTS、architecture、guides；歷史 Progress/MigrationMatrix 區塊保留並標明日期性。

## Rollback 與限制

- 本機 ignored `g7-source-rollback.zip.bak` 保存 manifest 全部 35 個 source/test 原始 bytes，包含原有 dirty/untracked WIP；另含本階段修改前的 controller/Qt/config/Mail/docs preimages。檔案只含 source，沒有 private payload。
- 需要回退時，先核對 archive SHA/manifest，再人工局部恢復相同 source/consumer 組；不可用 git reset/clean/checkout HEAD 覆蓋起點 WIP，不可啟用雙 UI/tray/poller。
- 10 個剩餘 source 是 **legacy debt／physical deletion blocker**，不允許接回 production。精確補刪命令在 [G8ManualAcceptance](G8ManualAcceptance.md)。
- userData、DB、OAuth、history、memory、model/voice 素材沒有刪除。正式 Windows adoption、tray/notification、device input 仍 UNVERIFIED；G8 按使用者要求繼續可安全執行的 acceptance。

# G2 工具設定與來源狀態交付

狀態：**Source PASS／Isolated Qt PASS／正式 Runtime Pending／Native UNVERIFIED／OMI auto BLOCKED**。待獨立 Reviewer 確認，不宣稱全產品完成。

## 本輪驗證

- Python **14 個定點 cases PASS**：6 個工具 enabled／CAS／負向／Qt broker tests，2 個 source overview tests，1 個 Today/observations transport budget，5 個既有 ToolPolicy compatibility tests。不是重跑 G0/G1。
- Node **4/4 PASS**：source empty/partial/missing/offline/auth/stale/OMI 文案、寫入與 GET readback、取消／錯版／提權回應拒絕、presentation preferences 不可存 policy。
- 真正隔離 Qt + signed assets + Core HTTP + synthetic policy：**14/14 DOM／native modal checks PASS**。驗 21 項／4 分組、收合保留、取消不寫、確認後 atomic persistence 與 UI readback、需確認工具仍封鎖、OMI 獨立區、四來源卡片、日英 source filters 與零假工作。兩張合成截圖可讀；物理手勢與正式 Native 仍待使用者驗收。
- 正式 CoreRuntime 保留 65,536 bytes cap；本輪長 payload Today **22,509 bytes**、observations **15,914 bytes**，Qt Controller 可讀，沒有全域放大限制。
- TypeScript `tsc --noEmit`、Python syntax、UTF-8／literal corruption 檢查與 `git diff --check`；簽章／lineage／六份 Git immutable originals 按原 builder 流程驗證。舊 bundle 驗簽保留，新 pin 在 isolated acceptance 後才更新。

收據目錄：`.tmp/g2-tools-today-20261023/`。`Targeted.json/log` 保留最初 8 PASS＋1 錯誤 fixture 預期（英文缺時間實為 partial）；`SourceOverviewFixed` 與 `FinalSourceBudget` 對修正後來源斷言驗證。6 個政策測試未因後續 UI 排版改動重跑。`PolicyCompatibility.log` 的 PowerShell NativeCommandError 是 stderr 包裝，原 unittest 輸出 5/5 OK，無權限或 sandbox 錯誤。

`surface` 初次因合成 token 長度不足而拒絕；`surface2`／`surface-diagnosis` 的頁面選取失敗，已定位 raw bytes 中字面 `?`：PowerShell 管線破壞測試中文，不是產品 failure。測試修為 ASCII Unicode escapes；`surface-utf8-fixed` 14/14、最終排版 `surface-final` 14/14 PASS。失敗收據保留，未降低門檻或修改正式元件迎合壞 selector。

## Bundle／實際改動

新 fingerprint：`159c5832bca59216ceb3a4bb96f92ea031b9437a969700786c4b9ca29cf27811`。
Manifest SHA：`8552e5f1d9ef3d01ef1003439a896472d4e2e0a7ff31cfba7d871bac1fe0e727`。
Builder 收據：`devtools/original-git-web-host-20261010/.runtime/g2-tools-today-20261023-reviewed-build.json`。未降低簽章驗證、未修改 originals。

本輪產品修改：ToolPolicy consumer 的 enabled gate；新增 Launcher tool_policy_settings；Controller／Qt protocol／adapter／native confirm；Today lean overview；owner-presentation、canonical-model、owner-preferences 三個正式 overlay；release pin。新增四個 targeted test/harness 與兩份文件。正式 `tool_policy.json` 和 `kuro_launcher.settings.yaml` **未改**。

TaskDiff／ChangedPaths／Status 是本輪相對 40 dirty 基線的精確增量；其他既有 WIP hash 保留。舊 G1 106＋12、G2 與 continuation 的有效來源證據繼承，原 receipts 不改寫；新 pin supersedes 舊 pin 的下次啟動選擇，不表示現役已採用。

## 現役保留

本輪末端 listener PID 與 surface 前相同：Core 23569→50712、Pet 23567→15200、Conversation 23456→72120、Bridge 1188→30296；共享 Voice 18890→50520。所有已記錄測試 PID 均已退出；未啟停任何正式 owner、未讀私人 token／DB／信件，未 provider refresh／LLM／交易／commit／push。進程與最後 Git dirty 數以 FinalRuntime.json／Status.json 為準。

下一步與 rollback 邊界見 CurrentStateGap.md，交由 Reviewer 審查後由使用者本人實機採用。

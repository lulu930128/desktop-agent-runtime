# Core persistence 與 migration 邊界

## 現況與本輪決策

保留單 DB、固定 table namespace 與 migration owner。這是邏輯切割，沒有拆庫、搬檔、修改 schema 或對正式 DB 執行 migration。獨立 Observation storage 需在後續有具體 research／cutover contract 時再設計。

G0–G8 沒有新增 DB migration。Core Work／Attention／Today 已接管 /v1/today，但採 bounded handoff 的 in-memory projection，沒有新增 TaskStore、Today table 或正式 Observation ingest。Core GET 不 refresh、不呼叫 KuroCoreStore.ingest()；Mail writer 仍屬明確 producer，Study snapshot 由學習 domain 維護。Electron briefing-store 不再是 production truth，既有 private userData 未讀取／遷移／刪除。


正式設定：`${ROOT}/local_state/core/work.sqlite3`，DB-wide `PRAGMA user_version=3`。`kuro_core/storage.py:SCHEMA_VERSION` 是全庫支援版本，不是 Observation 專屬版本。`ScheduleCapability`／ScheduleStore 與 Launcher／Electron 的 nested Schedule capability gate 都依賴 schema 3；`CoreApplication` 的 process contract 則是獨立的 `kuro.core.api.v1`。

## Table 與 migration owner

| 階段 | Owner／入口 | Tables／責任 | 正式依賴 |
| --- | --- | --- | --- |
| 0 → 1 | `storage.KuroCoreStore.initialize()` | `observations`、`decision_traces`、相關 indexes | 新 DB bootstrap；table 存在不等於 Observation 已採用 |
| 1 → 2 | `schedule_store.migrate_schedule()` | `schedule_items`、`schedule_occurrences`、`schedule_revisions`、`schedule_mutations`、`schedule_notification_deliveries` | 正式 Schedule state、audit／revision、idempotency |
| 2 → 3 | `schedule_notifications.migrate_notifications()` | delivery lease／snooze 等 columns；`schedule_preferences`、`schedule_notification_audit` | 正式 notification scheduler／delivery |
| 全部編排 | `storage.KuroCoreStore.initialize()` | 版本檢查 → v1 → v2 → v3；拒絕較新 schema | `ScheduleCapability.__init__()` 在 service DB lease 內呼叫；`CoreApplication` 只負責 composition |

ScheduleStore 每次連線要求 schema 3；read 使用既有 DB 的 `mode=ro`，write 使用 `mode=rw` 與 transaction。Observation store 另外提供 ingest／trace persistence，但其 `initialize()` 同樣會跑上述 schedule migrations。

`kuro_core.service.KuroCore` 的 public import path 留存，功能仍限於 shadow Observation／Decision。不能以該類別名稱推論它就是正式 service entrypoint，也不能把 schedule 寫入 `Observation.details`。

## Transaction、backup 與恢復限制

- v1 DDL 在 transaction 內逐 statement 建立，避免 `executescript` 隱式 commit。
- v2／v3 升級前使用 SQLite backup API，分別產生 `.pre-v2-<id>.bak`／`.pre-v3-<id>.bak`；DDL failure rollback 該階段。
- 三段 migration 不是一次全庫原子升級。若 v3 失敗，可能保留已提交的 v2；修復後再走正常 initializer，不手動改 `user_version`。
- 必要 tables／columns 有 readiness 檢查，不能以版本號代替 schema 完整性。
- SQLite backup 包含整庫，不是單一 table 備份；檔案包含私人工作資料，與 DB／WAL／SHM／lease 都不進 Git。
- Service lease 只約束遵守此協定的 `ScheduleCapability`；直接建立 KuroCoreStore 或 SQLite connection 能繞過 lease，因此 DB 路徑隔離是研究前置條件。

## Backup／restore 與 rollback contract

目前沒有整套 Kuro 一鍵備份／自動降版工具。以下是後續有明確資料還原授權時的操作 contract，本輪未對正式資料操作：

1. 先確認 source commit、DB schema、Core instance／listener 與一致性，透過 SQLite backup API 建立含 WAL 已提交資料的一致副本；不可在 writer 活躍時只複製 `.sqlite3` 主檔。
2. 對副本執行 integrity／schema／代表性 schedule、notification、revision、idempotency 檢查，記錄備份時間與版本。
3. 以 Launcher 關閉 exact Core owner，確認 worker／connection 結束、service lease 釋放。保留原 DB 與 sidecars 的 recovery 副本，不覆蓋唯一原始資料。
4. 將備份還原到隔離路徑，使用相容版本驗證；較新 schema 不可配舊 source 強行啟動。正式替換須在無 writer 狀態下連同 WAL／SHM 一致處置，避免舊 journal 污染還原檔。
5. 重新啟動後核對 identity、schema、read/write、occurrence／completion、audit／unknown delivery 與不重送語意。需要回退時恢復先前完整備份與相容 source；不得以刪庫、降低 `user_version` 或僅 revert code 代替資料還原。

相關既有測試入口：`tests/test_schedule_core.py`（migration／backup／restore／idempotency／concurrency）、`test_schedule_notifications.py`、`test_schedule_api.py`、`test_schedule_runtime.py`，另有 `test_kuro_core_store.py`。這是驗證範圍索引，不表示本輪文件修改已重跑全部或驗證正式 restore。

## 後續 schema 變更規則

每次變更都先回答：受影響 table owner、全庫版本、升降級策略、所有 consumer gate、migration failure 重入、private backup 與 runtime adoption。研究一律使用獨立 DB；Git worktree 不會自動隔離 env、absolute config、Electron userData 或中央服務。

已知耦合仍存在於共享 bootstrap，不能宣稱實體 persistence 解耦完成。未來是否拆 Observation DB，須根據正式 Observation cutover、資料敏感度與 recovery 成本決定。

# 來源遷移、重建與還原

以下 PowerShell 從此 repo 執行。`$fixtureRoot` 應指向自建的隔離目錄，內含 `chat_history` 與 `memories`。`$restoredRoot` 是尚不存在的新路徑。正式來源、正式啟動設定及私人資料須另選定範圍。

```powershell
$python = (Resolve-Path '.\envs\kuro-llm310\python.exe').Path
$env:PYTHONPATH = (Resolve-Path '.\Open-LLM-VTuber\src').Path
& $python -B -m open_llm_vtuber.memory_maintenance backfill $fixtureRoot $actor
& $python -B -m open_llm_vtuber.memory_maintenance backup $fixtureRoot $archive
& $python -B -m open_llm_vtuber.memory_maintenance restore $restoredRoot $archive
& $python -B -m open_llm_vtuber.memory_maintenance backfill $restoredRoot $actor --apply
```

1. 關閉該隔離根的寫入者，以取得跨檔案的一致時間點。封存包含 History、事件、待處理形成工作、政策、角色與共享記憶；SQLite 衍生索引從來源重建。保留原始根與 archive。
2. 先看 dry-run 的 eligible、excluded、failed 及各來源的工作結果。可重複 `--history ID` 選定歷史，或用 `--project ID` 選定專案。`--include-legacy` 另行納入可識別的舊格式，未確認身分不提升為跨角色事實。`--facts` 啟用已選範圍的事實形成；原有授權規則仍適用。
3. 在還原根上使用相同選項加 `--apply`。中斷後以相同參數續跑，來源 revision 已完成者可略過；損壞來源須保留原檔與錯誤，修好該來源再續跑。檢查 terminal 結果及失敗數；只看行程結束不足以判定完整。
4. 更換 encoder 時，對還原根重新執行索引核對，比較固定查詢的來源 turn、版本、停用和遺忘結果。啟用語意模型可設定 `KURO_MEMORY_ENCODER_DIR` 指向具備 `model_quint8_avx2.onnx` 與 `tokenizer.json` 的本機目錄。
5. 回復演練以支援新 scope 的相容 Repository 搭配封存，還原至另一個新根；核對 manifest、History 與正式記憶數。若正式使用者在切版後新增資料，必須先由 owner 對帳這些增量，才可決定正式指向。勿覆寫正在使用的根。
6. 正式切版須另取得目標角色、專案、日期／歷史範圍、授權模式及維護時段。以原 Launcher 執行，記錄 runtime 身分、模型、Qt 首輪／跨日／切角回讀及復原結果。


### 已知身分的 scope 遷移

執行 `migrate-scopes $fixtureRoot $newRoot --project $projectId` 會驗證封存、在全新目錄內重排已具明確 scope 的資料。相同 ID 遇到不同內容會停止發布。只有已標記 local-user 或能對上所選 project 的既有身分可遷移，其他資料繼續留在原角色。檢查 moved、unresolved 與 actor_retained，再核對新舊來源。既有授權、ID 與內容保持原值；正式部署及授權仍要由原 Launcher 操作。

若衍生 SQLite 損毀，在一致來源上執行 `rebuild-copy $fixtureRoot $newRoot --character $actor --project $projectId`。可重複指定角色及專案。這個 CLI 複製 canonical 檔案、重建選定投影、執行 SQLite integrity_check，再發布至新根。來源損毀時回報原因與失敗數。舊索引與切版後新增資料保留在原目錄。失去的衍生回填收據，可用原選項在新根重跑並依來源 ID 去重。


### 模型與回復時的相容性

語意模式在本機已有 ONNX Runtime 1.23.0、tokenizers 0.22.1 及 NumPy。可選套件清單在 Open-LLM-VTuber/requirements-companion.txt；重放前核對 Evidence 的兩個模型資產 hash。只停用 encoder 可回到 FTS；既有授權記憶和歷史仍由目前版 Repository 寫入。若要退回有 80 筆裁切行為的舊程式，應以還原副本唯讀比較：舊版對 shared namespace 與新增授權缺乏完整支援。正式程式 rollback 應使用保留新版 writer／scope 讀取相容性的版本，或在獨立根完成新增資料對帳後另行決定。

### 已重放的故障與切版後寫入

從 repo 根執行 `& $python -B "$run/migration_replay.py" "$run/recheck-migration.json"`，其中 `$run` 為本任務文件目錄。四個獨立程序寫入 366 個模擬日期、兩角色與兩專案，之後在新根切版、追加資料、破壞衍生索引、重建至另一個根並核對來源 hash。比對 `original_unchanged`、`post_cutover_retained`、`repaired.failed` 與各 scope 數量。已知測量結果見 [Migration.json](Migration.json)。

若正式採用，明確選擇後續回合的角色、專案、記憶類型（偏好／經歷／目標）與分享範圍；舊歷史需另外選擇角色、專案或 history IDs、是否納入 legacy、只建情節索引或也形成候選／已授權事實。日期需求先由 owner 對應到明確的歷史與回合範圍，CLI 目前提供 history 與 project 選取。核對目標後才由原 Launcher 切版，再記錄正式 Qt 聊天、來源、更正、語音、工具、Live2D 及 Today 讀回。

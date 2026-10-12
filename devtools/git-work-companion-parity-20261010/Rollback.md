# Source cutover 與回退邊界

目前 source 的唯一入口仍是 `launcher_qt.py → KuroQtLauncherWindow → WorkCompanionView`。沒有環境變數選擇第二套 production UI，沒有第二個 Electron Work Panel。執行中的 runtime 尚未採用本次 source，這份文件不授權啟停服務。

## 已保存的資料

- `Baseline.json`：修改前 HEAD 與原有 189 筆 WIP 的 hashes。
- `DeltaManifest.json`：25 個本次 source／test 項目的前後 hashes。`new_file` 與 `retired` 明確分開。
- `rollback/<path>.before`：15 份修改前精確 bytes，包括所有 10 個正式 runtime/UI 檔、3 個既有測試、2 個退役 preview 檔。
- `after-source/<path>`：本次結果的精確 bytes。`delta/<path>.patch` 供讀碼比較，不是可直接套用整個 dirty checkout 的 Git patch。
- **缺口**：`tests/test_g3_conversation.py` 的修改前 hash 為 `4cd5bb42df32ccda8534887718adc1fa879ffeea5f9388c0361f1bc9a395762e`，但原 bytes 未捕捉；猜測重建未匹配 hash，因此沒有冒充備份。

## 使用者決定回退 source 時

1. 先檢查 HEAD 仍為 `995c23c7c8d1be62000229d58610d2214f3bb745`，並將每個待回退檔的目前 SHA-256 對照 manifest 的 `after_sha256`。任何差異都表示後來還有工作，應停止自動覆寫，改人工合併。
2. 正式 UI/runtime 應作同一批回退：6 個 `kuro_launcher/qt_*` 檔與 4 個 `Open-LLM-VTuber/src/open_llm_vtuber/` 檔。不要只退 Qt client 或只退 WS history protocol。使用 Python `Path.read_bytes/write_bytes` 做逐檔精確回寫，不能用會轉碼的 PowerShell pipeline。
3. 不必恢復已退役的 preview；它們沒有 production consumer。任何需要保留的測試改動依 `delta/` 人工挑選；G3 舊測試的 exact-byte rollback **不可驗證**，不能盲目用 HEAD 取代 untracked WIP。
4. 校驗回寫結果等於 `before_sha256`，確認 G7 35 個 path 仍 absent，檢查 diff 僅有明確回退項目。禁止 `git restore/checkout/reset/clean`；不碰資料庫／History／Memory／模型／credentials。
5. Source 回退後使用與當時 source 配套的測試；本次 history.v1 integration tests 不能拿來宣稱舊 Console 同樣支援新協定。Runtime adoption／重啟仍須使用者在另外的實機驗收階段處理。

## Source 驗證與之後實機驗收

隔離命令（不啟動正式 app）：

```powershell
.\envs\kuro-llm310\python.exe -X utf8 -B tests/run_work_companion_parity.py test_work_companion_source_encoding.py test_r1_ws_dispatch_regression.py test_r1_history_parity.py test_r1_production_view.py test_r2_settings_parity.py test_r3_today_schedule_parity.py test_r4_history_transport.py test_v1_work_companion_view.py test_g3_conversation.py test_g4_qt_core.py test_g5_desktop.py test_g6_pet_boundary.py test_g8_runtime.py
.\envs\kuro-llm310\python.exe -X utf8 -B tests/run_work_companion_parity.py --scale 1.25 test_v1_work_companion_view.py
.\envs\kuro-llm310\python.exe -X utf8 -B tests/run_work_companion_parity.py --scale 2 test_v1_work_companion_view.py
.\envs\kuro-llm310\python.exe -X utf8 -B tests/run_work_companion_parity.py --start-dir Open-LLM-VTuber/tests test_character_memory_manager.py test_mcp_m0_memory.py
```

以上測試使用 mock、offscreen、臨時 loopback WS/HTTP 與 temp DB；wrapper 阻擋正式服務埠與外部連線。未測正式 Windows 桌面，不能以此取代使用者 acceptance。

實機應先由 Reviewer 通過 source，再由使用者安排一次 Qt＋Conversation 相容版本的採用；只在專用測試角色／測試資料驗證 History、Profile 與刪除取消／確認。若 handshake 未提供 `history.v1`，新版 UI 必須保持操作不可用；不可降級為檔案讀寫或舊 IPC。之後才逐項驗證 Today/Schedule、Memory、Pet、感知與 OS notifications。這些步驟本輪均未執行。

# W10 進度

- 基準核對、raw preimage／SHA 保存完成。
- `qt_app.py` 已刪除 136 個退役方法及 Widgets style；保留 30 個正式 owner／lifecycle 方法。
- 三個舊 UI modules 已實體刪除；正式 source／測試已無其 import。
- History ClientTests、RuntimeTests、strict-read／sidecar 測試、CoreWrapperTests、Memory／Policy owner 測試保留；真實 loopback WS CRUD 改走正式 Web Port／RequestBroker／Adapter。
- 首輪 History migration 出現 `KeyError: preview`。舊 drawer 的展示欄位為 `preview`，canonical WS／Web contract 是 `last_preview`；同時沿用 Web adapter 的 `history_owner_rejected` 錯誤投影。未修改 Backend 或降低 domain 斷言。針對性重跑 2/2 PASS。
- W10 current profile 已完成：267 項 Python＋20 項 Node，共 287 項 PASS，exit 0；350 個檔案 SHA 前後一致。Python syntax 與 `git diff --check` 通過。
- 狀態為 `W10_SOURCE_ISOLATED_PASS`，正式 runtime adoption／Win11 native cold start 尚未驗收。歷史測試仍可能使全庫 default discovery 失敗；詳見 [Checkpoint.md](Checkpoint.md)。

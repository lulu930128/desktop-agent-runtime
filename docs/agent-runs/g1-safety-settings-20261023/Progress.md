# G1 交付紀錄

基準 main `c53f2f0d59c44c63e2120785beb989231de3e558`，起始 clean；不 commit/push。
證據位於 `.tmp/g1-safety-settings-20261023/`，本文件不將 source/隔離結果當成正式 runtime adoption。

## 已完成

- Bridge stop/profile/toggle/restart/close 僅處理 held `ManagedProc`；未知 listener 不查 PID、不 taskkill。停止失敗保留 handle，restart 不繼續 spawn。中央 Voice 分支未變更。
- Settings > 語音與感知新增獨立「主動語音通知」；Tools／工具與權限新增 OMI 觀測、間隔及每日查詢上限。預設兩者關閉，明示 `G1 execution unavailable`。
- Qt native confirmation → Adapter → Controller → authenticated Core HTTP → JSON 原子保存 → POST 回應 → GET 讀回；UI 不以 localStorage 保存政策、不先顯示成功。
- Core handler response 保持自己的 contract；Qt Adapter 明確包裝自己的 `ok: true`。既有 Core HTTP server 也會加入 ok，因此不能由靜態缺欄推論正式 UI 必然失敗。`updateAssistantSettings` 屬 mutation 且強制 native confirmation，renderer 不可帶 `confirmed`。revision CAS 拒絕過期寫入，取消與 context 變更不寫。
- 原始 Settings 的 runtime 更新會重建容器；overlay 重掛同一表單，保留未儲存輸入。沒有修改六份 immutable originals。
- Pet outfit/expression 僅將原始 renderer 的提示轉為 canonical ID；參數仍由既有 owner 產生。附件 UI 明示且 transport 預先拒絕超出既有 native/backend caps 的資料。

## Core 保存與後端使用

`kuro_core/assistant_settings.py` 由唯一 `CoreApplication` 在取得既有 Schedule store lease 後建立。路徑由該 store 的 DB path 推導為同目錄、同 stem 的 `.settings.json`，不新增 service/manager，不修改 DB/schema。缺檔 read 不建立檔案；只有明確確認的 POST 才寫入。

格式為 schema 1、單調 generation、settings。寫入同目錄暫存檔，flush/fsync 後 replace；409 要重新讀取及確認，不自動重送。損壞、過大、redirect、無法讀取的檔案一律 fail-closed，不自動修復或覆蓋。需復原時由操作者保留原檔並另行處理，不用 runtime 自動 reset。

Core `/status.capabilities.assistantSettings` 及 `admission()` 每次讀取 owner policy；兩種 action 即使 enabled 也不准執行，理由為 `execution_not_available_g1`（零預算為 `query_budget_zero`）。查詢用量與上次觀測為 null，不能顯示虛構的零用量或執行成功。G1 尚無 OMI 排程／主動語音 executor；這是已揭露的能力缺口。

## 驗證

`run_checks.py` 與每組命令、PID、exit、log 留於 ignored evidence。

| 驗證 | 結果 |
| --- | --- |
| Bridge mock regression | 8/8 PASS；修正前負向失敗紀錄保留 |
| Settings store + actual Qt Port queue → Core HTTP → frontend contract | 10/10 PASS |
| Frontend contract／Pet hint／附件 caps | 22/22 PASS |
| Core isolated runtime | 3/3 PASS |
| Qt Adapter candidate regression | 41/41 PASS |
| W10 affected owner／signed bundle gate | 17/17 PASS |
| G1 補充 Core owner 重建／HTTP policy／並行 CAS／壞檔／Adapter envelope | 5/5 PASS |
| TypeScript `tsc --noEmit` | PASS |
| 簽章候選實際 Qt WebEngine DOM／native dialog fixture | 12/12 checks PASS，`surface-2/Result.json` |

共 106 個 targeted tests；DOM 12 checks 另外列，不重複算成 unit tests。未跑全庫 discovery。W9 56/56、W10 287/287 僅繼承 G0 已驗 hash 的歷史證據，不宣稱修改後重跑歷史整套。

最後 5 個測試原執行名稱誤稱 G2，log 保留在 `.tmp/g2-settings-acceptance-20261023/tests.log`；它們只驗證 G1，不是 G2 implementation。交付測試檔改名 `tests/test_g1_settings_acceptance.py`，同步更正 fixture 名稱，邏輯未變；未重跑。這次直接 test invocation 沒有保留子 PID receipt，不能補稱完整 process lineage 證據；其他分組 receipt 與 Qt surface PID 另存。

首次 Settings 測試缺少既有 conversation src 的 PYTHONPATH，修正測試啟動參數後通過。首次 surface 探針完成 DOM 操作後因未安裝 psutil 而失敗；`surface-1` 原始結果保留，後續使用 Windows 既有 PID snapshot API，未安裝套件。

offscreen WebEngine 發生 D3D context lost，截圖黑畫面。DOM 與儲存接線可驗證，像素呈現、實體手勢與 native desktop acceptance 為 **UNVERIFIED**；未關閉 sandbox、未更改 GPU flags。對話框由隔離 fixture 自動選 Yes/No，不能代表真人操作驗收。

## 簽章與 rollback

既有 builder 比對六份 originals 與 Git commit `995c23c7c8d1be62000229d58610d2214f3bb745`，產生新 content-addressed assets、manifest 與 Ed25519 signature。候選定點測試及 DOM 接線通過後才更新 `qt_web_release.py` pin；W10 gate 驗證簽章、lineage、tampering rejection。

- 新 fingerprint：`c45c572dd566dafb4cd7f7e3aeb05d3d9edf5588e97e502554e5f7bd2fdd7cca`
- 新 manifest SHA-256：`7327d4b085a29581f39fbccda9e9f4a5893aef82bfe3a2544ff8a1eea291a0c5`
- 舊 fingerprint：`8ba8ea29313601f944f760b901410efb8fc92bc801199d3b0b72ba22b7fa9b14`

舊資產及舊 pin 四欄在 Baseline.json 保留。Rollback 只需經受控修改恢復四欄 pin 並驗證舊 bundle，不刪除任何資產；本輪未執行 rollback 或正式重啟。生成資產依既有 `.gitignore` 留在本機，交接需帶上簽章資產或使用既有建置流程，不能只攜帶 source pin。

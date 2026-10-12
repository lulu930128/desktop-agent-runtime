# Work Companion 回遷 checkpoint

本工作延續同一個 R0–R4 job。2026-10-10 的結果是 **source-ready／isolated PASS，實機與獨立 Reviewer 尚未驗證**。正式 Qt、Conversation、Core、Pet、共享語音均未啟停；沒有讀取私人 History／Memory／Voice，沒有 provider 呼叫、commit 或 push。

## Gate 結果

| Gate | 結果 | 可查證內容 |
| --- | --- | --- |
| R0 | PASS（inventory） | [對照表](GitWorkCompanionParityMatrix.md)：59 個功能契約、138 個 source functions、155 個 DOM／bridge references、24 個 bridge methods、358 個 CSS rules；HEAD 與 3baf057 原始 SHA 均校驗。兩版都沒有 gold／180px exact snapshot 證據。 |
| R1 | PASS（source／temp WS／正式 view fixture） | 唯一 WorkCompanionView 內的 History 搜尋、新建、選取、active、刪除確認、empty／error／busy。正式 Qt client → real ephemeral WS → WebSocketHandler → temp canonical history CRUD；不用本機 controller history stitching。工具事件、換行、Enter／IME、停止、附件限制、profile/context/history fencing、回應去重與過期處理均有測試。 |
| R2 | PASS（有 owner 的接線）；明列 GAP | 六類 Settings 同頁；Profile 確認與新 context 生效證據；Memory 角色／digest 確認；唯讀工具政策；完整五種錄音操作、camera/screen 確認、Pet outfit/expression/input/window、diagnostics。工具權限寫入／確認隊列沒有 owner，保持停用。Memory 明示現有 260 字限制。 |
| R3 | PASS（Core projection／temp HTTP／DB） | Today priority、source filter、來源狀態、詳情與 limitations；刷新不清除已選項目，失敗保留且標示上次投影。可見草稿與脈絡標記不自動送出。Schedule prepare／revision／scope／idempotency／confirm／notifications 沿用 Core。 |
| R4 | PASS（source cutover／隔離檢查）；實機 UNVERIFIED | 正式 `_build_ui` 只組裝一個 WorkCompanionView／HistoryDrawer；移除 HistoryChatPage、V1 synthetic model／preview 程式與舊 Console 組裝。G7 35/35 維持 absent。100%／125%／200% offscreen 與 1120／1280／1440 logical widths 驗證。 |

原截圖未附在本輪，逐像素 fidelity 未通過驗收；Today 改為同頁詳情、完整角色／模型選擇集中 Settings，Chat 有直達入口。這些差異在矩陣中明列，不能說「所有畫面原封不動恢復」。

## Reviewer 指出的 regression

- `WebSocketHandler._message_handlers` 已回到 `__init__`，History 不重設 mapping。建構、Qt-primary／frontend／console／Pet 的原路由有 6 項專門 regression。見 [R1DispatchFix.md](R1DispatchFix.md)。
- History／Chat 被 shell 破壞的 `???` 文案已以 UTF-8 patch 修復。現在對 6 個 Qt UI／controller 檔做嚴格 UTF-8、U+FFFD、AST string literals、指定繁中訊息與 Python syntax 檢查。見 [EncodingFix.md](EncodingFix.md)。
- 驗證正式 `KuroQtLauncherWindow` 與其完整頁面 builders，沒有以未被載入的 HistoryChatPage 測試替代。fixture 遇到 Qt callback exception 會使測試失敗。

## 驗證證據

[ValidationSummary.json](ValidationSummary.json) 保留各 suite 的 command、退出碼、測試數與不可覆蓋的 `test-runs/<UTC timestamp>/results.json`／stdout/stderr。每次 run 包含受測 source hashes。

- Python：20 個不同 suite，208 項 PASS。其中最後主線 13 個 suite 共 142 項；另外 Core/Schedule/runtime/entrypoint 49 項、Memory owner 17 項。
- Node：Pet presentation／desktop owner／allowlist 20 項 PASS，[完整輸出](NodeOwnerRegression.txt)。
- 125% 與 200% 的同一正式 layout fixture 各額外 7 項 PASS，不重複計入上述 208 項。
- G7：[35/35 absent](G7Absence.json)。WIP：[189 筆原基線，176 筆未變、13 筆屬本任務，範圍外變動 0](WIPIntegrity.json)。另有 3 個原本乾淨的 canonical owner 檔案在 allowlist 中變更。
- [DeltaManifest.json](DeltaManifest.json)、`delta/`、`after-source/`、`rollback/`：本 job 的 source 範圍、前後 hashes、差異與 byte snapshots。[DiffCheck.txt](DiffCheck.txt) 返回 0；CRLF 正規化警告不是失敗。
- [OffscreenEvidence.json](OffscreenEvidence.json)：全部為正式 view＋SYNTHETIC fixture，沒有真機或私人畫面。

曾經失敗且已修正：錯用缺少依賴的 Python（改回既有 `envs/kuro-llm310/python.exe`，未安裝任何東西）；測試 fixture 未補 profile／project 欄位；新增 layout 測試把建構期 mock calls 算成按鍵副作用；temp WS fixture 使用了不存在的 slot 名稱，已改由實際刪除按鈕觸發。沒有忽略失敗或把空 stdout 視為 PASS。

## 剩餘限制與交接

- Mail 手動刷新／郵件內文與 Study 課程跳轉沒有正式 action owner，維持不可用；來源狀態仍依 Core projection 顯示。
- 工具確認隊列／政策寫入沒有 canonical owner；不新增旁路，不因唯讀政策可顯示就宣稱 runtime 已採用。
- History 最近 120 則上限與舊 Git controller 一致；更早分頁前後均未提供。訊息檔與事件 sidecar 的刪除不是 atomic；失敗時明示可能部分刪除、要求重新讀取，不自動重送。
- Byte rollback 的真實缺口：`tests/test_g3_conversation.py` 有修改前 hash，沒有保存修改前完整 bytes；不得宣稱它可 exact-byte rollback。10 個正式 runtime/UI 檔案都有完整前後 bytes。詳見 [Rollback.md](Rollback.md)。
- Windows 真機視覺／IME／GPU／tray／多螢幕、Live2D、Mic／camera／screen、真實 Profile/model/voice 與私人資料全部 UNVERIFIED。由使用者另行實機驗收。
- 下一步是獨立 Reviewer 依 [ReviewerHandoff.md](ReviewerHandoff.md) 靜態複查。沒有替 Reviewer 宣告核准。

任務文件原先指定的 `docs/agent-runs/` 位置遭 Windows 檔案寫入拒絕；因此本次同一 job 的文件與證據集中於此目錄，沒有改 ACL 或另建主程式。

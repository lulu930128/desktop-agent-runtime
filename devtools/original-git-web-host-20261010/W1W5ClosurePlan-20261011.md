# W1–W5 精確收斂計畫

本次範圍：feature-off candidate、disposable 測試與證據。最後停 W5 人工檢查；W6/W7 未授權。正式 launcher/VBS/Widgets、六個 pinned frontend、G7 刪除狀態、index 與無關 WIP 皆保護。

進入基線：main `af83df273602be3a616d6567855ea71d61a9ace7`；442 dirty paths；1,293 路徑 SHA/absence；index `947abd52c8c418b5207a996b24a4ee95e57ce699050598bd9b7b4c1a6d85ac91`。精確 bytes、Before.diff、Index.diff、preimages 位於 `.runtime/w1-w5-closure-20261011T072319Z/`。以本輪實際 source/receipts 為準；舊文件停止於 W1/W6 的描述不限制這次授權。

所有 Gate 分開記錄 source/disposable、native、人工驗收。不得把 synthetic PASS 升級為 native 或產品 PASS。單一路線硬阻塞時保留錯誤，繼續獨立安全工作。

## W1：Native／視覺

- 目標／owner：Qt WebEngine 隔離 host 的原版 renderer；視覺唯一來源是六個 pinned Git 檔，Windows/Chromium 負責 native 字型、DPI、控制項。
- 程式：`qt_preview_host.py`、`capture_parity.py`、`typography.js`、`w1_geometry_diagnostics.py`、`summarize_w1.py`；只允許非 pinned harness 必要修正。
- 進入：核對六個 SHA、最新 `.runtime/w1-windows-relay-20261011T0636350178563Z/` 24 pairs、其執行 fingerprint 與現在 host 一致。
- 實測／負例：保留 strict 原值；分類 Today kicker Intl 輸出/line-box +3px、native date intrinsic width、125%/200% quantization；測 import，native 可用才做 focus/IME/navigation/resource/download/permission。不可用留 traceback 與正常使用者 relay。
- 結束：24 pairs 參照及 SHA、原因/嚴重度/未知處、人工判準；host 若變更必須重跑 matrix。W1 PASS 需真 native 證據及人工接受，目前 strict FAIL 不變；不補 CSS、不正規化數值。
- 回滾：本 Gate 不改 pinned/正式程式；若有 helper 修改，只依本輪 preimage 與最終 SHA 逐 hunk 回退，舊 receipts 保留。

## W2：Qt WebHost／Bridge

- 目標／owner：既有單一 QMainWindow 的 child view；QWebChannel Wire → GUI RequestBroker → QtOwnerAdapter → 原 controller/client。正式 Widgets default-off 不變。
- 程式：`kuro_launcher/qt_web_host.py`、`qt_web_protocol.py`、`qt_web_adapter.py`；`frontend/src/owner-bootstrap.ts`、`owner-bridge.ts`、`vite.owner.config.mjs`；task-local native runner。
- 進入：W1 raw FAIL 已登記、source hashes 完整；只准 fixture marker，不注入 readiness PASS。
- 實測／負例：build manifest/tamper/traversal/CSP/網路/檔案/導航/下載/permission/storage deny；bootstrap-before-main、GUI queued workers、timeout/unknown/duplicate/context fence、關閉後 late delivery。真正 WebEngine/QWebChannel 由隔離 native runner 驗，受阻則 UNVERIFIED。
- 結束：來源與 compiled allowlist regression 通過；native 每個 probe 各自記錄，沒有 fallback bridge；無新增正式 client/tray/notifier/worker/process。
- 回滾：candidate 保持 OFF；逐檔 preimage 回退 host/helper，禁止動正式入口。

## W3：Chat／History 與可開啟 UI checkpoint

- 目標／owner：同一 QtRuntimeChatClient qt-primary WS；Conversation 是唯一 history/conversation owner。沿用 adapter，不建新 chat manager。
- 程式：`qt_chat_client.py`（唯讀）、adapter/protocol/owner presentation；`tests/test_qt_web_transport.py`、candidate/frontend tests；新增隔離測試入口及 PowerShell relay。
- 進入：W2 source gate、fixture 無正式設定或私人資料；native import 硬阻塞不得阻擋 source 路線。
- 實測／負例：真 disposable WS 的 stream/tool/interrupt/history list/new/select/delete；confirm cancel、stale/duplicate/disconnect/reconnect/replay/timeout、actor/history/revision fence；attachment MIME/size/data；Enter/Shift+Enter/composition。native modal、鍵盤/IME 使用 native 時才算證據。
- 結束：提供原版 Qt WebEngine candidate GUI 可重現命令、synthetic 標示、bounded 關閉與 log/screenshot（有執行才記錄），native gap 列明；完成 W3 checkpoint 後自動推進 W4。
- 回滾：關閉 fixture 視窗，只停止自有 loopback 子程序；不碰正式服務。新 helper 可保留供 reviewer，沒有正式 adoption。

## W4：Settings／Memory／Pet／Tools

- 目標／owner：六分類保持原 DOM/CSS；profile 由 controller/effective WS；Memory 由 Open-LLM-VTuber canonical manager；ToolPolicy 唯讀；Pet capture/presentation 經既有 gateway，Qt scoped submit。
- 程式：adapter、owner bridge/presentation；`test_qt_web_w4_w5.py`、`test_qt_web_disposable.py`、R2/candidate tests；controller/memory manager 僅讀取沿用。
- 進入：W3 source checkpoint 與 native relay 已具體；無 live provider/device/private data。
- 實測／負例：disposable Memory JSON+SQLite，260 字、actor/digest、native confirm/cancel、offline/stale snapshot/actor swap；profile 必待新 context 且 WS effective；capture 外層/內層拒絕、未知結果不能重送、policy 不升權。
- 結束：所有受影響 source/disposable cases 通過；native 六分類/確認/裝置如未驗則 UNVERIFIED，synthetic Pet 不能證明真裝置。
- 回滾：task preimage 局部還原；測試資料只在 factory disposable root，正式 Memory/設定不修改。

## W5：Core Today／Schedule／Notifications

- 目標／owner：Core `/v1/today` 唯一排序/工作 projection；Schedule Store/schema v3 唯一 mutation；QtScheduleDelivery 唯一 claim-authorize-ack，Web 不配送。
- 程式：candidate canonical-model/adapter/bridge；既有 Core API/Schedule 與 Qt notification（唯讀）；disposable、notification、Schedule、frontend tests。
- 進入：W4 source 結果；Core HTTP 僅 ephemeral loopback + disposable DB，不啟動 scheduler。
- 實測／負例：read/prepare/取消前後 DB bytes 相同；mutate revision/key/確認、replay/concurrent/conflict；materialize denied；Today 36 property cases/context cache invalidation；通知 revision/replay/單 owner；Mail body/refresh、Study jump、Tool mutation、incomplete lifecycle 保持 GAP。
- 結束：24 methods owner/read-write/freshness/side effects/audit lineage 清單；五份 receipts/logs；W3/W5 native test commands；six SHA、G7 35 absent、index/無關 WIP SHA 獨立重驗；W5 統一 checkpoint 並停止，不做 W6/W7。
- 回滾：candidate OFF 與原 Widgets 即正式保護；局部 diff 只依本次 preimages 回退，disposable DB 不可用來替換正式資料。

## 實作與驗證策略

優先重用 `validate_candidate.py`、`w1_import_probe.py`、既有 fixtures/Core/Memory managers。測試 output 使用新目錄，保存 argv/cwd/exit/log/count；重跑不重複加總。新 native fixture 只連自建 loopback，禁止任何正式 port/外網與 security override。若無法執行 native runner，交付可執行 source 與明確 UNVERIFIED，不能聲稱已展示。

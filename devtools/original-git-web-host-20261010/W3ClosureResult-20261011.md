# W3 checkpoint：隔離原生候選入口備妥；GUI UNVERIFIED

依 [Gate 計畫](W1W5ClosurePlan-20261011.md) 進入：W2 source tests 通過、native import 阻塞已保存，沒有正式 readiness 注入。

owner 仍是 `QtRuntimeChatClient` → qt-primary WS → Conversation；renderer 經既有 host/adapter。新增 `candidate_native.py`／`Open-NativeCandidate.ps1`，開一個可見 synthetic QMainWindow 與 child WebEngine，無 tray、notifier 或 formal launcher。`candidate_fixture_service.py` 只提供 disposable Core/Memory 及非 LLM synthetic Conversation；WS fixture 抽到既有 `tests/web_candidate_fixtures.py`，transport tests 與 runner 共用，沒有另一個正式 manager。

實测：`qt_web_transport` 2、`r1_history_parity` 22、`r4_history_transport` 2；新增 `candidate_native_relay` 1（真 child service、WS 兩次重連 context、Memory JSON/SQLite、Core prepare/read/replay、關閉）。`qt_web_candidate` 41 與 frontend 14 包含 streaming/tool/interrupt、CRUD confirm/cancel、stale/duplicate/unknown、附件 MIME/size/data、IME guard、context/revision。這些 suite 有重疊，**不可跨 checkpoint 重複加總**。

來源 logs 在 `.runtime/w1-w5-closure-20261011T072319Z/{w3-validation,w3-relay-fix,w3-final,final-affected}/`。首次 sidecar test 因測試預期 Memory path 不符 canonical `ensure_character_memory_root(output/memories)` 而 FAIL；已修正 fixture 預期並實測 PASS，沒有改 canonical manager。TS target 不支援 Object.hasOwn 的中間錯誤已改為現有 target 支援的 hasOwnProperty.call，最新 typecheck PASS。

真 native 嘗試：`native-W3/NativeResult.json`、`native-error.log`，PID60816、task `.venv` import PermissionError13，**未建立 window、未啟動 sidecar、沒有 screenshot**。不是可見 UI 已驗收。

```powershell
& 'C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010\Open-NativeCandidate.ps1' -Checkpoint W3
```

同一入口保留到 W5，見 [人工步驟與限制](NativeCandidateReview-20261011.md)。正常環境成功時保存 PNG、PID、asset/source SHA、channel/worker/confirmation metadata；BOOTSTRAP_OBSERVED 只代表觀測到 renderer 與 bridge，仍不等於 native IME/keyboard/visual/security PASS。

本 Gate 結束於 source/disposable PASS＋launch source 可用、native UNVERIFIED，依授權繼續 W4/W5。回滾／關閉：視窗 X 關閉 self-owned fixture 與 sidecar；stdin EOF/close 及最長20分鐘限制，無廣泛 kill、正式服務不受影響。

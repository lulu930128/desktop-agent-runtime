# 獨立 Reviewer 靜態複查入口

狀態：**PENDING**。這是交接材料，不是 Reviewer 核准。請先核對 [DeltaManifest.json](DeltaManifest.json) 與目前檔案 hashes；[Progress.md](Progress.md) 區分 source、fixture、實機與未恢復能力。

## 建議先檢查的 correctness 邊界

1. `websocket_handler.py`：`WebSocketHandler.__init__` 在建構時建立 `_message_handlers`；`_handle_fenced_history` 不重建 mapping。原 frontend／console／Pet 的 dispatch 與 allowlist 保留。History 僅 qt-primary 使用 request/client/conf/context/expected-history fences，建立／刪除仍由 Conversation owner 執行。
2. `qt_app._build_ui` 與 `qt_work_companion_view.py`：正式視窗只有一個 WorkCompanionView、一個 HistoryDrawer；signals 接既有 QtRuntimeChatClient。沒有 HistoryChatPage 或 fake rows fallback；Settings 是同頁六分類。
3. `qt_chat_client.py`：response 在 observer 之前更新 client；request id 與 UID 不符不完成 pending；set-model/reconnect 清掉舊 context；舊 socket callbacks 不能清掉新連線。timeout 不 replay mutation。text/audio/interrupt 帶 scope；PrimaryConversationOutput 的 scoped tools/text/control 不洩露給 Pet，stale event 不串入新對話。
4. History 的所有 reader 是 canonical Runtime；Qt 不呼叫 `controller.read_history_records/read_history_timeline/delete_history`。strict read 失敗不能偽裝 empty，system prompt 不進 timeline。刪除兩個檔案非 atomic 的限制有 UI 提示，沒有假報成功。
5. Profile apply：選取值不當成生效值；native confirmation 後 freeze，需新 context 與 matching conf/project/model/thinking、owner task 完成。Memory 的確認綁當時角色與 record digest；delete／compact owner 也驗證 digest，沒有另建 repository。
6. Today 使用 Core 既有排序／分類，不復活 Briefing/mail/market provider；定時刷新保留 workId，錯誤標示上次投影與禁止使用 stale draft action。Schedule 的 revision/scope/prepare/idempotency 仍由 Core 驗證。
7. Encoding：新增 UI 文案以 UTF-8 patch；static test 遍歷 6 個 Qt source 的字串與 U+FFFD，並 compile。Reviewer 指定的三個位置有明確繁中固定文案。

## 直接讀測試

- [建構與角色 dispatch](../../tests/test_r1_ws_dispatch_regression.py)
- [History／turn fences 與錯誤](../../tests/test_r1_history_parity.py)
- [正式主視窗完整 History／Chat 操作](../../tests/test_r1_production_view.py)
- [正式視窗 → 真實臨時 WS → canonical temp History](../../tests/test_r4_history_transport.py)
- [六類 Settings／Memory／Profile／感知／Pet](../../tests/test_r2_settings_parity.py)
- [Today／Schedule](../../tests/test_r3_today_schedule_parity.py)
- [正式 layout／IME／附件／單一 UI／G7](../../tests/test_v1_work_companion_view.py)
- [UTF-8 regression](../../tests/test_work_companion_source_encoding.py)

`test_v1_work_companion_view.py` 的歷史檔名保留，但已改成 production-window fixture，沒有 SyntheticPreviewModel。所有 tests 的 controller/device/lifecycle side effects 都被 mock 或限於 temp；fixture 會捕捉 Qt slot exception 作為 FAIL。

## 不能省略的限制

原兩張圖片的 exact fidelity、正式 Windows／Live2D／語音／感知／通知與私人資料均 UNVERIFIED。Mail/Study 舊 action 及工具確認隊列沒有 owner；明列不可用。`tests/test_g3_conversation.py` 只有 before hash，無 before bytes；10 個 production source 檔均有完整 rollback bytes，不能把這個 test-only 缺口藏成「全 worktree 可精確還原」。

完整功能與 CSS 對照見 [GitWorkCompanionParityMatrix.md](GitWorkCompanionParityMatrix.md)，完整輸出與 hash 見 [ValidationSummary.json](ValidationSummary.json)。

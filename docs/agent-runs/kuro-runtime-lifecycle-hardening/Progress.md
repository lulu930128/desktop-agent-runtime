# Progress

## Status

- Current phase: completed
- Last updated: 2026-08-24

## Completed

- 重現並確認 half-alive runtime：Launcher 與 backend services 存活，Electron／23567 消失。
- 確認 secondary `--work-panel` path 只呼叫 Pet control，失敗結果被忽略後退出。
- 確認 Work Panel close IPC 原本是 hide，但 native/window lifecycle 尚未保證 tray-resident。
- 確認現有 dirty worktree，將 Kuro Core、Roadmap、Work Panel profile 與 mouse policy 變更列為保護範圍。
- 新增 Launcher-owned Work Panel activation event；secondary `--work-panel` 不再直接呼叫 Pet control。
- 新增序列化、可合併的 `ensure-work-panel` 任務，讓 Work Panel 與完整 profile readiness 解耦。
- Pet control `/status` 新增 service、protocol、PID、instance identity；Launcher 對未知 listener fail closed。
- Electron native close 改成 hide，保留 tray-resident runtime；真正 app quit 才允許關閉視窗。
- 補上 lifecycle targeted tests，並更新 README 的 canonical 啟動契約。
- Live cold-start 發現 `start-profile` 仍會在早期 Work Panel 顯示後終止 Pet；已改成 backend restart 保留 Pet shell，並以 instance identity 補償啟動期間的意外 replacement。

## Validation evidence

- `launcher.combined.log`: existing launcher detected, followed by repeated `existing work panel reveal failed: <urlopen error timed out>`。
- Live process/listener inspection: `23568` owner 是既有 Launcher；`23567` 與 Electron process 缺席。
- Computer Use: 關閉後沒有 Kuro／Electron 可見視窗。
- `python -m unittest tests.test_launcher_entrypoint tests.test_pet_lifecycle tests.test_work_panel_api`: 17 tests passed。
- 首次 live cold-start：Work Panel 在 5.16s 先 ready，但後續 Pet instance 被 profile restart 取代；此 finding 已回到 implementation 修正，targeted tests 更新後 17 tests passed。
- 修正版 cold-start：Work Panel 在 3.11s 先 ready，當時 `wsConnected=false`；完整 runtime ready 後五個 port 全部在線，Pet 維持 `26860 / 26860-mt72i46i`，`wsConnected=true`。
- Close/reopen：右上角關閉後 `briefingVisible=false`，但 Pet PID／instance／23567 保留；再次執行 VBS 於 1.50s 內恢復，同一 Launcher 與 Pet identity 均未改變。
- Crash recovery：精確終止已驗證 Pet PID 後，Launcher PID `16048` 保留；再次執行 VBS 於 4.34s 建立新 instance `7412-mt72lff9` 並恢復可見面板與 WebSocket。
- Rapid repeat：連續執行 VBS 五次後仍只有一個 Launcher 與一個 Pet main process，identity 未改變。
- Computer Use：cold-start、VBS reopen 與 crash recovery 後都擷取到唯一且可操作的「Kuro 工作面板」。
- Static checks：Python `py_compile`、VBS `/check`、Electron `node --check`、mouse policy Node tests 5/5、`git diff --check` 全部通過。

## Decisions made

- 修復 ownership，不讓 VBS 或 secondary launcher 直接管理 Electron。
- Work Panel 啟動與完整 profile readiness 解耦。
- 陌生 listener fail closed；只允許處理已驗證 Kuro identity。
- backend/profile restart 保留 Pet shell；若啟動期間 Pet instance 真的更換，Launcher 以 instance identity 觸發一次 reconcile reveal。

## Known issues / risks

- `pet-electron/src/main.js` 有既存未提交 mouse policy 變更，實作必須做 additive integration。
- 本次採按需 crash recovery：Pet 意外退出後，再次點 VBS 會自癒；尚未加入無限 background watchdog，以避免 intentional exit 與 crash 未分流前產生重啟迴圈。

## Next step

- 觀察日常使用；若未來需要「不用再點 VBS 也自動復活」，下一階段先新增 intentional-exit reason 與 bounded restart budget，再啟用 watchdog。

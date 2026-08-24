# Kuro Runtime Lifecycle Hardening

## Goal

- 讓 `桌寵啟動器.vbs` 在冷啟動、工作面板隱藏、Electron 意外退出及重複點擊時，都由既有 Launcher 安全地確保唯一 Work Panel 可見。
- 將 Launcher 固定為 runtime lifecycle 的唯一 owner，不再讓 secondary launcher 直接依賴可能已死亡的 Pet control server。

## Non-goals

- 不重構 Kuro Core、聊天、記憶、tool policy 或外部 domain integration。
- 不拆分 Work Panel 與 Pet 為兩個 Electron app。
- 不新增 Windows Service、Task Scheduler 或會形成第二個 supervisor 的常駐程序。
- 不修改角色、TTS 模型、LLM contract 或使用者資料。

## Hard constraints

- `桌寵啟動器.vbs` 維持薄入口，不能自行 kill PID、重試整套 runtime 或成為 lifecycle owner。
- 只允許 Launcher 啟動／停止已確認身分的 Kuro Electron；陌生 listener 必須 fail closed。
- Work Panel 不等待 LLM／TTS 完全 ready 才顯示；局部服務故障要以降級狀態呈現。
- 重複啟動請求必須 idempotent、bounded、不可產生重複 Launcher 或 Electron。
- 保留目前 worktree 的 Kuro Core、Roadmap、Work Panel profile 與 pet mouse policy 未提交變更。
- 不 commit、push、清除 private state 或廣泛終止 Python／Node／Electron 程序。

## Context

- Repo: `C:\project\kuro`
- Entry point: `桌寵啟動器.vbs` -> `launcher_qt.py --work-panel`
- Launcher control: `127.0.0.1:23568`
- Pet control: `127.0.0.1:23567`
- Reproduced state: Launcher、Bridge、LLM、TTS 存活，但 Electron 與 `23567` 消失；secondary launcher 只對 `23567` reveal，timeout 後仍以成功碼退出。
- Current Electron close contract: Work Panel 的 UI close 走 `briefing-close` hide，但 Electron lifecycle 沒有對 native close／all-windows-closed 提供 tray-resident 保證。

## Deliverables

- Launcher-owned Work Panel activation event 與 pending request handling。
- Idempotent `ensure_work_panel`／Pet readiness contract，包含 service identity、protocol version、PID、instance ID 與 bounded wait。
- Electron tray-resident close semantics，以及可診斷的 runtime identity。
- 冷啟動時先顯示 Work Panel、profile 在背景繼續啟動。
- Targeted Python／Node tests、syntax／type checks、runtime endpoint 與可見 UI acceptance evidence。

## Done criteria

- 冷啟動、關閉後重點、Electron 意外退出後重點、啟動期間重複點擊都只產生一個 Launcher 與一個有效 Pet shell。
- `23567/status` 回傳正確 Kuro service identity，且 Launcher 驗證後才沿用 listener。
- Work Panel 在 LLM／TTS 尚未 ready 時仍可顯示真實降級狀態。
- 工作面板 close 後 Electron／tray／`23567` 仍存活；再點 VBS 可重新顯示。
- 真實 runtime 採用本次 source，且 Computer Use 可看見 `Kuro 工作面板`。
- 所有變更通過相關 unit、syntax、renderer 與 `git diff --check` 驗證。

## Open questions / assumptions

- 本次把關閉 Work Panel 定義為 hide；完整退出仍由 tray Quit 或 Launcher 停止 runtime 負責。
- 先提供按需 crash recovery（再次啟動時重建）；若後續需要無操作自動拉回，再以可區分 intentional exit 的 bounded supervisor 擴充。

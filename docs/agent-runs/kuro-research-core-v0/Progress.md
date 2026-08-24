# Progress

## Status

- Current phase: Milestone 2 shadow validation started; runtime/UI window-layer safety validated
- Last updated: 2026-08-24

## Completed

- 重新讀取 repo instructions、Product Vision、Operating Model、Quality Bar、Roadmap 與既有長任務文件。
- 確認 worktree 在開工前為 clean，現有 runtime 不需重啟或修改。
- 建立 Kuro Research Core v0 的 Goal、non-goal、trust boundary、里程碑、stop-and-fix 與完成條件。
- 建立 shadow-only `kuro_core/` package，尚未接入 Launcher、Electron 或 Open-LLM-VTuber。
- 建立 versioned、validated 且 metadata 不可變的 Observation contract，將 availability、freshness 與 connection 分開。
- 建立 SQLite schema、WAL、transaction、idempotency conflict 與 decision trace 基礎。
- 建立 Legacy Briefing source-status adapter；只轉換來源 health metadata，不複製 private message 或 domain payload。
- 加入 timezone、bounded current、missing、stale、schema、duplicate、concurrency、context projection 與 trace tests。
- 建立 loopback-only、credential-free shadow probe，可輸出來源 connection／availability／freshness aggregate，不寫入 DB。
- 建立 `ContractMap.md`，固定 v0 ownership、Observation、status projection、persistence、context、trace 與 privacy boundary。
- 修正桌寵滑鼠政策：開啟滑鼠穿透時整個 pet host 穿透；關閉時只有 Live2D hit area 可互動，透明區域仍保持穿透，避免 5120×1526 host 鎖住桌面。
- 將 F10、tray、IPC、Work Panel 與 game mode 的 mouse state 收斂到同一套 pure policy，並在狀態切換或視窗關閉時清除 transient hover／drag state。
- 強化普通對話與設定頁的角色切換：長時間 TTS reload 使用持續進度、IPC 例外用 `try/finally` 復原控制項、成功後重新同步 Launcher／conversation／pet state，partial sync 顯示警告。
- 收斂桌寵視窗層級政策：先套 focusability、再重申 `screen-saver` topmost，顯示／還原後以不搶 focus 的 `moveTop()` 修復 Z-order，並在 `always-on-top-changed` 掉層事件後自我修復。
- `/status.petWindowPolicy` 新增 expected／actual topmost、focusable 與 visible 狀態，讓重啟後可直接驗證原生視窗契約，不只靠截圖猜測。

## Validation evidence

- `.\envs\kuro-llm310\python.exe -m unittest tests.test_kuro_core_contracts tests.test_kuro_core_store tests.test_kuro_core_shadow_probe`: 16 tests passed。
- `.\envs\kuro-llm310\python.exe -m unittest discover -s tests -p 'test_*.py'`: 27 tests passed。
- `.\envs\kuro-llm310\python.exe -m py_compile ...`: 新增 Core modules 通過 compile。
- `git diff --check`: passed；只有 Git 的 CRLF conversion warning。
- 不落盤 live probe：目前既有來源可以同時投影為 `connection=connected` 與 `freshness=stale`，且輸出未包含 message／domain payload。
- 新增範圍掃描未發現 SQLite、`.env`、token、secret、credential 或 launcher log artifact。
- `node --test --test-isolation=none .\tests\pet_mouse_policy.test.cjs`: 5 tests passed。
- `node --test --test-isolation=none .\tests\pet_mouse_policy.test.cjs .\tests\pet_window_policy.test.cjs`: 7 tests passed。
- `npm run check:renderer`: passed。
- `npm run build:renderer`: sandbox 內先因 Vite child process `spawn EPERM` 失敗；在核准的執行環境重跑後 passed，保留既有 Live2D non-module script warning。
- Electron main／state／control server／menu／preload `node --check`: passed。
- `.\envs\kuro-llm310\python.exe -m unittest discover -s tests -p 'test_*.py'`: 27 tests passed。
- Live runtime evidence：pet host 目前橫跨 5120×1526；16:59 的兩次 `/launcher/switch-profile` 皆回 200，現行 Launcher status 與 pet renderer 都回報 `yumi`，問題屬於 mouse policy 與切換中的 UI feedback／recovery，不是 backend profile request 未執行。
- 18:05 scoped restart 後 `/status.petMousePolicy` 已存在，證明 mouse policy source 已由 live Electron 採用；同一 live pet host 仍橫跨 5120×1526，使用者截圖證明一般 Notepad 視窗可覆蓋 Live2D，故另列為 window-layer regression。
- 1.0.0 release gate：Python `py_compile` 通過，完整 `unittest discover` 為 33 tests passed；mouse／window policy Node tests 7 tests passed；renderer typecheck 與 production build passed；VBS `/check`、UTF-8 讀回與 `git diff --check` passed。
- Live adoption：五個 canonical listeners 皆由 repo 預期 executable 擁有；`/status` 回報 `kuro-pet-control`、renderer WebSocket connected、`petMousePolicy.mode=transparent-passthrough`，且 `petWindowPolicy.actualAlwaysOnTop=true`、`actualFocusable=false`。

## Decisions made

- v0 不接 live runtime；避免新資料 owner 尚未完成前破壞目前工作面板。
- current observation 必須同時有 `observed_at` 與 `valid_until`，否則 fail closed。
- 同一 integration／idempotency key 若語意不同，視為 conflict，不採 last-write-wins。
- Decision trace 保存 references、digests、bounded summary 與 metrics，不保存 raw prompt。
- 全穿透開關採明確語意：`on = full-passthrough`；`off = transparent-passthrough + model-interactive`，不允許 `off` 退回整個透明 BrowserWindow 可點擊。
- Profile apply 不因短暫 UI 狀態決定成功；以 Launcher response 加上 conversation／pet state reconciliation 判定，未同步時保留 partial warning。
- Pet topmost 必須是可觀測、可重申的 runtime policy；不可只在 BrowserWindow 建立途中呼叫一次 `setAlwaysOnTop()` 後假設 Windows 多螢幕 Z-order 永遠不變。

## Known issues / risks

- 目前只完成 Observation／context projection／decision trace；Task、Attention、Action、Policy 與 Audit authoritative contract 尚未實作。
- 尚未建立 persistent shadow runner、API、scheduler、backup／restore 或 runtime lifecycle。
- Legacy Briefing store 與 Today classifier 仍是目前 live primary；新 Core 尚不是使用者可見真相來源。
- 各來源 TTL 尚未定義正式設定 owner；adapter 目前要求呼叫端提供或使用保守預設。
- Window-layer policy 已由 live Electron 採用；後續若 Windows 更新、螢幕拓樸或縮放設定改變，仍需重新做多螢幕 Z-order regression。

## Next step

- 回到 Milestone 2，將 per-source TTL／retention 收斂到正式 settings／adapter owner，並建立 legacy-vs-Core shadow comparison。

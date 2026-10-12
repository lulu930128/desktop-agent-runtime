# Kuro Qt / Live2D 收斂計畫

日期：2026-10-07  
狀態：Final target locked（2026-10-09）；**G0 source checkpoint ready，G1 尚未開始**。後續依 `QtFinalConvergencePlan.md` 執行 G1 → G8；G0 證據見 `G0Checkpoint.md`。

## 目標

Kuro 最終只保留兩個使用者可見桌面 surface：

1. PySide6 Qt 主介面：唯一主 UI，承擔 Chat、Today、Schedule、History、Memory、Profile、Tool Policy、Settings、Diagnostics、Tray 與 OS notification presentation。
2. Electron Live2D shell：只承擔 Live2D render、motion/expression、audio/lipsync、mouse interaction、window geometry/display 與最小必要 pet-local control。

Electron Work Panel、Reader、Briefing window、Electron-owned Today/Briefing/Mail/Study business ownership在逐項 cutover 後**實體刪除**。舊 Electron 功能自此 Feature Freeze；除 blocking bug/security/data-loss/migration instrumentation 外不再新增或調整功能，產品功能改動等 Qt canonical 後再做。完整 Gate / deletion / acceptance 定義見 `QtFinalConvergencePlan.md`。

## 硬性原則

- 不把 Electron business logic 直接翻譯後塞進 Qt。
- Qt 是 presentation / user-command layer，不成為 Today、Mail、Study、Tool、Memory 的第二套 domain owner。
- 一次只切換一個 authoritative read/write path；cutover 前可 shadow 比較，但不得雙 writer。
- 新正式路徑完成後不保留 silent legacy fallback。
- Schedule / notification eligibility 保持 Kuro Core ownership。
- Conversation、MCP/tool policy、character memory 保持 Open-LLM-VTuber/runtime ownership。
- Central Voice Runtime 是外部共享 owner；Kuro 只觀察與消費，不停止或重啟。
- 外部 domain truth（例如 mail provider、study system、OMI）不因顯示於 Kuro 而轉移 ownership。

## Milestones

### M0 — Migration baseline
- 盤點 Qt、Electron Work Panel、Reader、Briefing、Pet shell、Core、conversation runtime。
- 建立 capability migration matrix。
- 記錄 live listener baseline 與未驗證範圍。
- 不改 production behavior。

### M1 — Backend ownership cutover foundation
- 先把 Electron legacy primary 的 Today / Briefing / Mail / Study 責任拆出 presentation layer。
- 先定 versioned contract，再做 shadow parity；不得直接把 JS 邏輯搬入 Qt。
- Core Observation / Decision 目前只有 shadow，不能假設已有 production Today/Task/Attention API。
- 若新增 Task/Attention/Today owner，先建立明確 schema、freshness、timezone、dedup、persistence 與 migration contract。

### M2 — Qt feature parity
- Schedule UI 改由 Qt 直接消費既有 Core API，不複製 recurrence/notification domain logic。
- Today / source status / detail UI 在 backend owner 完成後接到 Qt。
- Chat / History / Memory 以既有 Qt UI 為基礎收斂。
- Tool Policy、Perception、Pet controls、Diagnostics 保留單一 Qt surface。
- Qt chat 必須先脫離 Electron renderer 的 send-text path，才能宣稱 Qt chat 獨立。

### M3 — Desktop ownership cutover
- single-instance activation target 改為 Qt 主窗。
- Qt 成為預設 visible window。
- Tray 與 OS notification presentation 由 Qt 接管。
- 啟動鏈變成 Launcher/Qt -> runtime/Core + background Live2D shell；不再啟動 Work Panel。

### M4 — Live2D shell slim-down
Electron 僅保留：
- Live2D render / model loading
- expression / motion
- audio playback / lipsync
- pet window / mouse / display geometry
- pet-local status/control

移出或刪除：
- Work Panel
- Reader
- Briefing UI/store
- Today classifier
- Mail poller/service
- Study projection
- Schedule UI/proxy
- Launcher-control UI proxy
- 非 pet-local tray/menu

### M5 — Legacy removal
- 刪除已完成 cutover 的 window、IPC、route、store、renderer 與 compatibility path。
- 搜尋 dead code / duplicated ownership / old fallback。
- :23567 收斂成 pet-only contract；:23568 若已無 consumer，移除整個 Work Panel control surface。

### M6 — Final acceptance
至少驗證：
- single-instance / second launch activation
- restart / crash / reboot recovery
- Qt ↔ conversation runtime
- Qt ↔ Kuro Core
- Qt ↔ Live2D shell
- Schedule CRUD / notification / ack
- Today source freshness / stale / partial / missing
- Mail / Study ownership與刷新
- History / Memory / Tool Policy
- Central Voice consumer 與文字降級
- Live2D motion / expression / audio / geometry
- legacy route / IPC / window / persistence writer 不再 production 生效

## 回滾原則

每個 cutover 都必須保留「切換前同一份已驗證 state」的回滾方式。回滾只能在單一 authoritative owner 間切換，不得以同時啟用新舊 writer 作為回滾策略。

## 本輪非目標

M0 不：
- 啟動目前停著的 Kuro production stack
- 修改 production DB、history、memory、mail preferences/rules
- 建立新的 Today/Core implementation
- 刪除 Electron legacy
- commit / push

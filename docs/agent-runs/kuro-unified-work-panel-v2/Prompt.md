# Kuro 統一工作面板 v2

## 背景

Kuro 目前的普通對話、Briefing、Reader、行事曆與各資料來源預覽分散在 Qt、Electron Reader 與 Electron Briefing 等多個可見介面。使用者希望主要功能留在同一個工作面板，不再另外打開多塊功能視窗。

## 目標

- 以 Electron 既有 Briefing 視窗為相容入口，改造成唯一主要工作面板。
- 工作面板只保留三個使用者層級入口：`對話`、`今天`、左下角 `設定`。
- 普通對話維持第一級、可直接使用的模式。
- 行事曆是 `今天` 模式的主要時間視角；Mail、Study、News、Market、Messages、Notes 是內容來源與篩選器，不是主導航。
- 所有項目共用同一個右側詳情面板；需要延伸討論時，清楚帶回同一個普通對話 composer。
- 建立一致且可長期擴充的 Kuro 視覺 token 與前端模組邊界。

## 非目標

- 不重寫 Open-LLM-VTuber、Briefing pipeline、OMI、Mail、Memory 或 Tool Policy。
- 不把市場判斷、資料 freshness 或 domain logic 搬到 renderer。
- 不移除 Qt Launcher 或舊 Reader 的相容 contract。
- 不導入新的 UI framework 或大型 dependency。
- 不建立第二套長期記憶 storage／policy、外部系統寫入或新的自動刷新行為；工作面板只代理既有 launcher 記憶操作。

## 硬性限制

- 保留現有 `set-briefing-visible`、`briefing-*`、`reader-*` 與 control-server contract。
- Renderer 只呈現 backend 已提供的 `today`、`sections`、`sourceStatus`、`mail`、`study` 與 runtime state。
- `stale`、`partial`、`missing`、`offline`、`auth`、`unknown` 等狀態必須如實顯示。
- 既有 dirty worktree 內容皆視為使用者工作，不得覆蓋或回復。
- 桌寵設定只能呼叫 allowlist 內既有安全動作。

## 交付物

- Vite/TypeScript 工作面板入口與樣式。
- 對話、今天、共用詳情、設定四個呈現區域（其中設定是左下角入口）。
- 對既有 Electron main/preload/menu 的局部相容接線。
- 可讀取目前聊天紀錄、送出一般對話與附件的工作面板 chat。
- 在同一工作面板內接回對話歷史管理、角色／專案／模型／推理深度、麥克風／鏡頭／螢幕、記憶審核、工具政策檢視與桌寵外觀控制。
- 建立 loopback-only launcher control contract；renderer 不直接讀寫角色、記憶、工具政策或 runtime config 檔案。
- TypeScript、Node syntax、renderer build 與可行的實際畫面驗證。

## 完成條件

- 桌寵右鍵或 tray 可直接打開「Kuro 工作面板」。
- 工作面板內不再需要開另一個 Reader 或 Briefing 視窗完成主要瀏覽。
- 普通對話可顯示目前對話並送出文字／附件。
- `今天` 第一屏優先顯示需要處理的事情與今日行程，來源內容以下層 filter 呈現。
- 點擊 Today 或來源項目會在同一視窗打開詳情；可將項目明確帶入普通對話。
- 設定固定在左下角，提供桌寵與工作面板的安全設定及 runtime 狀態。
- 相關檢查通過；若 runtime 無法啟動，清楚記錄未驗證風險。
- 對話紀錄以暫時抽屜呈現，不建立永久第二欄；設定一次只顯示一個分類。
- Profile／memory／history delete 等寫入操作具備明確確認與錯誤回報。

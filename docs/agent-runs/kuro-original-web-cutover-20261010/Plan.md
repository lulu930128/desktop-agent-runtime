# Kuro 原版 Work Companion 前端收斂與管線回接計畫

日期：2026-10-10（Asia/Taipei）
狀態：**計畫審議／原版 Web UI 先建立 scoped Git baseline；尚未開始 production cutover**
範圍：`C:\project\desktop-agent-runtime`
決策：使用者已人工確認隔離瀏覽器預覽就是想要的 Chat／Settings 版型；**這只證明目標視覺選對，並不代表 Qt WebEngine／正式 Backend 驗收已完成。**

## 0. 最終判斷與不變條件

- **唯一正式 UI**：原始 Git Work Companion Web renderer，最後由 **Qt QMainWindow + QWebEngineView** 承載。不可再用 PySide6 Widgets／QSS 重繪整份 Chat／Settings／Today。以原始 DOM、CSS、交互、78px icon rail、50px chrome、青綠色 tokens 為視覺規格。
- **Qt**：唯一 application window / tray / second-launch mutex / process owner / qt-primary conversation client。Web 前端是 Qt 內的 presentation，不能變成獨立 Electron 應用或第二套 WS owner。
- **Electron**：只有單一 Pet BrowserWindow（Live2D、presentation／audio、擷取、位置與 pet-local :23567），不恢復 Work Panel／Reader／Briefing 視窗、preload、IPC、business gateway 或 :23568。
- **後端 owners 不動**：Conversation／History／Character Memory／Tool Policy 由 Open-LLM-VTuber；Schedule／Task／Attention／Today 由 Kuro Core；Mail／Study／OMI 的 domain truth 由各自既有 owner；Qt Controller 負責 lifecycle 與當前受控 facade。
- **先接通、驗證，再移除**：舊 Qt Widgets 主畫面僅能做短期測試回滾路徑，正式環境不可雙 UI 同時對話／訂閱、雙排程與雙寫入。切換 Gate 通過後移除 dead widget/UI code；不得先砍掉可用 controller、Core 或 service。
- 新增按鈕、頁籤、status、彈窗、動線，**必須使用 `frontend-design`、`design-taste-frontend`、`ui-ux-pro-max` skill** 審查，並以原版 CSS tokens／資訊層次設計；不得自由改一套陌生視覺。

## 1. 固定原始 Source of Truth 與本輪基準

### 1.1 原始版與當前 candidate

- 原始 Git commit：`995c23c7c8d1be62000229d58610d2214f3bb745`。
- 本輪已還原到：`devtools/original-git-web-host-20261010/frontend/`。原始 `main.ts`、`styles.css`、`model.ts`、`types.ts`、`schedule.ts`、`work-panel.html` 均已由 `SourceVerification.json` 確認與該 commit 位元相同。
- `frontend/src/work-panel/main.ts` 的 `renderShell / renderChat / renderHistoryDrawer / renderSettings` 為唯一 presentation source；`styles.css` 為唯一 visual source；`types.ts: WorkPanelBridge` 為前端契約參考。
- `frontend/src/baseline.ts` + `preview-bridge.ts` + `synthetic.json` 是**隔離預覽**：不得將 synthetic bridge、假回覆或直接 fallback 搬到正式產品。
- 現有 `qt_preview_host.py` / `preview_protocol.py` 也是 read-only synthetic proof，不是正式 connector。所有完成度以實際 production bridge 和 source/test 為準。
- 原始 CSS 的 `--rail-width: 78px`、`--chrome-height: 50px`、`--iris: #65b3a6`、原有 Settings 六分類及 Composer／History drawer 都是可比較的固定項目。

### 1.2 本機現況（提交前盤點）

- Git 分支：`main`；觀察到 **412** 項未提交路徑：**61 修改、34 刪除、317 未追蹤**；暫未 staged。
- 大量先前 Qt G0-G8 / R0-R4 的程式、文件、tests、資料流已在 working tree 而未提交，包含 `kuro_launcher/qt_app.py`、`qt_chat_client.py`、`qt_controller.py`、`qt_core_pages.py`、`qt_work_companion_view.py` 與 Core/Conversation/Pet 改動。
- 原有 `QtFinalConvergencePlan.md`、`GitWorkCompanionParityMatrix.md` 等對**舊 Qt Widgets**的「PASS」不等於新 Web Host 已接線；不得沿用其測試冒充 Web renderer 的驗收。
- 使用者已在正常瀏覽器親自查看原始預覽並確認版面正確。先前 Codex headless Chrome / WebEngine 因 OS/GPU/依賴阻塞，尚無可比較 Qt Host 截圖；正式切換仍 `BLOCKED`。

### 1.3 第一個 commit：只建立可還原的 UI Source 基準

**請先做一筆 scoped local commit**（例如 `chore(kuro): checkpoint original work-companion web UI and cutover plan`）。它必須只含：
1. `devtools/original-git-web-host-20261010/frontend/` 下不被忽略的 original renderer / bootstrap / synthetic fixtures / TS+Vite config；
2. 本任務的 `docs/agent-runs/kuro-original-web-cutover-20261010/Plan.md`；
3. 經差異、安全掃描確認且必要的獨立 preview host / protocol / harness 測試與使用說明（明確列舉，避免整個 devtools 證據目錄全納入）。

**禁止**混入之前 412 項 WIP 的既有 Core/Qt/Conversation/Pet 修改、未驗收 migration、私人資料、環境檔、logs、DB、mail/history/memory/model/voice、依賴、build、巨型 WIP/測試 receipt 或任何未知檔。嚴禁 `git add .`、`git add -A`、`reset`、`stash`、`clean`、`restore`。commit 前查看**實際 staged files、staged diff、秘密／二進位／巨大檔案掃描**；HEAD 沒有非預期更新才 commit，不 push（使用者尚未要求）。

**基準語意**：這一筆是「**原始前端 UI 可回到的 Git 錨點**」，不是整個 Kuro dirty worktree 的可重現運作快照；後者仍需另行工程盤點／獨立 checkpoint。最終回報 exact commit SHA 與 stage 清單，以及保留多少 WIP 未提交。

## 2. Ownership 與前端能力回收對照

| UI 能力 | 正式資料／行為 owner | 原始 renderer method | 最終 transport / 策略 |
| --- | --- | --- | --- |
| Shell / Chat / Today / Settings / Window actions | Qt window、Work Companion Web presentation | `renderShell / bindShell / renderActiveView` | 單個 Qt WebEngine，Qt tray／second-launch，不重建 Electron app |
| Chat 串流、送出、interrupt、tool timeline | `QtRuntimeChatClient` → qt-primary WS → Conversation Runtime | `getChatState / sendText / onChatState / renderChat` | Qt 原有 client 唯一握 WS；WebChannel 單向事件投影及受控 UI command |
| History CRUD、active conversation、草稿、stale fence | Conversation Runtime、Qt Client | `renderHistoryDrawer / getHistories / createHistory / selectHistory / deleteHistory` | 不讀本機 history JSON；原有 request ID／conf UID／context/revision／timeout／native delete confirmation |
| 角色、專案、模型、Thinking | `QtLauncherController`／profile config／Runtime | `getProfile / applyProfile / populateChatControls / settingsAssistantGroup` | 先 confirm、再 apply、最後核對 runtime effective state；取消／失敗 rollback UI selection |
| Memory、tools、policy | Character Memory manager、ToolPolicy manager | `getMemories / memoryAction / getTools` | digest + conf fencing；需要寫入確認；工具 confirm 尚不完整必須 disabled，不能因新按鈕放行 |
| 麥克風、鏡頭、畫面擷取 | Pet capture + Qt conversation submit | `handleMicrophonePrimary / toggleSensor / settingsPerceptionGroup` | Pet 只 capture，Qt 決定綁定 history 後送出；無裝置可用時顯示 unsupported，不得假成功 |
| 服裝、表情、動作、Pet 狀態 | Electron pet-local :23567 via existing controller | `settingsPetGroup` | 使用既有 Pet gateway；不可重建 Electron app control server |
| Today、來源 status、work/attention、detail | Core `/v1/today` | `renderToday / renderPriorityBlock / renderSourcesBlock / renderDetail` | Core 投影唯一來源；保留 source/time/freshness/limitations；禁止 UI 自行重新排名或回源補資料 |
| Schedule、notifications、quiet hours | Core Schedule API/Store + QtScheduleDelivery | `schedule.ts`、`schedule(...)` | prepare → native confirm → mutate → revision/idempotency；通知由 Qt tray claim→authorize→ack |
| Mail refresh、Mail body、Study jump | 各原系統與正式 Core handoff | `refreshMail / loadMailDetail / Today detail` | **目前是 GAP/LEGACY，不得為了按鈕直接接回舊 provider/IPC**；先確認 canonical owner contract，再加 affordance |
| 診斷與 lifecycle、source health | Qt Launcher / Core / Pet owner | `settingsRuntimeGroup / settingsSourceGroup` | status 的真實 source identity；stop/restart 要 confirmation；共享中央 TTS 不受 Qt stop 誤傷 |
| UI 本地偏好與 History drawer 狀態 | Qt QSettings 或明確允許的 presentation-only local state | `localStorage` preferences、settings sections | 選擇**一個** prefs owner；不能形成 Qt QSettings／localStorage 雙真相。禁止 token/PII 被 Web Storage 保存 |

待下一輪的 source audit 給每條標示 `Source present / Adapter mapped / Live proven / Retired`，每個方法都要有 action/error response contract、必要的 test 和可回退方案，不能只說「接線成功」。

## 3. 分階段 Gate（每 Gate reviewer 通過才往下）

### Gate W0 — UI baseline & repo hygiene（本輪範圍）

1. 讀 repo／AGENTS、四份 product doc、先前 G8 與 Git parity matrix。
2. 固定來源 Git SHA／6 個原版 source SHA，不修改 original renderer source。
3. 完成此計畫與 scoped local commit；執行 TypeScript typecheck、Vite build、synthetic adapter tests。
4. 保存 commit SHA、staged paths、excluded WIP、是否 staged/untracked drift。**不切換正式程序**。

**PASS**：可從該 commit 還原相同 original UI source/build；沒有新舊 production 雙前端，也沒有 secrets。

### Gate W1 — WebEngine dependency & same-source 視覺驗收

- 在**隔離** Python env 使用匹配版本的 Qt WebEngine/Qt WebChannel；真實 import + load + render + resource/security checks。缺模組或 GPU/OS 問題要 BLOCKED，不暗中關 sandbox 或改正式 venv。
- Browser baseline 與 Qt Host 使用**同一份 Git UI、相同 synthetic fixture、view、viewport、DPI**，測 1280×720、1380×860，至少 100%/125%/200% DPI；Chat、Settings、History、Today/Schedule。
- 保存每個窗口 DOM rect、CSS variables、字型、overflow、PNG、pixel diff／MAE／RMS、人工視覺 reviewer 判決。使用者先前對瀏覽器預覽的肯定作為 visual target，但不能替代 Qt Host screenshot。

**Stop**：任何 Qt WebEngine render/安全初始化問題，不碰正式 Launcher。

### Gate W2 — 唯一 Qt Web Host 與 Bridge contract

- 製作受控 `QWebEngineView + QWebChannel`，預設離線、本地資源 allowlist、禁任意網路／導航／下載、無 Node／Electron bridge。
- 在 `main.ts` import **之前**注入 typed `window.kuroWorkPanel` adapter；正式執行時不得使用 silent `fallbackBridge` 假成功。
- 一個 Qt window/tray/mutex；WebView 只有 UI 指令轉發權限，要求 request ID、expected actor/history/context/revision、schema/value bounds、timeout、busy/error/unknown、no retry-on-uncertain。
- 暫保留舊 Qt Widgets 僅作 rollback，但不能同時實際掛兩個 qt-primary WS 或 Core notifier。
- W1 過後再做 production worktree cutover；原始 Git 六檔與第一個 commit 仍是不可改的基準，所有改動留可審計 diff。

### Gate W3 — Chat / History（最高優先）

- 測真實一條 qt-primary WS：connect/reconnect、文字串流、tool timeline、interrupt、角色切換、延遲／重複／過期訊息、輸入草稿、附件 size/MIME/type、IME Enter / Shift+Enter。
- History list/search/new/select/delete；identity fence、刪除 confirmation、未知結局不自動重送；工具事件不可當 assistant 回覆。
- 不讀寫 private history 作 automated fixture；synthetic／disposable history 測試後，正式 live 人工驗收分開。

### Gate W4 — Settings / Memory / Tool Policy / Pet & Perception

- 原版 Settings 六分類完整對接：角色／專案／模型／推理、長期記憶／審核／停用／刪除／整理、工具政策與狀態、感知、Pet、診斷。
- 優先沿用 Qt 現有 controller/confirm/quality gates，不新增各自的 manager。
- Memory 260 vs 舊 UI 1200 字等規格差異單獨決策，不為一致性偷繞後端限制。Tool confirm 缺佇列維持 disabled＋可解釋。
- 相機、麥克風、螢幕／語音／多螢幕 pet controls 必須實際桌面驗收，不能只看無例外回傳。

### Gate W5 — Core Today / Schedule / Mail / Study / Notification

- Today 必須從 Core canonical projection 取資料，保留 source statuses、時間戳與 limitations；不從 `model.ts` 建第二套 priority、分類或 provider fallback。
- Schedule、提醒、quiet hours、claim/authorize/ack 全部走現有 Core/Qt owner；資料寫入需 expectedRevision、idempotency、confirmation。
- 原版 UI 所需但現在無 canonical owner 的 Mail body／手動刷新／Study jump 做明確 `GAP`，先定對外 contract 才實作；無法安全接線要 disabled。
- 新增操作按鈕以 frontend skills 審核、保留原版色彩/spacing，空狀態／partial/stale/busy/error／tooltip／鍵盤導航一併設計；可在不破壞原生版型的位置新增小型 UI affordance。

### Gate W6 — Legacy deletion / 單一 UI 收斂

- W1–W5 經實測 PASS 後，先查 import graph、event handler、renderer entry、routes、tests、config、generated assets，再精確移除不再可達的 **Qt Widgets presentation**：候選如 `qt_work_companion_view.py`、`qt_work_companion_theme.py`、`qt_app.py` 中舊 Chat/Settings page builder 與多餘 QSS；`qt_core_pages.py` 內 presentation 可清，但 canonical controller/service API 不可隨便刪。
- 舊 Electron WorkPanel/Reader/Briefing 應維持 G7 35/35 不可達／已刪，**不得為了搬回原版 HTML 而連它們的 IPC/business owner 一起復活**。
- 清除 temporary opt-in preview entry、重複 Web renderer/Widget render path、fallback 和 stale config。原始 Git UI baseline 維持在有明確標識的 source reference，不成第二個 production entry。
- 檢查 GET/read-only 不偷偷寫 DB／refresh；無雙 history owner、schedule producer、notification delivery、thread、tray 或 WebSocket。

### Gate W7 — G8 正式 Windows 驗收與封版

- 從桌面原 VBS 啟動，新 Qt Web UI 第一屏是原版 Work Companion；確認 second launch 喚回同視窗、X→Qt tray、Quit、relaunch，沒有再看到 Kuro Desktop Console。
- 實測 Live2D／Pet absence、Chat、History、Memory、Tools、Today／Schedule／Mail／Study、mic/camera/screen、音效／中央 Voice、multi-display 與 Windows 通知。
- 程式與畫面獨立回歸：前端 typecheck/build、Qt／Conversation／Core targeted tests、Pet-only Node tests、G7 absence、後端 error/timeout tests、formal runtime API/WS，來源 freshness/品質顯示。
- 阻塞缺陷／重複 owner／不完整 identity/side effects／死路徑／視覺回歸，一律不得封版。剩餘缺口以 Confirmed Defect／Architecture Risk／Legacy Debt／Unverified 分級，接受才可下一個 release commit。

## 4. 本次與後續禁止事項

- 目前任務只做計畫＋scoped local commit，不進入 W1–W7 的 production 實作，不重啟 Kuro／Core／Conversation／Pet／中央語音。
- 不將 preview 的 synthetic Data Bridge 或 legacy `model.ts` Today 計算直接當 backend 來源；不在 UI 直接接 Gmail/OMI/provider，也不在 WebEngine 暴露 Controller 全方法。
- 不一次刪掉舊 Qt Widget、Core/Conversation、G7 evidence；不能因 tests PASS 便宣稱 UI release PASS。
- 不 stage 全 repo／偷偷改私有設定、執行遠端 API／測實際 LLM、commit/push 沒經使用者指定的其他改動。
- rollback 優先回上一筆 scoped frontend baseline + 先前仍可用 Qt host，不能使用整庫 reset／clean 覆寫大量先前 dirty changes。

## 5. 下一輪作業順序與驗收表

**本輪交付**：計畫文件、source manifest、完整 staged diff 審計紀錄、**一筆 local Git commit SHA**、未提交 WIP 範圍、git status。**不 push**。

**下一輪首要工作**：W1 真實 WebEngine render／視覺同源驗收，接著 W2 建立正式 Qt Host/Bridge；只要 W1 blocked，不開始正式 UI 替換。

### 可量測 Done 條件

- 同一 Git original UI source 的 source SHA 被追蹤；使用者目標截圖與 Qt Host 的 Chat/Settings geometry、內容層級與控制元件互動可證高度一致；新增按鈕有設計系統與 review。
- 正式 UI path 只有 Qt Web Host；Qt-primary WS、Core Today、Schedule、Memory、Policy、Pet、通知、權限與持久化皆能追到單一 owner。
- 舊 Qt Widgets 與 Electron WorkPanel 兩套舊 application UI 在 production 上沒有可達 fallback；凡保留 legacy 必標不可達與刪除時點。
- 具有 fixture 與正式 runtime 的驗證證據，使用者人工可核對；無 silent success、資料變空、重複請求／重複寫入、stale/partial 資訊遺失。


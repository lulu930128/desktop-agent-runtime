# Kuro AGENTS.md

本檔是 Kuro repo-level agent instructions。它放在 repo root，並繼承全域 `~\.codex\AGENTS.md` 與 `C:\project\AGENTS.md` 的基本工作準則。
使用者可見的 Codex 回覆、交付摘要與固定欄位標題預設使用繁體中文。日文只用於角色語音、spoken rendering、i18n、原始文案或使用者明確要求；不要因為 Kuro 有日文語音/角色內容，就把專案問答改成日文或英文。

## 專案定位

Kuro 是 local-first desktop AI companion runtime，但長期目標不是單純聊天角色或展示 demo。

產品方向：

- Kuro 是可展示的桌寵助理，核心是工作助理能力。
- Live2D、語音、角色人格、Reader、Briefing、任務牆與桌面常駐體驗，是提升展示與使用體驗的互動層。
- Kuro 應能透過工具告訴使用者「該注意什麼、該做什麼、哪裡有狀況」，而不是只陪聊。
- 不同角色可以有不同聲音、人格、語氣與展示方式，但不能破壞工具權限、記憶邊界與 runtime 穩定性。

## 最終產品文件

`docs/product/` 是 Kuro 的長期產品方向文件區。非平凡功能、產品判斷、重大 UI/runtime/tool/memory 邊界調整開始前，若下列文件已有使用者填寫內容，要先讀取並對齊：

- `docs/product/ProductVision.md`
- `docs/product/OperatingModel.md`
- `docs/product/QualityBar.md`
- `docs/product/Roadmap.md`

空白模板不是產品事實。若文件仍未填寫，以本 `AGENTS.md`、既有程式與使用者當次需求為準；若當次需求和已填寫產品方向衝突，先反駁並提出較穩定方案。

## 方向保護與反駁責任

- 如果需求把 Kuro 做成只有聊天、陪伴或角色表演，必須提醒這會偏離「工作助理」核心。
- 如果需求把 domain logic 塞進角色 prompt，例如市場分析、郵件判斷、行程規劃、資料刷新策略，必須反駁。角色 prompt 不是核心業務邏輯層。
- 如果需求讓 Live2D / Electron 展示層承擔 tool orchestration、market logic、memory policy 或資料真相來源，必須反駁。
- 如果需求要求 Kuro 繞過 tool policy、直接修改外部系統、發送訊息、刪除資料、發布內容、改 repo、或消耗大量 quota，必須先要求確認或提出安全替代方案。
- 如果需求會把 private runtime state、角色記憶、語音素材、模型權重、log、chat history 或 secrets 放進 git，必須拒絕。

## 架構邊界

- `launcher_qt.py` 是目前 Qt desktop console，負責啟動 profile、服務 orchestration、chat、Briefing、memory、pet shell 控制。
- `kuro_launcher/` 負責 config parsing、service helpers、runtime config generation、memory panel 與 records。
- `kuro_launcher.settings.yaml` 是本機 runtime source of truth：paths、ports、LLM env names、startup profile。
- `Open-LLM-VTuber/` 負責 conversation runtime、prompt composition、tool integration、WebSocket protocol 與 memory system。
- `pet-electron/` 負責 Live2D desktop shell、Reader、Briefing、tray、local control server 與 Electron window behavior。
- `bridges/` 負責 bridge service、translation 與 spoken rendering integration。
- 舊 `gpt_sovits/` 已比對並移除；保存對照位於中央語音工作區的 `inventory/legacy-gpt-sovits-20260912/manifest.json`。中央語音服務擁有模型與推論；consumer 不得停止共用服務。
- `projects/` 放 project prompt packs 與 assistant context definitions。

展示層可以呈現、提醒、收集操作與播報；domain tool 與外部資料專案才是資料/分析真相來源。

## Tool Policy

Kuro 可以具備工具操作能力，但必須分級。

預設可自動執行：

- 讀取型狀態檢查，例如 local status、Briefing snapshot、OMI read-only result。
- 本機 dashboard / task wall / Reader / Briefing 的呈現更新。
- 安全的摘要、分類、重排與格式轉換。

預設需要確認：

- 寫入長期記憶或刪改既有記憶。
- 發送 email、message、社群貼文或任何對外內容。
- 刪除、移動或覆蓋使用者資料。
- 修改 repo、commit、push、改設定、改啟動捷徑。
- 觸發外部 API 大量刷新、付費 quota、LLM report generation 或長時間背景工作。
- 任何可能影響 OMI 市場資料、Kuro memory、private docs、tool policy 或使用者工作流的操作。

目前政策是：寫入、刪除、發送、發布、以及會消耗大量 quota 的動作都必須先確認。等工具政策與審計能力完善後，再逐項放寬。

如果 tool policy 已經有更明確的 allow/deny 規則，優先遵守 tool policy。不要在 prompt 或 UI 裡繞過 policy。

## OMI 整合

- Kuro 不直接承擔市場資料與交易決策邏輯。
- Kuro 可以向 OMI 提出需求，例如「產生今日市場分析」、「整理某檔股票技術決策稿」、「找出需要注意的自選股」。
- OMI 必須用自己的資料、freshness、tool、AI decision core 產出結構化結果。
- Kuro 負責把 OMI 結果轉成 Reader、Briefing、任務牆或語音播報，不應在 Kuro 端重新判斷市場。
- 如果 OMI 回傳 stale、partial、missing 或 provider failure，Kuro 要保留這些警告，不得把不完整資料講成確定結論。

## 記憶策略

使用者希望記憶不要過度保守，但必須可審計、可修改、可刪除。

記憶應分層：

- 角色記憶：人格、偏好、長期互動設定。
- 工作記憶：使用者工作習慣、常用專案、常用工具與流程。
- Briefing snapshot：每日狀態、任務牆、信件、學習、市場與其他短期摘要。
- Tool result：外部工具結果、查詢證據、一次性分析輸出。

不要把每日 briefing、工具結果、暫時市場狀態或噪音自動升級成角色長期記憶。若自動寫入，必須能追蹤來源、時間、類型與刪改方式。

## 語音、人格與展示品質

- 語音輸出與角色人格是對外展示核心品質，不可視為可隨意破壞的附屬功能。
- 不同角色可以有不同語音、人格、語氣與情緒呈現。
- Spoken output 應配合角色與情境：重要狀態要簡潔，長報告要轉成可聽的摘要，不要照讀大段文字。
- 繁中內容、日文 spoken rendering、情緒、簡報式輸出與 Reader/Briefing 分工都屬於展示 contract。修改時要避免回歸成雜亂口播。
- 如果改動影響 TTS、bridge、spoken report、字幕或 Reader/Briefing，需要跑對應 smoke test 或至少做 syntax/build check。

## Runtime 與 Port

預設 local ports 來自 `kuro_launcher.settings.yaml`：

- Bridge: `127.0.0.1:1188`
- Central TTS: `127.0.0.1:18890`（`9981` 僅供 legacy 回退；`18790` 已由 japanese-study-mcp 使用）
- LLM runtime: `127.0.0.1:23456`
- Pet control: `127.0.0.1:23567`
- Launcher control: `127.0.0.1:23568`（工作面板 IPC proxy 專用；session token 不得進 renderer 或 git）

不要恢復舊的 `9881` TTS port；該 port 可能落入 Windows reserved TCP range。遇到 startup 失敗時，先檢查目前設定、launcher log、stale shortcuts、舊 root path 與 port listener。

## Private / Local State

不得 commit：

- `.env`, `.env.local`
- API keys、tokens、cookies、credentials
- `open_ai_api.txt`
- `launcher_logs/`
- generated runtime config
- chat history and memory data
- Electron `userData`
- model weights
- private voice references
- `pet-electron/node_modules/`
- `pet-electron/renderer-dist/`
- `pet-electron/.tmp/`
- Python virtual environments under `envs/`

可以 commit：

- source code
- launcher/runtime helpers
- prompt/config templates
- safe character/project metadata
- documentation
- README screenshots
- placeholder configs

## 修改前檢查

修改前先判斷改動屬於：

- launcher / Qt UI
- runtime config generation
- Open-LLM-VTuber prompt/tool/memory
- Electron pet shell / Reader / Briefing
- bridge / spoken rendering / TTS
- project prompt pack
- docs / README / screenshots

不要在未確認邊界時跨層改動。特別是不要用角色 prompt 修補本該由 tool policy、runtime service、backend API 或 Electron control server 解決的問題。

## 驗證命令

依修改範圍執行最相關檢查。

驗證預算：

- 只改 docs、prompt、AGENTS、模板：UTF-8 讀回與 `git diff --check` 即可；不要啟動 GUI、LLM runtime、TTS 或 Electron。
- 只改文案、label、i18n、角色描述或小型 spoken wording：做相關字串搜尋與 diff 檢查；除非改到可編譯檔案，否則不要跑全套。
- 改 launcher、runtime config 或 Python 局部邏輯：跑對應 py_compile 或 targeted tests。
- 改 tool policy、memory、OMI integration、Briefing snapshot、Reader 或外部 side effect 邊界：跑相關 policy/unit/smoke 檢查。
- 改 Electron main/renderer、Live2D、Reader/Briefing UI 或可視體驗：依風險跑 node check、renderer check/build；只有需要驗證實際 UI 時才啟動 runtime 或做 screenshot。
- 發送/發布、刪除資料、寫入長期記憶、修改 repo、消耗大量 quota 或外部 API 寫入：先確認，再驗證。

Python syntax checks：

```powershell
cd "C:\project\desktop-agent-runtime"
.\envs\kuro-llm310\python.exe -m py_compile .\launcher_qt.py .\kuro_launcher\qt_app.py .\kuro_launcher\qt_controller.py .\kuro_launcher\qt_chat_client.py
```

Electron main-process checks：

```powershell
cd "C:\project\desktop-agent-runtime"
node --check .\pet-electron\src\main.js
node --check .\pet-electron\src\state.js
node --check .\pet-electron\src\main-process\control-server.js
node --check .\pet-electron\src\main-process\briefing-store.js
node --check .\pet-electron\src\briefing-preload.js
```

Renderer checks：

```powershell
cd "C:\project\desktop-agent-runtime\pet-electron"
npm run check:renderer
npm run build:renderer
```

Runtime smoke checks when the pet shell is running：

```powershell
Invoke-RestMethod http://127.0.0.1:23567/status
Invoke-RestMethod http://127.0.0.1:23567/briefing
```

若無法啟動 GUI 或 runtime，至少執行可行的 syntax/build 檢查，並清楚說明未驗證的互動層風險。

## Git Hygiene

- 使用者沒有明確要求時，不要 commit 或 push。
- commit 前檢查 staged diff，確保沒有 private state、log、model、voice、memory、runtime config 或 dependency output。
- Kuro 是本機 runtime workspace；很多重要資料只應留在本機，不應成為 repo 內容。

## Project Subagents

本 repo 提供 read-only custom subagents，只有在使用者明確要求 subagents、parallel review 或指定 agent 名稱時才使用；不要自動啟動。

- `kuro-runtime-boundary-reviewer`：審查 launcher、Open-LLM-VTuber runtime、Electron pet shell、Reader/Briefing、ports、startup 與 private runtime boundary。
- `kuro-tool-memory-reviewer`：審查 tool policy、memory strategy、OMI integration、briefing snapshots、spoken output、character/persona contract 與寫入確認邊界。

這些 subagents 預設用於讀取、探索、審查與回報 findings。除非 parent task 明確要求它們實作局部修正，否則不應修改檔案。
## 長任務文件

大型任務可建立：

- `docs/agent-runs/<task>/Prompt.md`
- `docs/agent-runs/<task>/Plan.md`
- `docs/agent-runs/<task>/Progress.md`

這些檔案應記錄目標、限制、milestone、驗證與決策。不要把單次任務的進度塞進 repo root `AGENTS.md`。

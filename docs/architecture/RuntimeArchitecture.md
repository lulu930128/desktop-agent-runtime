# Kuro 現況架構

本頁保留原 README 的元件地圖、設定與資料流。描述 source 現況，不代表正式 runtime 已完成驗收；目標架構見 [Operating Model](../product/OperatingModel.md)。

## 系統全貌

```mermaid
flowchart LR
    User["使用者"] --> WorkPanel["Electron 工作面板<br/>對話 / Today / 設定"]
    User --> PetUI["Electron 桌寵<br/>Live2D"]
    Console["Qt orchestrator<br/>launcher_qt.py"] --> WorkPanel

    Settings["kuro_launcher.settings.yaml<br/>路徑、port、startup profile"] --> Console
    Env[".env / .env.local<br/>secrets 與 provider 設定"] --> Console
    Character["characters/*.yaml<br/>角色、模型、TTS 設定"] --> RuntimeBuilder["runtime config builder"]
    Project["projects/*<br/>工作情境與 prompts"] --> RuntimeBuilder
    Console --> RuntimeBuilder
    RuntimeBuilder --> Generated["conf.launcher_runtime.yaml<br/>產生檔，不進 git"]

    Console --> Bridge["Bridge :1188<br/>翻譯與 spoken rendering"]
    Console -.->|"連接與驗證，不管理生命週期"| TTS["Central Voice :18890<br/>語音合成"]
    Console --> Runtime["Open-LLM-VTuber :23456<br/>conversation runtime"]
    Console --> PetMain["Electron main process<br/>pet control :23567"]
    Console --> LauncherControl["Launcher control :23568<br/>session token + confirmed writes"]
    LauncherControl --> PetMain

    Console <-->|"/client-ws"| Runtime
    PetUI <-->|"WebSocket 對話、音訊與控制事件"| Runtime
    Runtime --> Bridge
    Runtime --> TTS

    Runtime --> Tools["Tool catalog + policy + MCP"]
    Tools --> Domain["外部 domain systems<br/>OMI / mail / future adapters"]
    Domain --> Tools

    Console <-->|"HTTP status / command"| PetMain
    PetMain --> BriefingStore["Briefing store<br/>snapshot + memory candidates"]
    BriefingStore --> PetUI
```

### 一次啟動實際發生的事情

1. `launcher_qt.py` 依序載入 `.env`、`.env.local` 與 `kuro_launcher.settings.yaml`。
2. 使用者選擇 character、project、outfit 與 thinking power。
3. `kuro_launcher/runtime_conf.py` 合併基礎設定、角色設定與 project prompt，產生
   `Open-LLM-VTuber/conf.launcher_runtime.yaml`。
4. Launcher 先啟動或沿用具備正確 service identity 的 Electron 桌寵殼，讓工作面板不必等待 LLM／TTS readiness 就能顯示。
5. Launcher 啟動或沿用 Bridge，連接獨立中央語音服務，並用一小段真實音訊請求確認 TTS 可用；接著啟動 Open-LLM-VTuber。
6. Qt chat client 與 Electron frontend 在 LLM runtime ready 後各自連到 `/client-ws`；服務尚未 ready 時，工作面板保留可見並呈現各自狀態。
7. Pet control server 提供帶有 service、protocol、PID 與 instance identity 的本機狀態與操作 API；Launcher 只會沿用或停止可驗證身分的 Pet shell。
8. Launcher 以每次啟動產生的臨時 token，讓 Electron main process 透過 `:23568` 讀取 profile、history、memory 與 tool policy；renderer 不會取得 token，寫入前仍須經 Electron 原生確認視窗。

`QtLauncherController` 也支援在條件允許時 hot switch profile；中央模式會驗證 voice，模型切換由中央服務處理，不重啟共用 TTS。

## 元件責任地圖

### Launcher 與 Qt 控制台

| 路徑 | 現在負責什麼 |
| --- | --- |
| `launcher_qt.py` | Windows AppUserModelID、env 載入、Qt application 與主視窗入口。 |
| `kuro_launcher/qt_app.py` | Qt Widgets 畫面、頁面、按鈕、狀態呈現與使用者事件。 |
| `kuro_launcher/qt_controller.py` | Profile orchestration、服務生命週期、狀態 probe、chat/history/memory/Briefing 操作、Electron commands。 |
| `kuro_launcher/qt_chat_client.py` | Launcher 與 Open-LLM-VTuber `/client-ws` 之間的 WebSocket client。 |
| `kuro_launcher/config.py` | 解析 `kuro_launcher.settings.yaml`、展開路徑與建立 typed `AppConfig`。 |
| `kuro_launcher/runtime_conf.py` | 合併 base、character、project 與 runtime override，寫出 generated runtime config。 |
| `kuro_launcher/work_panel_api.py` | Loopback-only 工作面板 contract；提供受 session token 保護的 profile、history、memory 與 tool policy API。 |
| `kuro_launcher/services.py` | Bridge、TTS、LLM 子程序啟動、資產驗證與 readiness probe。 |
| `kuro_launcher/procs.py` | 子程序與 stdout/stderr log 管理。 |
| `kuro_launcher/project_manager.py` | 掃描與驗證 `projects/*/project.yaml`。 |
| `kuro_launcher/memory_*.py` | 控制台記憶列表、分類、核准、停用、刪除與 compact 操作。 |

Launcher 是 **runtime operator**，不是 conversation、market、mail 或 memory database 的資料真相來源。

### Open-LLM-VTuber conversation runtime

`Open-LLM-VTuber/` 是對話與工具執行核心。目前 Kuro 使用的是 repo 內的 fork／客製版本，
Launcher 啟動時會把 `Open-LLM-VTuber/src` 放在 `PYTHONPATH` 前方，避免誤載到舊的 site-packages 版本。

| 區域 | 現在負責什麼 |
| --- | --- |
| `src/open_llm_vtuber/routes.py` | `/client-ws`、launcher profile/history API、ASR 與 TTS WebSocket routes。 |
| `src/open_llm_vtuber/websocket_handler.py` | Client session、訊息 routing、history 操作、heartbeat 與 group 狀態。 |
| `src/open_llm_vtuber/conversations/` | 一次 conversation turn 的輸入、模型、tool 與輸出流程。 |
| `src/open_llm_vtuber/agent/` | Agent、prompt composition、memory context 與模型互動。 |
| `src/open_llm_vtuber/mcpp/` | MCP registry/client、tool adapter、catalog ranking、policy enforcement 與市場 preflight。 |
| `src/open_llm_vtuber/tts/` | TTS provider adapter 與合成請求。 |
| `src/open_llm_vtuber/translate/` | 翻譯／spoken rendering provider adapter。 |
| `tool_catalog.json` | 工具有哪些能力、分類與 routing metadata。 |
| `tool_policy.json` | 哪些工具與參數可執行，以及 read/write、quota、report 等限制。 |
| `characters/*.yaml` | 角色 persona、Live2D、TTS、語音與角色層設定。 |

角色 prompt 只能定義人格與表達方式；不能用來取代 tool policy、資料 freshness、寄信規則、
市場判斷或其他 domain logic。

### Project prompt packs

`projects/` 描述角色目前工作的情境，而不是新增另一個 runtime。

```text
projects/
├─ desktop-agent-runtime/
│  ├─ project.yaml
│  └─ prompts/
└─ casual-chat/
   ├─ project.yaml
   └─ prompts/
```

每個 `project.yaml` 連到三類可選 prompt：

- `project_prompt`：專案背景、目標與工作情境。
- `tool_prompt`：這個情境下如何選擇與使用工具。
- `response_style_prompt`：輸出格式與語氣規則。

Project pack 可以改變工作上下文，但不應直接持有 secret、啟動服務或實作 domain adapter。

### Bridge 與 spoken output

`bridges/deeplx_bridge.py` 是本機 FastAPI bridge。名稱保留了早期 DeepLX 歷史，
目前實際責任包含：

- `POST /translate`：翻譯成適合角色 TTS 的日文。
- `POST /translate_debug`：翻譯診斷。
- `POST /render_spoken`：把完整可見回答整理成較短、可自然播報的日文與 emotion。
- OpenAI 為主要 rendering provider，可依設定使用 Ollama 或 DeepLX fallback。
- 過濾 JSON、code、URL、路徑與不適合直接朗讀的內容。

Bridge 只負責 **輸出轉換**。它不能改寫工具結果的事實、補上不存在的證據或重新做市場判斷。

`local_translator/server.py` 是較單純的 Ollama 翻譯服務；它不是 Launcher 目前預設啟動的主 Bridge。

### GPT-SoVITS

舊 `gpt_sovits/` 已完成 SHA-256 比對並清除；音檔、模型與訓練資料保存在中央語音工作區。正式設定使用獨立中央 Voice Runtime，
由中央 package 擁有模型與 reference；Launcher 在 LLM runtime 啟動前執行實際 TTS smoke request。
啟動方式、角色映射與舊資料保存紀錄見 [中央語音服務](../central-voice-runtime.md)。

模型權重、pretrained models、角色 reference audio 與產生音訊都屬於 local/private state，不能進 git。

### Electron 桌寵殼

`pet-electron/` 是 Kuro 自己的桌面 shell，不是資料分析 backend。

| 路徑 | 現在負責什麼 |
| --- | --- |
| `src/main.js` | Electron main process、視窗、tray、IPC、backend wiring 與生命週期。 |
| `src/state.js` | 視窗 bounds、visibility 等 shell state。 |
| `src/main-process/control-server.js` | `127.0.0.1:23567` 的本機 HTTP status、Briefing 與 command API。 |
| `src/main-process/menus.js` | Tray 與桌寵右鍵選單。 |
| `src/main-process/briefing-store.js` | Briefing snapshot、source status 與 memory candidate 的正規化及持久化。 |
| `src/main-process/mail-briefing-service.js` | 目前的 mail poller、preferences、rules、message read 與 refresh 整合。 |
| `src/main-process/study-briefing.js` | 讀取並合併 local study snapshot。 |
| `src/main-process/reader-attachments.js` | Reader 附件分類、大小限制與 payload 正規化。 |
| `src/reader-window.html` | Reader 視窗。 |
| `src/briefing-window.html` | Briefing dashboard 視窗。 |
| `renderer/` | TypeScript/Vite Live2D renderer、backend adapter、互動與音訊控制。 |
| `vendor/CubismWebFramework/` | Electron renderer 使用的 Cubism framework source。 |

Electron runtime state 存在 Electron `userData`，不放在 repo：

```text
pet-shell-state.json
briefing-store.json
pet-shell.log
```

### 外部工具與 domain systems

Kuro 可以呼叫工具，但不應把每個領域的商業邏輯搬進自己。

```text
使用者問題
  -> Open-LLM-VTuber tool catalog
  -> tool policy 與參數檢查
  -> MCP / local adapter
  -> domain system
  -> 結構化結果與限制
  -> Kuro 顯示、摘要或播報
```

市場能力目前由 Open Market Intelligence（OMI）負責。Kuro 的 market preflight 消費
`omi.decision.v4` 的 `answer`、`decision`、`evidence`、`limitations`、`status` 與
`continuation`，但 freshness、provider fallback、證據與市場語意仍由 OMI 決定。

同樣的原則也適用於 mail、calendar、news、messages 與未來 adapters：
Kuro 負責 orchestration 與 presentation，domain service 負責資料真相與寫入規則。

## 三條主要資料流

### 對話、畫面與語音

```mermaid
flowchart LR
    Input["使用者輸入"] --> Runtime["Conversation runtime"]
    Runtime --> Prompt["character + project + memory + tool context"]
    Prompt --> Model["LLM response"]
    Model --> Visible["繁中可見回答"]
    Model --> Spoken["Bridge spoken rendering"]
    Spoken --> TTS["GPT-SoVITS 音訊"]
    Visible --> Client["Qt / Reader / Pet"]
    TTS --> Client
    Client --> Complete["playback complete / turn finalize"]
```

可見文字、語音文字、emotion 與 Live2D action 是不同輸出 lane。長報告保留在畫面，
語音只播報結論、風險與下一步，不直接朗讀 URL、code 或完整診斷內容。

### Tool request

```mermaid
flowchart LR
    Ask["使用者需求"] --> Catalog["Catalog routing"]
    Catalog --> Policy["Policy guard"]
    Policy --> Tool["MCP / local tool"]
    Tool --> Domain["Domain owner"]
    Domain --> Result["結果 + status + limits + evidence"]
    Result --> Answer["Kuro 回答／Briefing"]
```

任何 write、delete、send、publish、長期記憶寫入或大量 quota 操作，預設都要先取得使用者確認。

### Briefing 與記憶

```mermaid
flowchart LR
    Adapter["Tool / adapter snapshot"] --> Snapshot["今日 Briefing snapshot"]
    Snapshot --> Dashboard["Briefing UI"]
    Snapshot --> Candidate["可選的 memory candidate"]
    Candidate --> Review["使用者核准／拒絕"]
    Review --> LongTerm["角色長期記憶"]
```

Briefing 是短期狀態；長期記憶只保存穩定偏好、背景與持續有效的工作資訊。
工具結果、每日信件、市場變化與暫時任務不能自動污染角色記憶。

## 設定與資料真相來源

| 類型 | 真相來源 | 說明 |
| --- | --- | --- |
| Repo 路徑、port、startup profile | `kuro_launcher.settings.yaml` | Launcher 的 canonical runtime 設定。 |
| Secrets、provider、model override | `.env`、`.env.local`、OS environment | `.env.local` 後載入，可覆蓋 `.env`；兩者都不能 commit。 |
| 角色設定 | `Open-LLM-VTuber/characters/*.yaml` | Persona、Live2D、TTS 與角色層設定。 |
| 專案情境 | `projects/*/project.yaml` 與 `prompts/` | 工作 context、tool guidance 與 response style。 |
| 執行中設定 | `Open-LLM-VTuber/conf.launcher_runtime.yaml` | Launcher 產生；不要手動維護或 commit。 |
| Tool routing / permission | `tool_catalog.json`、`tool_policy.json` | 能力描述與執行限制；不是 domain data。 |
| Chat history | `Open-LLM-VTuber/chat_history/` | Local-only conversation state。 |
| Character memory | `Open-LLM-VTuber/memories/` | Local-only、可審核的長期記憶。 |
| Pet / Briefing state | Electron `userData` | 視窗狀態、Briefing store 與 pet log。 |
| 市場資料與判斷 | OMI | Kuro 不重算或硬編碼。 |
| Runtime logs | `launcher_logs/` 與 Electron `userData` | 診斷用 local state，不進 git。 |

## 預設本機 port

| Service | 位址 | 用途 |
| --- | --- | --- |
| Bridge | `127.0.0.1:1188` | `/translate`、`/translate_debug`、`/render_spoken`。 |
| Central Voice Runtime | `127.0.0.1:18890` | `/health`、`/voices`、`POST /tts`。 |
| Open-LLM-VTuber | `127.0.0.1:23456` | HTTP、launcher API 與 `/client-ws`。 |
| Pet control | `127.0.0.1:23567` | `/status`、`/briefing`、`/command` 等本機控制 API。 |
| Launcher control | `127.0.0.1:23568` | 工作面板的 profile、history、memory 與 tool policy 窄 contract；只接受本次啟動的 Electron session token。 |

所有預設服務都只綁定 loopback。不要把這些 API 直接暴露到 LAN 或 Internet。

> 中央 TTS 使用 `18890`；`9981` 僅供 legacy 回退。不要恢復舊的 `9881`。`18790` 已由 japanese-study-mcp 使用。

## 1.1.0 更新

- 改用獨立中央 Voice Runtime，以 voice ID 選擇聲音；Launcher 不啟停共用服務。
- 移除已保存比對的舊 GPT-SoVITS 原始碼，更新專案路徑與中央服務文件。
- Core 維持 shadow-only；人工聽感及桌面互動仍待驗收。

## 版本來源

Kuro 的產品版本以 repo root 的 [`VERSION`](../../VERSION) 為準，目前是 `1.1.0`。

下列版本屬於子元件，不和 Kuro 產品版本綁在一起：

- `pet-electron/package.json`：Electron shell 的 private package 版本。
- `Open-LLM-VTuber/pyproject.toml`：conversation runtime fork 的元件版本。
- 各項 schema、protocol 與 tool policy version：用來維護資料或 contract 相容性，不能拿來代替產品版本。

因此，升級 Kuro 大版本時不應直接改寫所有子元件版本；只有對應元件本身發布或 contract 改變時才各自調整。

## Repo 結構

```text
kuro/
├─ VERSION                        # Kuro 產品版本；目前為 1.1.0
├─ launcher_qt.py                 # Qt 應用入口
├─ kuro_launcher/                 # Launcher UI、controller、config 與 process helpers
├─ kuro_core/                     # Shadow-only Kuro Core contract、SQLite 與研究 trace
├─ kuro_launcher.settings.yaml    # Canonical local runtime 設定
├─ Open-LLM-VTuber/               # Conversation、agent、tools、memory、WebSocket
├─ projects/                      # Project prompt packs
├─ bridges/                       # 翻譯與 spoken rendering bridge
├─ pet-electron/                  # Live2D、Reader、Briefing、tray 與 control server
├─ local_translator/              # 獨立 Ollama 翻譯 helper
├─ voices/                        # Local voice references；git 只保留 .gitkeep
├─ vendor/                        # 第三方 Cubism source/reference
├─ docs/product/                  # 已填寫的長期產品方向
├─ docs/agent-runs/               # 長任務規格、計畫、進度與驗證證據
├─ docs/assets/readme/            # README 公開圖片
├─ .env.example                   # 無 secret 的環境變數範例
├─ compose.yaml                   # 舊容器化實驗；目前不是 canonical 啟動方式
└─ 00_kuro_bootstrap.ps1          # 早期環境準備 helper；不是完整安裝器
```

以下內容只應存在本機，不應進 git：

- `.env`、`.env.local`、API keys、tokens、cookies、credentials。
- `launcher_logs/`、chat history、memory、Electron `userData` 與 generated runtime config。
- `envs/`、`node_modules/`、renderer build output 與暫存檔。
- 模型權重、pretrained models、datasets、reference audio 與產生音訊。

## Local control API

Pet shell 啟動後可做最小狀態檢查：

```powershell
Invoke-RestMethod http://127.0.0.1:23567/status
Invoke-RestMethod http://127.0.0.1:23567/briefing
```

主要 endpoint：

| Method | Path | 用途 |
| --- | --- | --- |
| `GET` | `/status` | Electron、renderer、backend connection 與視窗狀態。 |
| `GET` | `/briefing` | 目前 snapshot、source status 與 memory candidates。 |
| `POST` | `/briefing/snapshot` | 取代目前 Briefing snapshot。 |
| `POST` | `/briefing/memory-candidates` | 新增待審核記憶候選。 |
| `POST` | `/briefing/memory-candidate-status` | 核准、拒絕或更新候選狀態。 |
| `POST` | `/briefing/mail/refresh` | 觸發一次 mail refresh。 |
| `POST` | `/command` | 顯示、隱藏、Reader、Briefing、表情與其他 pet commands。 |
| `POST` | `/backend-config` | 更新 Electron renderer 的 backend connection。 |

這是 loopback control surface，不是公開網路 API。新增 endpoint 時要保留輸入驗證、payload bounds 與 write confirmation 邊界。

工作面板另外使用 `127.0.0.1:23568` 的 launcher control API。它不是一般管理者 CLI：
每次 launcher 啟動會產生新的 bearer token，只傳給 Electron main process，不寫入設定檔、renderer 或 git。
Profile、記憶與刪除對話等操作，還必須先通過 Electron 原生確認視窗；renderer 只能呼叫明確列出的 IPC。

## 目前已知的架構債

這些是重整時應優先處理的責任混合，不代表要一次全部重寫：

1. **`QtLauncherController` 責任過廣**：它同時管理 process、profile、history、memory、Briefing 與 pet commands。後續應依 runtime orchestration 與 feature service 拆分，但保留現有 UI contract。
2. **Electron main process 暫時持有 domain integration**：mail polling/rules 與 study snapshot normalization 現在位於 `pet-electron/src/main-process/`。長期應移到獨立 adapter/service，Electron 只消費 typed snapshot。
3. **Briefing store 混合 schema、persistence 與 memory candidate queue**：應先版本化資料 contract，再決定是否抽離 storage service。
4. **設定層次多但缺少單一 schema 驗證**：env、launcher settings、character、project 與 generated config 需要更明確的 precedence、version 與 startup validation。
5. **`compose.yaml` 與 `00_kuro_bootstrap.ps1` 已偏離目前 Launcher 模型**：前者仍使用 `9881/8001`，後者建立的環境路徑也不同。完成對齊前，兩者不能當 canonical 啟動文件。
6. **Fork 與產品程式放在同一 repo**：`Open-LLM-VTuber/` 與 Cubism vendor code 的上游同步、Kuro patch boundary 和 upgrade 流程仍需明文化。
7. **Local state 分散**：conversation/memory、launcher logs、Briefing/Electron state 分屬不同 runtime owner；未來需要統一的資料盤點、備份與清除策略，但不能把 private state 搬進 git。
8. **Kuro Core 仍在 shadow 階段**：`kuro_core/` 已建立 observation、freshness、SQLite 與 decision trace 基礎，但尚未接入 live runtime；目前 Today 與 Briefing 仍以 Electron legacy path 為 primary，不能把 shadow package 描述為已完成 cutover。

## 重構時必須守住的原則

- Launcher 管啟動與操作，conversation runtime 管對話，Electron 管呈現，domain service 管資料真相。
- Backend contract、tool policy、memory policy 與 freshness 不能藏在角色 prompt 或 UI 裡。
- 顯示層可以摘要與排版，但不能把 `partial`、`missing`、`stale` 或 provider failure 說成確定結論。
- 短期 Briefing、tool result 與長期角色記憶必須保持分離。
- Write、delete、send、publish、長期記憶修改與大量 quota 行為預設需要確認並留下可審計線索。
- 每次重構先保留 public interface 與使用者可見行為，再逐步替換內部責任；不要用一次性大改寫掩蓋 ownership 問題。

建議的重整順序是：先固定 component ownership 與資料 contract，再拆 process orchestration，
接著抽離 Electron 內的 domain adapters，最後才重做 UI 與安裝／發佈流程。

## 工具確認的實作限制

工作面板特定操作透過 Electron main process 與 Launcher control API 提供原生確認。這不等於一般 MCP 工具已有確認佇列：`Open-LLM-VTuber/src/open_llm_vtuber/mcpp/tool_policy_manager.py` 目前會拒絕 `confirm`／`needs_confirmation`，回報 runtime 尚無確認流程。不能改成 allow 來繞過限制。

返回[架構索引](index.md)。

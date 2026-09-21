# 能力與責任地圖

2026-09-21 source inventory。Production 表示目前正式接線；目前程序是否載入該版本，另依 [RuntimeServices](RuntimeServices.md) 驗證。目標分層見 [OperatingModel](../product/OperatingModel.md)。

## Canonical owner

| 能力 | 現行 owner／入口 | Truth／persistence | Consumer／成熟度 |
| --- | --- | --- | --- |
| Profile、process lifecycle | `kuro_launcher/qt_controller.py`、`services.py`、`procs.py` | Launcher child handles、component readiness | Work Panel／Production |
| Runtime config | `kuro_launcher/config.py`、`runtime_conf.py` | `kuro_launcher.settings.yaml`；generated conf 是衍生檔 | Launcher、conversation、Electron／Production |
| Core lifecycle | `kuro_launcher/core_runtime.py` | owned PID、instance、token、sourceRoot | Electron main／Production |
| Conversation | `Open-LLM-VTuber/src/open_llm_vtuber/conversations/`、`routes.py`、`websocket_handler.py` | runtime turn／session；local chat history | WebSocket clients／Production |
| Agent／prompt composition | 同 runtime 的 `agent/` | 模型輸出是衍生建議，非權限或正式工作狀態 | conversation／Production |
| MCP registry／discovery | `mcpp/server_registry.py`、`mcp_client.py` | server registry＋完整 discovery；partial 與 cache 分開 | tool adapter／Production source |
| Tool identity／catalog | `mcpp/tool_identity.py`、`tool_catalog_manager.py` | canonical `server::tool`；provider alias 是映射 | agent／executor／Production source |
| Tool permission | `mcpp/tool_policy_manager.py` | `tool_policy.json` 及有效參數規則 | Launcher policy UI、executor、OMI direct path／Production source |
| Tool schema | `mcpp/tool_schema.py`、`tool_adapter.py` | discovery raw schema、validated args、provider profile | agent／executor／Production source |
| Tool execution／result | `mcpp/tool_executor.py`、`tool_result.py` | 外部結果與 execution state；工具文字不是授權 | 模型／Reader／history／Production source |
| Privacy projection | `mcpp/privacy.py` | 依模型、UI、log 等接收面投影 | runtime consumers／Production source |
| OMI preflight | `mcpp/market_preflight.py` | 消費 OMI evidence／limits；市場 truth 仍屬 OMI | agent／Production source |
| Character memory | runtime 的 `character_memory_*.py` | local memory records／index；來源、授權與 lifecycle | agent、Launcher memory UI／Production source |
| Schedule | `kuro_core/schedule_contract.py`、`schedule_store.py`、`schedule_api.py` | `schedule_*` tables；Core 為唯一正式 owner | `core-client.js`、SchedulePanel／Production |
| Schedule notification 決策 | `kuro_core/schedule_notifications.py` | preferences、delivery、lease、audit | Electron delivery／Production |
| Schedule notification 配送 | `pet-electron/src/main-process/schedule-notifications.js` | OS callback 回 Core ack；不是 eligibility truth | 桌面通知／Production |
| DB bootstrap／schema orchestration | `kuro_core/storage.py` | 單一 DB-wide `user_version=3` | ScheduleServer 及 shadow tests／Production dependency |
| Observation／DecisionTrace | `kuro_core/contracts.py`、`service.py`、`storage.py` | typed observations／decision_traces；研究另用 DB | tests／explicit probe／Shadow |
| Legacy observation adapter | `kuro_core/legacy_briefing_adapter.py`、`shadow_probe.py` | source-status 投影與比較摘要 | shadow diagnostics；不接管正式 Today |
| Today／Briefing | Electron `briefing-store.js`、`today-classifier.js` | `userData/briefing-store.json` 與讀取時投影 | Work Panel／Briefing／Legacy primary |
| Mail integration | Electron `mail-briefing-service.js`＋`Open-LLM-VTuber/local_mcp/mail_*` | provider message truth；private preferences／rules／snapshot | Briefing／Legacy primary |
| Study integration | Electron `study-briefing.js` | external study snapshot；學習系統擁有進度算法 | Briefing／Legacy primary |
| Work Panel／Reader／Live2D | `pet-electron/` | 顯示、互動、視窗 state | 使用者／Production |
| Spoken rendering | `bridges/deeplx_bridge.py` | 衍生的短語音文字／emotion | runtime translate／TTS／Production |
| TTS consumer | runtime `tts/gpt_sovits_tts.py`、Launcher `voice_client.py` | voice ID／readiness；不持有模型或引擎 | 語音 lane／Production source |
| Voice model／inference | 外部 Central Voice Runtime | 外部工作區模型、references、inference lock | Kuro、其他 consumers／Shared external owner |

表內 `mcpp/` 與 memory 簡寫皆位於 `Open-LLM-VTuber/src/open_llm_vtuber/`。MCP M0 的 source 與 A8 runtime/provider/desktop 狀態見[既有交付紀錄](../agent-runs/mcp-trust-security-m0/Progress.md)，不能從此表推論 A8 已完成。

## Electron legacy owner 與切換條件

以下目標尚未接線。本輪只固定 owner 與驗收邊界，不建立第二套 Core 實作。

| 現行 owner | 正式 read／write path 與保存 | 目標 owner | Cutover 必須證明 |
| --- | --- | --- | --- |
| `briefing-store.js` | `createBriefingStore` 讀寫 `userData/briefing-store.json`；snapshot／candidate mutation 由 main IPC 或 Pet control 到 store；read 合併 study 並產生 Today | Core Briefing composition；外部原始內容仍屬 domain | versioned snapshot contract；source/time/status/candidates parity；私有 state 備份；consumer 全部切換後停止舊 writer |
| `today-classifier.js` | `briefing-store.normalizeSnapshot()` 呼叫 `buildTodaySnapshot`／`mergeTodaySections`；投影隨 snapshot 保存，無獨立 Task Store | Core Task／Attention priority projection | priority reason、去重、日期／時區、空白／missing／stale parity；UI 只 consume；不可將分類結果直接等同正式 task |
| `mail-briefing-service.js` | 啟停本 repo mail poller、一次 refresh、message reader；讀寫 private Gmail preferences／rules；poller 將 snapshot 送 Pet control | Integration plane 管 provider IO；Core 管工作投影與提醒偏好 | source identity/time/failure contract；poller／rules 單一 owner；讀寫確認與 quota 邊界；切換後關閉舊 poller；mail provider 保留 message／delivery truth |
| `study-briefing.js` | 讀 `studySnapshotPath`，由 `mergeStudyIntoSnapshot` 合併內容、Today 與 sourceStatus；不寫 external study DB | Study adapter 管投影；Core 組成 Briefing／Attention | freshness 與 connection 分開；不能以現行 `connected` 或缺值預設推論 current／零任務；保留學習系統進度與日界線語意 |

共同順序：contract → shadow 比較 → parity evidence → 一次只切一個 authoritative writer／reader → runtime 與 UI 驗收 → 移除 legacy。回退必須恢復同一份已驗證 state 與舊 consumer，不能開雙 writer 或用 prompt 補足缺失。Schedule 已完成自己的局部 cutover，不需因 Today 尚未切換而回退。

讀寫細節見 [DataLineage](DataLineage.md)，DB ownership 見 [CorePersistence](CorePersistence.md)。

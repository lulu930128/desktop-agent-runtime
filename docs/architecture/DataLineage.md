# 現行資料流與寫入邊界

本頁描述 source 接線；[責任地圖](OwnershipMap.md)定義 owner，[RuntimeServices](RuntimeServices.md)定義程序與驗證。外部 domain truth 不因進入 LLM、snapshot 或語音而改由 Kuro 擁有。

## 對話與工具

```text
Work Panel / Pet / Qt client
  -> /client-ws -> websocket_handler -> conversations -> agent
  -> LLM request / tool request
  -> mcpp identity + catalog + policy + raw schema validation
  -> executor / MCP server -> domain system
  -> structured result + execution status + limitations
  -> privacy / bounded projections -> agent / visible answer / Reader / history
```

Canonical identity 是 `server::tool`；provider alias 不得改變 owner 或 wire name。Discovery complete、cached、partial 分開；tool description／result 是資料，不能批准下一個 action。一般 MCP `confirm`／`needs_confirmation` 目前會 blocked，不能將 Launcher 特定原生確認流程推論成通用 tool confirmation queue。

OMI 還有 agent 的 direct stream／fallback 與 `market_preflight.py` 路徑；它們仍受 policy／schema／privacy 邊界約束，不能因不經一般 executor 就變成 bypass。Market freshness、provider failure、partial／missing 與 decision 由 OMI 提供；Kuro 只保留、投影與解釋。

Chat history 是 conversation state；tool result 與回答不是正式 Schedule mutation，也不是長期記憶授權。

## Schedule 與通知

```text
SchedulePanel
  -> preload work-panel-schedule IPC
  -> core-client.js 驗證 main frame / action / Core identity
  -> :23569 /v1/schedule/*（session token）
  -> ScheduleServer -> ScheduleStore -> work.sqlite3
  -> versioned response / view -> UI

ScheduleServer worker -> materialize occurrences -> ScheduleNotifications.tick
  -> persisted ready delivery
  -> Electron claim -> authorize -> OS notification -> ack -> Core audit
```

Core 持有 recurrence、overdue、timezone、completion、revision、idempotency 及通知 eligibility。`view` 讀取既有狀態；materialization／mutation 是明確寫入。Client 每次先驗證 `kuro.core.schedule.v1`／schema 3／instance，renderer 不取得 token 或 DB handle。

Write contract 包含 confirmation、expected revision 與 idempotency；UI 收到 conflict／offline／unknown 時不能假裝已保存。通知 OS 配送與 SQLite 無法原子提交；unknown acknowledgement 不盲目重送。`delivered` 是配送端回報，不等於使用者已閱讀。

正式 API 不提供 Observation ingest 或 `context_snapshot()`；Schedule 與 shadow details 不互相替代。

## Briefing／Today／mail／study

```text
Mail provider -> local_mcp mail poller（Electron service 管理）
  -> Pet control /briefing/snapshot -> briefing-store.json
External study source -> local study snapshot（設定的 studySnapshotPath）
  -> study-briefing read / normalize / merge
briefing-store normalize -> today-classifier -> Today / Briefing / Work Panel
```

`briefing-store.js` 在讀取時可合併 study 檔案；snapshot 與 memory candidates 的 mutation 可落盤 Electron `userData`。Mail preferences／rules 存在可配置的 private 路徑，預設為 `Open-LLM-VTuber/private/gmail/`。這些是 current legacy integration paths，不是 Core 已接管的證據。

外部 study 進度與 mail message truth 仍由來源擁有。現行 study projection 會標 `connected`，並有空值預設；這些不能當作 current／無待辦的可靠判定。Observation shadow adapter 的正交 availability／freshness／connection 比較尚未成為正式顯示路徑。

各 module 的讀寫、保存、target owner 與切換條件見 [OwnershipMap](OwnershipMap.md)。

## Observation／Decision shadow

```text
顯式 shadow probe -> GET Pet /briefing（唯讀）
  -> legacy_briefing_adapter.source_status_observations
  -> availability / freshness / connection 比較摘要

測試或隔離研究 harness -> KuroCore.ingest / record_decision
  -> KuroCoreStore -> 隔離 DB observations / decision_traces
  -> context_snapshot(as_of=...) -> 研究 consumer
```

`shadow_probe.py` 不落盤 raw Briefing，也不啟動 refresh；它不是背景 production writer。Source 搜尋中 `KuroCore(...)` 的直接建構者在 `tests/test_kuro_core_store.py`。但 `KuroCoreStore.initialize()` 是正式 ScheduleServer 啟動依賴：同庫有 shadow tables，不代表 production 已在使用 observation 服務，也不代表可對正式 DB 做研究。

## 記憶

Briefing snapshot → memory candidate → `setBriefingMemoryCandidateStatus` → 更新 `briefing-store.json`。這條 status 路徑不會呼叫 runtime memory manager，candidate 標示核准不等於已保存成長期記憶。

正式 memory 管理由 Launcher memory 操作／runtime memory manager 與 index 處理。Candidate status、保存授權、evidence provenance 與記憶可檢索狀態是不同關卡。Daily snapshot、tool success、LLM 說「已完成」不能自行變成 active long-term memory。

Character memory、shared work memory、tool result、Briefing 與 system work state 維持不同責任；目前能力與限制以 memory source 及 [M0 紀錄](../agent-runs/mcp-trust-security-m0/Progress.md)為準。

## 語音與顯示

可見完整回答 → Bridge `/render_spoken`／translation → 簡短 spoken text／emotion → runtime TTS consumer `POST /tts` → 外部 Central Voice → WAV → runtime audio payload → Electron playback／嘴型 → playback-complete。

Launcher health readiness 只觀察，不合成：cold、busy、available、unavailable 不等於播放或人工聽感結果。Consumer 每句先 discovery；busy 略過本句、timeout 不重送原句，文字 lane 可完成。模型與 inference lifecycle 由中央 owner 管理，詳見[中央語音文件](../central-voice-runtime.md)。

# Kuro Research Core v0

## Goal

- 建立 model-agnostic、local-first、可長期承接的 Kuro Core，讓 observation、task、attention、policy、action 與 audit 逐步由 backend-owned contract 管理。
- 建立可回放的 decision trace 與評估基礎，使 Kuro 的優先順序、記憶、主動提醒和模型選擇能以證據比較，而不是只憑主觀印象調整。
- 第一階段先以 shadow path 驗證資料語意與持久化，不影響目前可用的 Work Panel、Launcher、conversation runtime、Live2D、TTS 或外部 domain systems。

## Non-goals

- 不訓練或 fine-tune 自有基礎模型。
- 不讓 Kuro 取代 OMI、學習、新聞、mail、calendar 或 Memory Core 的 domain truth。
- 不在 v0 開放寄信、交易、刪除、發布或其他 `scoped_auto` side effect。
- 不進行 Big Bang rewrite，也不立即移除 Electron Briefing store 或現有 Today classifier。
- 不把 private runtime snapshot、信件內容、記憶、chat history、token、log 或研究 trace 寫入 Git。

## Hard constraints

- OMI 擁有市場 evidence、freshness、decision 與 limitations；Kuro 只消費並保留其語意。
- Electron、Qt、Live2D、Reader、Briefing 與角色 prompt 不得成為 task、freshness、policy 或 audit 的唯一真相來源。
- `connected` 只代表 transport／connection 狀態，不能取代 `current`；availability、freshness 與 connection 必須可分別表達。
- `unknown`、`missing`、`partial`、`stale` 與 `0` 不得互換。
- 所有 current observation 必須有 bounded validity；無 source time 或 freshness policy 時降級為 unknown。
- 寫入必須具備 schema version、idempotency、concurrency protection 與 crash-safe transaction。
- Decision trace 只保存 bounded metadata、digest、reference 與結果摘要，不保存完整 prompt、secret 或不必要的 private payload。
- 新路徑先 shadow、compare、保留 rollback，再逐步成為 primary。

## Context

- Repo: `C:\project\kuro`
- Related systems: Qt Launcher、Open-LLM-VTuber、Electron Work Panel／Briefing、OMI、study systems、mail adapter、Memory Core。
- Current known state:
  - Work Panel 與對話 runtime 已可用，但產品工作狀態仍散落在 Qt、Electron Briefing store、conversation runtime 與 local state。
  - Today priority 目前在 Electron main process 計算，Briefing snapshot 由 Electron `userData` JSON 保存。
  - 唯讀 live probe 已證明 connection healthy 與資料 current 可能同時不成立；因此 freshness 必須由 Core contract 顯式管理。
  - Tool policy 能 fail closed，但完整 confirmation queue、action audit 與 reconciliation 尚未完成。

## Deliverables

- `kuro_core/` shadow package：versioned observation contract、freshness semantics、SQLite persistence、bounded context projection、decision trace。
- Legacy Briefing source-status shadow adapter，僅搬運 health metadata，不複製 private message 或 domain payload。
- Targeted tests：timezone、freshness、missing semantics、schema、idempotency、concurrency、trace round-trip。
- 後續 Task／Attention／Action／Policy／Audit contracts 與 runtime cutover 計畫。
- `docs/product/Roadmap.md` 與本目錄的 `Plan.md`／`Progress.md`。

## Done criteria

- 至少一個真實 read-only integration 透過 Core contract 產生 observation，且 Work Panel 能正確顯示 current、stale、partial、missing、offline 與 auth_required。
- Kuro Core 成為 task、attention、policy、action status 與 audit 的唯一 authoritative owner；legacy path 已完成 shadow comparison 與 rollback-safe cutover。
- Today 可顯示三到五個優先項目、排序理由、來源時間、限制與下一步。
- Decision replay 能比較 rule-only、不同模型與 hybrid ranking，並記錄可解釋的結果與使用者 feedback。
- Confirmation payload binding、idempotency、failure／unknown result reconciliation 與 audit 通過 targeted tests。
- 正常重啟、異常終止及 Windows reboot 後不遺失正式狀態、不重複提醒或重複 side effect。
- 完成對應 Q2、Q3 與 Q4 runtime／UI 驗證後，才可把專案標記為完成。

## Open questions / assumptions

- v0 以 repo 內純 Python package 與 SQLite 建立 logical Core；是否獨立成常駐 process，待 API contract 與 lifecycle acceptance 後決定。
- Shared work memory 未來可由獨立 Memory Core 提供，但 tasks／attention／actions 仍由 Kuro Core 擁有。
- 各 integration 的 TTL 與 freshness policy 必須由 source contract 或 adapter 設定，不能使用一個全域時間假設。

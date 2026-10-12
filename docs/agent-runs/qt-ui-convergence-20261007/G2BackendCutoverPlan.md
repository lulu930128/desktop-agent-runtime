# G2 — Actionable evidence + backend owner cutover plan

日期：2026-10-09
狀態：Ready for implementation

## Goal

把 G1 pure Work/Attention/Today contract 接到真實但 bounded 的 Study/Mail integration evidence，建立 canonical Core Today read path，並先把 Mail poller lifecycle 從 Electron 搬到 Launcher。

G2 完成後：
- Core Today composition 是 canonical backend truth。
- Study/Mail concrete evidence 由 backend adapters 產生。
- Electron 不再擁有 Mail poller lifecycle。
- Legacy Work Panel 可以暫時仍是 display consumer，直到 G4/G5 Qt cutover。
- 不把 provider truth 搬進 Core，不新增 DB。

## 1. Study actionable evidence

新增 `kuro_core/study_work_adapter.py`（或同責任最小模組）。

Input：既有 configured Study snapshot handoff。

Output：bounded `tuple[SourceEvidence, ...]`。

來源：
- `vocab.today.review`
- `vocab.today.focus`
- `vocab.today.new`
- explicit `today.items` only when identity/action fields valid

Rules：
- 必須有 stable word/item id。
- title/summary bounded；可顯示 kanji/reading/meaning 的 bounded local presentation，但不進 status API/shadow report。
- source_ref opaque bounded text。
- review：action=STUDY，required=true。
- focus：action=STUDY，attention_requested=true，importance=high。
- new：action=STUDY；除非 source 明確 required，不自行宣稱 critical。
- 不用 aggregate counts 生成 evidence。
- timestamp / freshness / availability 沿用 snapshot quality。
- max evidence count bounded，超限 fail closed，不 truncate silently。
- no DB/provider/network。

## 2. Mail actionable evidence handoff

新增 producer handoff（建議 `mail_work_handoff.py`）與 Core adapter（`mail_work_adapter.py`）。

`mail_update_briefing()` 同一次 provider fetch：
1. 寫 status handoff（現有）。
2. 寫 work handoff（新）。
3. legacy dashboard publish（在 G5 前仍可保留 display consumer）。

Work handoff只包含 bounded actionable metadata，例如：
- schemaVersion/source/updatedAt
- message id / thread id
- subject (bounded)
- sender display/address (bounded)
- date
- unread
- requiredEvent
- muted
- attention
- priorityLevel (bounded enum)
- gmailImportant
- safe event id/name/category
- no body
- no attachment content
- no token/cookie/OAuth
- snippet 不進 canonical work handoff

Failure：
- provider失敗保留 last-good work handoff，不把空清單覆蓋成「0 work」。
- status handoff仍記 provider/auth failure。
- dashboard publish failure不得改寫 provider/work success。

Core `mail_work_adapter.py`：
- bounded pure read
- output concrete SourceEvidence
- id/dedup deterministic
- requiredEvent -> required
- muted -> muted
- attention -> attention_requested
- priorityLevel high/critical/urgent only 映射 bounded importance；不沿用 legacy numeric priorityScore
- action=OPEN（message detail/reply仍由 provider command/detail path）
- no DB/provider IO

## 3. Canonical configuration

`core.integrations.mail` 增加 work_path，例如：`${open_llm_vtuber_dir}/private/gmail/mail_work.json`。

Study沿用既有 snapshot_path。

Launcher config / CoreRuntime：
- enabled/path/TTL/max fail closed
- Core child收到 Mail work path
- Electron/producer收到同一 resolved Mail work path env
- inherited env先清除再注入 canonical path
- missing handoff是 runtime missing，不是 startup failure

## 4. Core Today capability

新增 minimal `TodayCapability` / equivalent composition，不做 manager/store。

Responsibilities：
- 從 configured Study work adapter / Mail work adapter 取得 concrete evidence
- 從既有 Study/Mail status adapters取得 source Observations
- 呼叫 G1 `build_today_view()`
- 使用 Core configured timezone
- pure read
- no persistence

Register：
- `GET /v1/today`
- response contract `kuro.core.today.v1`
- bearer auth同 Core
- no query mutation / no refresh
- API host不 import provider/business adapter；composition root注入 capability

Status：
- Core `/status` capabilities新增 today contract/configured source ids
- 不把 Today schema綁 Schedule schema

## 5. Mail poller lifecycle owner

新增 Launcher-owned `MailPollerRuntime`（或最小同責任類別），spawn既有 `mail_briefing_poller.py`。

Canonical owner：Launcher lifecycle -> one poller process。

要求：
- exact child handle/PID
- disabled不啟動
- interval/preferences仍讀既有 canonical private settings
- 不新增第二份 preferences/rules truth
- Electron不再自行 spawn long-running poller when owner=launcher
- Launcher注入明確 `KURO_MAIL_POLLER_OWNER=launcher`
- Electron mail service看到該 owner時只保留 display/manual/detail/preferences/rules compatibility，不 start/restart poller
- G5時 legacy dashboard publish可關閉；G2暫時可保留 legacy display更新

禁止雙 poller。

## 6. Legacy boundary

G2不要 physical delete：
- study-briefing.js
- mail-briefing-service.js
- briefing-store.js
- today-classifier.js

但要在 owner map/tests明確：
- Today priority/composition canonical backend = Core TodayCapability
- Mail poller lifecycle = Launcher
- provider truth = local_mcp/Gmail
- Study truth = external Study system
- legacy modules只剩 display/parity/compat until Qt cutover

不要在 Electron新增新 business rule。

## 7. Tests

新增 synthetic tests：
- Study concrete review/focus/new -> SourceEvidence
- invalid/missing ids不產假 evidence
- aggregate-only snapshot不冒充 work
- Mail handoff privacy/bounds/last-good
- mail required/muted/attention/importance映射
- Core Today route healthy/degraded/missing
- no GET side effects
- Today route sourceStates與items一致
- config path canonical
- inherited work path env清除
- one Mail poller owner
- Electron canonical owner flag下不 spawn poller
- Launcher poller exact-child lifecycle
- no DB/provider IO from Core Today

Regression：
- G1 53
- Core
- Schedule
- Mail status
- Study
- Node relevant Electron tests
- diff check
- temp/pyc integrity

## 8. Stop conditions

- 新增 Mail provider client到 Core
- 新增第二個 poller
- Today GET觸發 provider refresh
- aggregate counts轉正式 tasks
- 新增 DB tables
- 修改 Qt UI（屬 G4）
- physical delete legacy modules（屬 G7）
- 新增 silent fallback to legacy Today

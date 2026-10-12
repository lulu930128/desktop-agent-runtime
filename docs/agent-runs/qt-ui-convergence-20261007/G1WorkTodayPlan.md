# G1 — Work / Attention / Today backend plan

日期：2026-10-09  
狀態：**Implemented + source/backend validated（2026-10-09）；production adoption / UI cutover 未做；G2 未開始。** 驗收見 `G1Checkpoint.md`。

## 1. Goal

建立完全不依賴 Electron / Qt 的 canonical backend contract：

```text
SourceEvidence
  -> Work Projection
  -> TaskCandidate
  -> WorkItem
  -> AttentionDecision
  -> TodayView
```

同時保留 source health：

```text
Observation(source_status)
  -> TodayView.sourceStates
```

G1 只建立純 backend contract、deterministic policy、synthetic tests 與 shadow comparison tooling。

**不做 production cutover、不新增 Today writer、不新增 Qt UI、不讀真實 Mail/Study payload。**

---

## 2. Why G1 must not consume current aggregate status as tasks

M1a–M1f 的 Study/Mail integrations目前只提供 privacy-bounded source status/aggregate，例如：

- Study: todayFocus / todayReview / todayNew counts
- Mail: highPriority / requiredEvents / unread counts

這些足以判斷 source health / aggregate state，但不足以回答：

- 哪一封 Mail 要處理？
- 哪一個 Study item 要複習？
- 為什麼它今天要出現？
- 它和另一個 item 是否重複？
- 使用者能執行什麼 action？

因此 G1 禁止：

```text
todayFocus=8 -> 建一個「複習 8 個單字」正式 Task
highPriority=3 -> 建一個「處理 3 封重要信」正式 Task
```

除非未來 integration 明確產生 versioned actionable evidence。

Current status Observation 只進 sourceStates，不直接變 TaskCandidate。

---

## 3. Contracts

建議新增 `kuro_core/work_contracts.py`。

### 3.1 SourceEvidence

標準化「一個可被工作層判斷的具體 evidence」。

至少：

- evidence_id
- integration_id
- kind
- source_ref
- title
- summary
- observed_at
- received_at
- valid_until
- availability
- freshness
- connection
- dedup_key
- due_at / remind_at optional
- required
- muted
- attention_requested
- importance: low / normal / high / critical
- action_kind
- safe metadata

限制：

- immutable
- timezone-aware UTC normalization
- bounded text / metadata
- sensitive key rejection沿用 Core contracts
- source_ref 不是 permission
- evidence 不等於 Task

### 3.2 TaskCandidate

由 SourceEvidence 投影出的「可被 Work/Attention 接受或抑制的候選」。

至少：

- candidate_id
- evidence_id
- integration_id/source
- kind
- dedup_key
- title/summary
- due_at
- required
- muted
- attention_requested
- importance
- action_kind
- source quality snapshot
- inclusion reason codes

TaskCandidate 不持久化，不等於正式完成/未完成 task state。

### 3.3 WorkItem

G1 先定 canonical in-memory work representation，不新增 DB：

- work_id
- candidate_id
- status = open（G1 only）
- identity/dedup fields
- title/summary
- source/action
- due_at
- source evidence ref

不得新增 TaskStore / work tables。

### 3.4 AttentionReason

machine-readable：

- code
- category
- weight/rank optional
- safe detail

禁止只有 UI prose。

建議 reason codes至少：

- required
- overdue
- due_today
- due_soon
- attention_requested
- importance_high
- importance_critical
- source_stale
- source_partial
- source_offline
- source_auth_required
- muted
- duplicate_suppressed

### 3.5 AttentionDecision

- work_id
- level
- included
- reasons
- deterministic rank

Level 可沿用 legacy vocabulary 作為 domain enum，但重新定義語意，不抄 JS rule：

- urgent
- must
- focus
- watch
- normal
- muted

基本 policy：

1. muted && !required -> muted / not included in default Today items
2. required + overdue -> urgent
3. required -> must
4. critical -> urgent
5. high importance / explicit attention -> focus
6. due today / due soon -> watch or focus（依 deterministic rule）
7. default -> normal
8. source stale/partial 不自動升 priority；只附 quality reason
9. source missing/offline/auth_required 且沒有 concrete evidence -> 不產生假 Task，source state 仍顯示 degraded

不要做 opaque numeric priority score。

### 3.6 TodayItem

UI-neutral view model：

- id/work_id
- source
- kind
- title
- summary
- action_kind
- due_at
- level
- reasonCodes
- evidenceRef
- stale/partial flags

不包含 provider secret/raw mail body。

### 3.7 TodaySection

G1 不把 Electron section layout搬進 domain。

建議 canonical sections只依 attention：

- immediate: urgent + must
- focus: focus
- watch: watch
- normal: normal（可被 consumer選擇是否顯示）

muted不進 default sections，但有 suppressed count。

### 3.8 TodayView

contract: `kuro.core.today.v1`

至少：

- generatedAt
- asOf
- localDate
- timezone
- complete: bool
- items
- sections
- counts
- sourceStates
- limitations

sourceStates 要讓 missing/stale/partial/offline/auth_required 不會被 UI 解讀成「0 tasks」。

---

## 4. Time / timezone

G1 必須把 date boundary 定死：

- input timestamps timezone-aware
- internal normalize UTC
- Today localDate 使用 explicit IANA timezone，例如 Asia/Taipei
- 不使用 process local timezone 作隱性真相
- due_today 以 TodayView timezone 判定
- deterministic as_of required in tests
- DST timezone亦需至少一組測試，即使 production default Asia/Taipei

---

## 5. Dedup

Dedup 是 Work layer，不是 UI。

基本規則：

- canonical dedup_key required
- 同 dedup_key 多 evidence 時選 deterministic winner
- winner：較高 source quality / required / newer observedAt，再 stable evidence_id
- 被壓掉的 candidate留下 duplicate_suppressed evidence count / diagnostic
- 不用 title fuzzy matching
- 不用 LLM dedup

---

## 6. Source health

G1 可以重用既有 Observation status enums，但不得把 Observation直接當 Task。

建議：

`build_today_view(..., source_observations=[...])`

sourceStates 只輸出：

- integrationId
- availability
- freshness
- connection
- observedAt
- validUntil
- limitationCount

privacy-bounded，類似 M1a–M1f status projection。

complete=false if any configured/expected source is missing/offline/auth_required/partial/stale（policy需明確測試）。

「沒有 item」和「source 不完整」必須可區分。

---

## 7. Work projection

建議新增：

- `work_projection.py`
- `attention.py`
- `today.py`

但不要新增 manager/service/store abstraction。

所有 function pure / deterministic：

- `project_evidence(evidence) -> TaskCandidate | None`
- `materialize_work(candidate) -> WorkItem`
- `decide_attention(work, evidence, as_of, timezone) -> AttentionDecision`
- `build_today_view(evidence, source_observations, as_of, timezone) -> TodayView`

G1 不掛到 `CoreApplication` route。

---

## 8. Legacy Today usage

`today-classifier.js` 只當：

- existing behavior inventory
- synthetic shadow oracle / comparison source

禁止：

- line-by-line port
- 同 priorityScore thresholds照搬
- Electron UI section layout變成 Core contract
- legacy `meta/text` 字串成為 domain truth

可保留的概念：

- urgent / must / focus / watch / normal / muted vocabulary
- deterministic ordering
- dedup
- source attribution

但新 contract必須有 explicit reasons / source quality / timezone semantics。

---

## 9. Shadow comparison tooling

建議新增 `today_shadow.py` pure helper。

輸入：

- new TodayView
- synthetic / exported legacy Today snapshot

輸出 privacy-bounded comparison：

- item count by level
- item count by source
- overlap count
- new-only count
- legacy-only count
- hashed identity samples（bounded）
- no title/snippet/raw message content

Shadow comparator 不進 production API，不讀檔，不 call Electron。

至少 synthetic tests證明：
- same logical items -> overlap
- level difference明確報出
- text/private payload不出現在 report

---

## 10. Persistence / API

G1：

- **不新增 DB table**
- 不改 schema version
- 不 ingest source evidence 到正式 observations DB
- 不新增 `/v1/today`
- 不改 `CoreApplication` route
- 不改 Electron production reader
- 不改 Qt

G1 完成只是 backend contract ready。

Production read API / persistence若需要，屬後續 Gate，先由 reviewer重新決定。

---

## 11. Tests

至少新增：

### Contract
- immutable
- bounds
- timezone required
- sensitive metadata rejected
- deterministic serialization
- invalid enum / id rejected

### Projection
- concrete Mail synthetic evidence -> candidate
- concrete Study synthetic evidence -> candidate
- aggregate source status alone -> no candidate
- muted suppression
- required preserved

### Attention
- overdue required -> urgent
- required -> must
- critical -> urgent
- high/attention -> focus
- due today/soon deterministic
- stale/partial only adds quality reason
- missing source without evidence -> no fake task

### Dedup
- same dedup -> one item
- deterministic winner independent of input order

### Today
- timezone/localDate
- deterministic sorting
- sourceStates degraded != zero tasks
- complete flag
- section counts
- suppressed count
- privacy bounded
- empty healthy source vs empty degraded source distinguishable

### Shadow
- legacy synthetic comparison
- no private text leakage

### Regression
- existing M1a–M1f Core/Schedule/Mail/Study suites still pass
- no changes to Electron JS
- git diff --check
- no temp/pyc side effects

---

## 12. Stop conditions

立即停止並回報：

- 需要讀真 Gmail / Study production payload
- 想把 aggregate count直接轉正式 task
- 想改 `today-classifier.js`
- 想新增 Today API route
- 想新增 DB tables
- 想改 Qt
- 想把 legacy Today切到新 backend
- 想新增 Mail/Study provider IO
- 想用 LLM分類 priority/dedup
- 想把 current Electron priorityScore threshold整套複製

---

## 13. G1 done definition

G1 可以標 DONE 只有當：

- versioned Work/Attention/Today contracts存在
- synthetic Mail + Study concrete evidence能產生 deterministic TodayView
- missing/stale/partial不會被當成零任務
- priority有 explicit machine-readable reasons
- dedup deterministic
- timezone/date boundary explicit
- shadow compare可用且不洩漏 private text
- no DB/API/Qt/Electron production cutover
- existing foundation regressions全綠
- reviewer確認沒有做成 today-classifier.py 的平行翻版

下一 Gate 才能討論 G2 actionable evidence producer / legacy backend cutover。

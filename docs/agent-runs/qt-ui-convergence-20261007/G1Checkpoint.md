# G1 — Work / Attention / Today backend checkpoint

日期：2026-10-09  
狀態：**G1 source/backend contract ready；production adoption / UI cutover 未做；G2 未開始。**

## Gate 判定

G1 已建立 Electron-independent、Qt-independent、pure/deterministic 的 Work / Attention / Today backend contract：

```text
SourceEvidence
  -> TaskCandidate
  -> WorkItem
  -> AttentionDecision
  -> TodayView

Observation(kind=source_status)
  -> TodayView.sourceStates
```

這是 source/backend foundation，不是 production Today owner。

目前正式使用路徑仍是：
- Electron `briefing-store.js` / `today-classifier.js`：Today / Briefing legacy primary；
- Electron Study / Mail consumer lifecycle：legacy primary；
- Qt 尚未 consume G1 TodayView。

G1 沒有新增 API route、DB table/schema、persistence、provider IO 或 UI wiring。

## 新增 source

| 檔案 | 責任 |
| --- | --- |
| `kuro_core/work_contracts.py` | immutable/versioned SourceEvidence、TaskCandidate、WorkItem、AttentionReason、AttentionDecision、TodayItem、TodaySection、SourceState、TodayView |
| `kuro_core/work_projection.py` | concrete evidence projection、in-memory work materialization、canonical dedup |
| `kuro_core/attention.py` | deterministic attention policy 與 machine-readable reasons |
| `kuro_core/today.py` | Today composition、source health、sections/counts、timezone/date boundary |
| `kuro_core/today_shadow.py` | privacy-bounded synthetic legacy comparison |
| `tests/test_kuro_core_work_g1.py` | G1 synthetic contract/policy/boundary regression |

## Contract boundary

### SourceEvidence

只有**具體、可行動 evidence** 才能進 Work projection。

Current M1a–M1f aggregate `Observation`（例如 Study todayFocus count、Mail highPriority count）一律：

```text
project_evidence(Observation) -> None
```

因此：
- `todayFocus=8` 不會變成正式「複習 8 個單字」Task；
- `highPriority=3` 不會變成正式「處理 3 封重要信」Task；
- aggregate status 只進 `sourceStates` / source health。

`source_ref` 是 required bounded opaque text（最多 500 字），允許 `/` 等 provider reference 字元，不是 permission / canonical ID。Reviewer 在第一版 contract 發現過度使用 strict identifier，已修正並補 regression。

Canonical identifier 只用於：
- evidence_id
- integration_id
- dedup_key
- candidate/work identity

### Privacy / bounds

- frozen dataclasses；
- timezone-aware datetime，內部 normalize UTC；
- bounded title/summary/metadata；
- recursive sensitive-key rejection；
- raw body/snippet/message/attachment/study payload metadata 拒絕；
- no provider secret / OAuth / raw mail body；
- no file / DB / network / subprocess IO in G1 pipeline。

## Attention policy

Level vocabulary保留：
- urgent
- must
- focus
- watch
- normal
- muted

但沒有照抄 legacy `priorityScore` threshold。

Deterministic precedence：

1. muted && !required -> muted / default Today excluded
2. required + overdue -> urgent
3. required -> must
4. critical -> urgent
5. high importance / attention requested / non-required overdue -> focus
6. due today / due within 24h / reminder due -> watch
7. otherwise -> normal

所有決策都有 machine-readable reason codes。

Source quality：
- stale
- partial
- missing
- offline
- auth_required
- unknown

只增加 quality reason，不自動把 priority 往上拉。

## Time / timezone

- `as_of` explicit；
- `timezone` 必須是 IANA zone；
- 不使用 process-local timezone；
- due_today 依 TodayView timezone local date；
- due_soon 是未來 24 小時 elapsed UTC window；
- exact due_at 不算 overdue；
- exact valid_until 仍 current；
- tests 包含 Asia/Taipei 以及 America/New_York DST spring-forward / fall-back fold。

## Dedup

- 只使用 explicit canonical `dedup_key`；
- 不用 title fuzzy matching；
- 不用 LLM dedup；
- winner selection deterministic、與 input order 無關；
- source quality優先，再 required、observedAt、stable IDs；
- duplicate losers 被記錄為 suppressed count / reason，而不是靜默消失。

## TodayView

Contract：`kuro.core.today.v1`

包含：
- generatedAt
- asOf
- localDate
- timezone
- complete
- items
- sections
- counts
- sourceStates
- limitations

Canonical sections：
- immediate = urgent + must
- focus
- watch
- normal

muted 不進 default sections，但保留 suppressed count。

### complete 的精確語意

**`complete=true` 只代表 caller 提供的 source status / evidence quality 完整健康，不代表「所有真實世界 actionable work 已完整列舉」。**

因此：
- healthy source + zero concrete evidence 可以是 `items=[] / complete=true`；
- missing/degraded expected source + zero evidence 是 `items=[] / complete=false`；
- concrete evidence 存在但沒有 source status，可顯示 item，但 source state missing、`complete=false`。

這個欄位在 G2 建立真正 actionable evidence producer 前，禁止 UI 解讀為「今天沒有其他事」。

## Shadow comparison

`today_shadow.compare_today_shadow()`：
- 不讀檔；
- 不呼叫 Electron；
- caller 必須提供 legacy ID -> canonical dedup key mapping；
- 不從 title/text 猜 identity；
- 只輸出 level/source counts、overlap/new-only/legacy-only、level transitions、bounded HMAC identity samples；
- 不輸出 title、summary、snippet、raw Mail/Study、source_ref、raw identity。

## Reviewer reverse check

已確認：
- 沒有 `/v1/today`；
- `CoreApplication` 沒有 Today route；
- 沒有 G1 DB table/schema/persistence；
- Qt / Launcher 沒有 TodayView consumer；
- Electron `today-classifier.js` / `briefing-store.js` 未修改；
- aggregate Observation 不產 TaskCandidate；
- G1 modules 為 pure backend，boundary test禁止 file/network/SQLite/subprocess IO。

## Validation

G1 targeted：
- `tests/test_kuro_core_work_g1.py`：**53 / 53 PASS**

Foundation regression：
- Mail handoff：**16 / 16 PASS**
- Mail adapter：**13 / 13 PASS**
- Study adapter：**16 / 16 PASS**
- `test_kuro_core*.py`：**121 / 121 PASS**（含 G1 53）
- Schedule：**44 / 44 PASS**
- Node core-client：**4 / 4 PASS**
- `git diff --check`：PASS

Targeted / full regression均使用：
- repo Python
- `-B`
- `PYTHONDONTWRITEBYTECODE=1`
- disposable TEMP/TMP
- synthetic data only

測試前後：
- Git status identical
- tracked/untracked file set identical
- ignored pyc/pyo/tmp path set identical
- validation temp removed

## Observation / acceptable debt

### Observation — EvidenceKind / ActionKind extensibility

G1 enum目前刻意只涵蓋已需要的 Mail / Study / reference 與基本 actions。

這不是 current defect，因為 G1 沒有 production consumer；但 G2 或未來 Calendar / Market evidence接入前，必須：
- 明確擴充 versioned contract；
- 不把未知 domain 偷塞成 `reference` 或 generic string；
- 補 projection / attention / privacy tests。

## G1 exit / next gate

G1 已滿足 source/backend contract done criteria。

尚未做：
- real Mail/Study actionable evidence producer；
- production Today API；
- DB persistence / TaskStore；
- Electron Today cutover；
- Qt consumer；
- runtime/UI acceptance。

**下一 Gate：G2 — actionable evidence producer + legacy backend owner cutover planning。G2 必須獨立開始，不由本 checkpoint 自動施工。**

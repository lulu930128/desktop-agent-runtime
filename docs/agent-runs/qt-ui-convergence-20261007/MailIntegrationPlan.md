# M1f — Mail Integration Boundary

日期：2026-10-08
狀態：source-level adoption 接線與 regression 已通過；正式 runtime 與 UI consumer 尚未 cutover。

## 1. 目標

在不改變現行 Mail UI / poller authoritative ownership 的前提下，建立第二個正式 Core integration boundary，驗證 M1e 的 IntegrationRegistry 不是 Study-specific abstraction。

本輪只做到：

Mail producer refresh
-> privacy-bounded local handoff
-> Core Mail adapter
-> read-only GET /v1/integrations/mail

不做 Today / Briefing / Qt consumer cutover。

## 2. 現況事實

目前 production Mail 主路徑：

Electron mail-briefing-service.js
-> mail_briefing_poller.py
-> mail_tools_server.mail_update_briefing()
-> live Gmail read-only fetch
-> build briefing snapshot / current mail classification
-> POST :23567 /briefing/snapshot
-> Electron briefing-store / Today

Mail preferences / rules 仍由 Electron + local_mcp private files 管理。
Core 目前不應讀 Electron userData / briefing-store，也不應直接呼叫 Gmail。

## 3. 核心原則

1. Core GET 不可觸發 Gmail/provider network。
2. Core GET 不可觸發 refresh、poller、OAuth、message detail 或 local mutation。
3. Core 不可讀 Electron userData / briefing-store 作 canonical Mail source。
4. Mail provider truth 仍屬 Gmail；目前 rules/preferences/classification owner 不在 Core。
5. 本輪新增 handoff 是 producer-to-Core 的 bounded status contract，不是 mailbox database。
6. 不搬 poller lifecycle、不搬 rules/preferences writer、不搬 Today classification。
7. 不新增第二個 Mail poller / Gmail client / process / port。
8. Electron legacy Briefing/Today 在 consumer cutover 前仍是正式 UI primary。

## 4. Mail status handoff

Canonical private handoff：

${open_llm_vtuber_dir}/private/gmail/mail_status.json

Writer owner：
既有 mail update producer path（mail_tools_server / mail_briefing_poller），不是 Core。

Reader：
Core mail_adapter only。

### Schema v1

建議最小 contract：

{
  "schemaVersion": 1,
  "source": "gmail_briefing",
  "lastAttemptAt": "<UTC ISO>",
  "lastAttemptOk": true,
  "lastSuccessAt": "<UTC ISO or empty>",
  "counts": {
    "resultSizeEstimate": 0,
    "fetched": 0,
    "unread": 0,
    "requiredEvents": 0,
    "highPriority": 0,
    "mediumPriority": 0,
    "muted": 0,
    "ordinary": 0,
    "gmailImportant": 0
  },
  "privacy": {
    "bodyFetched": false,
    "attachmentsFetched": false,
    "mailboxModified": false
  },
  "errorType": ""
}

禁止 handoff 保存：
- account email
- query text
- message id
- subject
- sender
- snippet/body
- rule content
- preference content
- OAuth/token path/value
- private filesystem path
- dashboard Today text

### Success / failure semantics

- provider fetch 成功時：
  - lastAttemptOk=true
  - lastSuccessAt 使用該成功 snapshot 的 timestamp
  - bounded aggregate counts 更新
  - errorType 清空
- provider fetch 失敗時：
  - 更新 lastAttemptAt / lastAttemptOk=false / bounded errorType
  - 保留上一份 lastSuccessAt + counts（若有）
  - 不把缺資料偽造成 0
- legacy dashboard POST 失敗，不得把 Gmail provider 成功誤判為 provider failure。
  handoff 應在成功 fetch 後即可更新，與 Electron dashboard availability 分離。

## 5. Handoff writer safety

新增 handoff writer 必須：
- atomic replace
- same-directory temp
- private dir only
- bounded JSON
- best-effort chmod 0600
- 不輸出 secrets/raw mail
- 不因 handoff write failure修改 mailbox
- 明確回報 local handoff write failure給 poller/tool，不 silent swallow
- 若存在平行 refresh，不能讓較舊 attempt 明顯覆蓋較新的 status；需要 bounded serialization/lock 或等價 ordering proof

不要修改既有 generic _write_json_file 的 OAuth/session semantics，除非有獨立 regression。

## 6. Core Mail adapter

新增 kuro_core/mail_adapter.py。

責任：
- bounded read mail_status.json
- schema validation
- mapping to existing Observation/status semantics
- no IO write
- no provider call
- no Today priority

建議 output contract：

kuro.core.integration.mail.v1

Connection mapping：
- lastAttemptOk=true -> connected
- lastAttemptOk=false -> disconnected
- no attempt evidence -> unknown

Availability/freshness：
- 有 valid last success + complete safe counts -> available
- last success 存在但 safe counts 不完整 -> partial
- handoff 不存在 -> missing
- 只有 failure、從未成功 -> offline / auth_required if bounded errorType explicitly proves auth
- freshness 只由 lastSuccessAt + configured TTL 決定
- connection 與 freshness 分開；last attempt fail + last-good current/stale 都必須可表達

不得把 lastAttemptAt 當 data observedAt。

## 7. Common bounded file helper

目前 Study adapter 已有 bounded JSON read。
M1f 不應複製第二套完全相同的：
stat -> max bytes -> read -> utf8 -> json -> shape

允許抽出一個 domain-neutral helper，例如 kuro_core/handoff.py：
- bounded JSON file read
- 只回 payload / typed read error
- 不判 availability/freshness/connection
- 不知道 Study/Mail
- 不 import domain modules

若抽 helper，Study adapter 必須同步改用並完整 regression；不得改 Study semantics。

## 8. IntegrationRegistry / Core host

IntegrationRegistry 必須證明可以同時獨立註冊：
- study
- mail

不要把 Registry 改成任意 plugin loader。

Mail route：
GET /v1/integrations/mail

要求：
- same bearer auth / no Origin
- no query
- disabled/unconfigured -> 404
- no private path in /status or response
- /status capabilities.integrations.configured 可列 mail
- API host 不 import mail_adapter
- ScheduleCapability 不 import mail

## 9. Launcher config / env ownership

在 core.integrations.mail 下新增：
- enabled: false
- status_path: ${open_llm_vtuber_dir}/private/gmail/mail_status.json
- ttl_seconds: 1800
- max_bytes: 65536

要求：
- enabled=true 時 status_path 必須 explicit/resolved absolute path
- TTL/max bytes bounded integer；拒絕 bool
- handoff file 本身可不存在，這是 runtime missing state，不是 startup failure
- 同一 canonical resolved path：
  - 傳給 Core child
  - 以 KURO_MAIL_STATUS_FILE 傳給 Electron main / poller child
- 不在 Python/JS 各自硬編兩份不同 canonical path
- status path 不出現在 /status 或 Mail API response

## 10. Existing Mail behavior preservation

本輪必須保持：
- mail-briefing-service.js 仍是 poller lifecycle / preferences / rules owner
- manual refresh 行為不變
- mail.get_message_detail 行為不變
- mail.daily_brief dashboard-first/live fallback 行為不變
- mail.update_briefing 仍更新 Electron Briefing
- Gmail scope 仍 readonly
- mailbox 不被 mark read / mutate
- 不改 tool policy risk category

本輪 handoff 寫入只能掛在既有 explicit update/poller refresh path。
不要讓 mail.daily_brief 的 live fallback 因本輪偷偷新增 local write。

## 11. Tests

### Producer handoff
Synthetic tests：
- success writes bounded schema
- no raw account/query/message/subject/sender/snippet/body
- failure preserves last-good success timestamp/counts
- failure without last-good does not invent zero counts
- dashboard POST failure does not erase successful provider status
- atomic write / no truncated JSON
- stale concurrent attempt cannot replace newer status
- handoff write failure surfaced without mailbox mutation

### Core adapter
- valid/current
- stale
- missing
- last-attempt-failed + current last-good
- last-attempt-failed + stale last-good
- never-success failure
- invalid json/utf8/shape/schema
- oversize
- safe metrics only
- idempotency/privacy
- no DB write

### Registry / host
- Study + Mail can coexist
- each disabled route 404 independently
- /status configured list correct
- no arbitrary renderer Core route
- Schedule regression unchanged

### Config/runtime
- mail enabled missing path rejects before child start
- configured missing file still starts Core
- Core child receives mail CLI path/ttl/max
- Electron child receives same KURO_MAIL_STATUS_FILE
- path never returned by Core API

### Regression
至少：
- test_kuro_core*.py
- test_schedule*.py
- new Mail producer tests
- core_client.test.cjs
- relevant config/runtime tests
- git diff --check
- temp / pyc / file-set integrity

全部使用 synthetic Gmail payload / mocked provider / temp files。
不得讀真實 Gmail、OAuth token、正式 briefing-store 或 production Core DB。

## 12. Stop conditions

出現任一項立即停止：
- Core GET 直接 import/call mail_tools_server 或 Gmail
- Core 讀 Electron briefing-store/userData
- API host 直接處理 Mail business logic
- ScheduleCapability import Mail
- 新建第二個 poller
- Core 開始寫 mail handoff
- handoff 含 account/query/message raw content
- mail.daily_brief 因本輪開始寫 handoff
- rules/preferences ownership被偷偷搬進 Core
- Today priority在本輪被新增到 Core
- legacy Electron reader被刪或 silent fallback改變
- 新舊 Mail writer 同時寫不同 canonical status truth

## 13. 完成定義

M1f 完成時只能宣稱：

- Mail producer 有一份 privacy-bounded status handoff
- Core 可以 pure-read Mail status
- IntegrationRegistry 已證明至少容納 Study + Mail 兩個獨立 capability
- Mail provider / poller / rules / Today ownership尚未 cutover

不得宣稱 Mail / Briefing / Today migration 完成。

## M1f adoption gap 修正與驗證（2026-10-08）

狀態：**source-level adoption 與 synthetic regression 通過；正式 runtime / Electron Mail / Today / Briefing / Qt consumer 未 cutover。**

- settings 新增 Mail block：預設 enabled=false、status_path=`${open_llm_vtuber_dir}/private/gmail/mail_status.json`、TTL 1800、max bytes 65536。
- CoreRuntime 驗證 explicit absolute path、bounded integer TTL/max 後傳入四個 Mail CLI flags；handoff file 不存在仍可啟動，route 回 missing。
- Electron child_environment 的 KURO_MAIL_STATUS_FILE 與 Core CLI 使用同一 resolved config path；disabled 不注入 env、不傳 Mail CLI、不註冊 Mail route。Registry configured 維持排序為 ["mail", "study"]。
- mail_update_briefing 的 provider MailAuthError 寫 auth_required，其他 failure 寫 provider_error；不寫 raw exception，保留 last-good counts/time，dashboard failure 不覆寫 provider success。
- Windows sharing/access/busy 衝突：writer atomic replace 與 domain-neutral reader 各有 0.5 秒 monotonic retry 上限；逾時仍 fail closed。保留同目錄 temp、writer lock/ordering，不 unlink target、不 truncate overwrite；reader 不寫檔。
- Concurrency test 使用 production read_json_handoff，要求每次成功讀取都是有效 dict/schema，且沒有 handoff error；deterministic tests 覆蓋 retry、timeout、nonretryable error。

驗證使用 `envs/kuro-llm310/python.exe -B -m unittest discover -s tests -p <pattern>`：

| Pattern / 命令 | 結果 |
| --- | --- |
| test_mail_status_handoff.py | 16/16 PASS |
| test_kuro_core_mail_adapter.py | 12/12 PASS |
| test_kuro_core_study_adapter.py | 15/15 PASS |
| test_schedule_runtime.py | 8/8 PASS |
| test_kuro_core*.py | 66/66 PASS |
| test_schedule*.py | 43/43 PASS |
| node --test tests/core_client.test.cjs | 4/4 PASS |
| in-memory Python compile | 7 files PASS |
| git diff --check | PASS |

Targeted adapter/runtime tests 已包含於對應 regression suite，不重複計入總數。所有 Python 測試使用 PYTHONDONTWRITEBYTECODE=1，TEMP/TMP 指向 disposable repo-local directory；測試前後 Git status 與 ignored pyc/tmp file set 一致，temp 已清除。

未讀真 Gmail、OAuth token、正式 handoff、briefing-store 或正式 Core DB，未啟動正式 stack，未改 ACL、commit/push。保留 M1e host 與既有 M1f producer/adapter/registry/CLI；Mail poller/preferences/rules/message detail/daily_brief live fallback 及 Today/Briefing/Qt ownership 不變，未新增第二個 provider client、poller、正式 process 或 port。

下一 gate 為獨立的正式 runtime adoption / consumer parity；本次證據不代表桌面常駐 process 已載入變更，也不代表 Mail/Today migration 完成。


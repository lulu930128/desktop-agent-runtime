# M1e — Kuro Core API Host Generalization

日期：2026-10-08  
狀態：Implemented + source-level validated（2026-10-08）；尚未宣稱目前桌面常駐 runtime 已重啟採用，也未完成 Study UI cutover

## 1. 背景與問題

M1e 實作前（歷史背景），`:23569` 由 `kuro_core/schedule_api.py::ScheduleServer` 同時負責。現行 source 已改由 `CoreApplication` 組裝 general `CoreApiServer` 與獨立 capability；G0 驗證見 `G0Checkpoint.md`：

- HTTP listener / auth / request parsing / error mapping
- `/status` process identity
- Schedule store / DB lease / schema bootstrap
- Schedule materialization worker
- Schedule notification decision
- Schedule routes

這在 Schedule 是唯一 capability 時可接受，但 M1a–M1c 已建立 read-only Study backend path：

`Study handoff -> study_adapter -> privacy-bounded Observation -> shadow report`

先前 M1d 曾直接在 `ScheduleServer` 加入 `/v1/integrations/study`。功能測試通過，但 reviewer 拒絕此設計並已回退，因為它讓 Schedule owner 偷偷變成 general integration gateway，而 `/status` / Launcher / Electron 仍宣告 `kuro.core.schedule.v1`。

本輪目標是先把 **process host** 與 **capability owner** 分開，再讓 Study 以 read-only integration capability 掛到同一個 Core process。

## 2. 終局原則

同一個 process / 同一個 port，不代表同一個 owner。

```
Launcher CoreRuntime
       |
       v
Kuro Core Process :23569
       |
       +-- Core API Host
       |     - listener
       |     - bearer auth
       |     - request parsing
       |     - route registry
       |     - process identity
       |     - shutdown
       |
       +-- Schedule Capability
       |     - ScheduleStore
       |     - DB lease / schema bootstrap
       |     - recurrence/materialization
       |     - notification decision
       |     - /v1/schedule/*
       |     - contract kuro.core.schedule.v1
       |
       +-- Integration Registry
             |
             +-- Study Integration
                   - bounded read only
                   - source -> Observation/status
                   - /v1/integrations/study
                   - contract kuro.core.integration.study.v1
```

禁止：

- API Host 直接讀 Study JSON。
- Study integration 直接碰 ScheduleStore / schedule DB tables。
- Schedule capability import Study adapter。
- Qt / Electron 直接讀 Study JSON 作為新 canonical path。
- 本輪搬 Mail / Today / Task / Attention。
- 為每個 integration 再開新 process / port。
- 保留舊 ScheduleServer 作 production fallback 與新 host 雙跑。

## 3. API contracts

### 3.1 Core process identity

`GET /status` 改為 process-level contract：

```json
{
  "ok": true,
  "service": "kuro-core",
  "contract": "kuro.core.api.v1",
  "instanceId": "...",
  "pid": 123,
  "sourceRoot": "...",
  "capabilities": {
    "schedule": {
      "contract": "kuro.core.schedule.v1",
      "schema": 3,
      "materialization": "complete|incomplete|failed|pending",
      "notificationScheduler": "running|failed|pending",
      "timezone": "Asia/Taipei",
      "today": "YYYY-MM-DD"
    },
    "integrations": {
      "contract": "kuro.core.integrations.v1",
      "configured": ["study"]
    }
  }
}
```

不應再把 schedule DB schema 當作 Core process top-level contract。

### 3.2 Schedule routes

既有 `/v1/schedule/*` request / response contract 保持 `kuro.core.schedule.v1`。

Schedule 的 persistence、recurrence、transaction、notification semantics 不改。

### 3.3 Study integration

`GET /v1/integrations/study`

- 使用既有 `kuro_core/study_adapter.py::build_study_status`。
- response contract：`kuro.core.integration.study.v1`。
- pure read。
- 不 refresh provider、不寫檔、不 ingest Core DB、不產生 Today item。
- connection / availability / freshness 必須保留正交語意。
- 不輸出 raw Study JSON、word、meaning、Today title / summary、實際 private path。
- 不接受 query fields。
- 未配置 Study 時應明確 unavailable / 404，不 fallback 到 Electron Briefing。
- route 需要相同 Core bearer auth，不接受 Origin。

## 4. 建議 source 結構

先拆 logical boundary，不做大規模 package relocation。

建議新增：

- `kuro_core/api_server.py`
  - `CoreApiServer`
  - loopback binding
  - exclusive listener
  - bearer auth
  - body limit / JSON parsing
  - route registration
  - generic error -> HTTP mapping
  - 不 import schedule_store / study_adapter

- `kuro_core/core_app.py`
  - `CoreApplication`
  - composition root
  - process-level `/status`
  - `/shutdown`
  - start/stop ordering
  - 組裝 Schedule capability + Integration registry

- `kuro_core/integrations.py`
  - 小型 integration registry / Study integration wrapper
  - 不做 provider algorithm
  - Study wrapper 只委派 `build_study_status`

Refactor：

- `kuro_core/schedule_api.py`
  - 從 HTTP host 降為 Schedule capability / route owner。
  - 保留 DB lease、ScheduleStore、materialization worker、notification owner。
  - 對 Core API Host 註冊 `/v1/schedule/*`。
  - 不 import Study。

如果 Codex 發現更少變更即可達到相同 ownership，可調整檔名，但不得改變上述責任。

## 5. Lifecycle / failure ordering

必須保留現有重要 invariant：

1. port collision 不可建立/修改另一個 DB。
2. 同 DB 第二個 Core process 必須被 service lease 阻擋。
3. capability init 失敗時，已 bind 的 API listener 必須關閉。
4. API host 啟動成功但 Schedule worker failed，status 必須能區分 process identity 與 capability failure。
5. shutdown 只停止 Launcher 持有的 exact Core child。
6. Central Voice 不屬 Core lifecycle。

建議 composition ordering：

```
pre-bind CoreApiServer
-> initialize Schedule capability / lease / schema
-> register capabilities/routes
-> start API serving
-> start Schedule worker
```

若實際 code 需要不同順序，必須以 tests 證明 port-collision / DB-touch invariant 未回歸。

## 6. Launcher / Electron consumer migration

所有硬驗 `kuro.core.schedule.v1` 的 process identity consumer 必須一起修改。

至少已知：

- `kuro_launcher/core_runtime.py::ready()`
- `pet-electron/src/main-process/core-client.js`
- `tests/core_client.test.cjs`
- `tests/test_schedule_runtime.py`
- architecture docs

新的驗證：

```
service == kuro-core
contract == kuro.core.api.v1
instanceId == expected
pid/sourceRoot == expected        # Launcher
capabilities.schedule.contract == kuro.core.schedule.v1
capabilities.schedule.schema == 3
```

Electron Schedule client 仍然只能呼叫 Schedule allowlist；不要因 Core host generalize 就讓 renderer 任意 call integration route。

若需要 Study consumer，應建立 main-process 專用 read-only integration client / IPC，不能把 bearer token 放 renderer。本輪可以只驗 API route，不必把 Work Panel 改成新 Study consumer。

## 7. Configuration

不要 hard-code private Study path 在 API Host。

在既有 Launcher config 下新增明確 integration config，例如：

```yaml
core:
  enabled: true
  port: 23569
  timezone: Asia/Taipei
  db_path: ...
  integrations:
    study:
      enabled: true
      snapshot_path: "${open_llm_vtuber_dir}/private/study/study_snapshot.json"
      ttl_seconds: 3600
      max_bytes: 2097152
```

要求：

- config parser 驗證 TTL / max bytes。
- disabled 時不註冊 Study route。
- path 由 Launcher config 解析後傳給 Core child。
- token 仍只走 env；private path 可走 argv/config，不能出現在 `/status` 或 API response。
- 不讀 raw payload 來判斷 startup readiness。

## 8. Tests / acceptance

### Core host
- `/status` = `kuro.core.api.v1`。
- process identity fields 正確。
- schedule capability nested contract/schema 正確。
- unauthorized / Origin rejected。
- unknown route = 404。
- repeated query / invalid JSON / body limit 保持 fail closed。
- `/shutdown` 不暴露給 Electron IPC。

### Schedule regression
- 既有 `test_schedule*.py` 全過。
- schedule API output contract 不變。
- GET purity 不回歸。
- recurrence / materialization / notification / DB lease 不變。
- port collision 不觸碰 DB。
- same DB second process 被 lease 擋住。

### Study
- configured route = 200 + `kuro.core.integration.study.v1`。
- missing/stale/partial semantics 沿用 M1a–M1c。
- input file bytes before/after 相同。
- private content/path 不出現在 response。
- no query。
- disabled/unconfigured = 404/unavailable，無 legacy fallback。
- 不建立 Observation DB write。

### Consumer
- Launcher `CoreRuntime.ready()` 驗新 host identity + nested schedule capability。
- Electron Schedule client 驗新 host identity，但 route allowlist仍只 Schedule。
- core-client Node tests 全過。

### Validation
至少：
- `test_kuro_core*.py`
- `test_schedule*.py`
- `node --test tests/core_client.test.cjs`（或 repo 既有等價命令）
- config targeted tests
- `git diff --check`

測試 temp 必須設 `PYTHONDONTWRITEBYTECODE=1` 或確保 isolated child 不留下 repo pyc。

## 9. 明確不做

本輪不：

- Qt UI migration。
- Electron Work Panel removal。
- Study authoritative UI cutover。
- Mail migration。
- Today / Briefing / Task / Attention implementation。
- Observation persistence adoption。
- DB schema migration。
- 新 port / 新 process。
- commit / push。

## 10. Reviewer stop conditions

出現以下任一情況就停止並回報，不應硬做完：

- `ScheduleServer` 只是改名但仍同時直接處理 Study business logic。
- `api_server.py` import `study_adapter` 或 `schedule_store`。
- Study route 直接加入舊 Schedule handler 巨型 if/elif。
- `/status` 仍用 `kuro.core.schedule.v1` 卻宣稱 host 已 generalize。
- Electron renderer 取得 Core token 或 arbitrary Core route。
- GET Study 觸發 refresh / persistence / DB mutation。
- 為相容保留新舊兩個 Core server 同時 production 生效。
- 測試為了通過而改變既有 Schedule semantics。

## 11. 完成定義

本輪完成時應能明確回答：

- 誰擁有 process listener/auth？ -> CoreApiServer
- 誰擁有 Schedule domain？ -> Schedule capability
- 誰擁有 Study projection？ -> Study integration adapter
- 誰啟動/停止 process？ -> Launcher CoreRuntime
- `:23569` 是什麼？ -> Kuro Core API Host
- Schedule contract 是否仍獨立？ -> 是，`kuro.core.schedule.v1`
- Study 是否已取代 Electron Today？ -> 否

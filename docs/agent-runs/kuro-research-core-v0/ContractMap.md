# Contract Map

本文件記錄 Kuro Research Core v0 已實作的 shadow contract。它是未來 producer／consumer 的程式介面基線，不代表 live runtime 已完成 cutover。

## Ownership

| Surface | v0 owner | Live status |
| --- | --- | --- |
| Observation schema、freshness projection、idempotency | `kuro_core` | Shadow only |
| Shadow SQLite 與 decision trace | `kuro_core.KuroCoreStore` | Tests only；尚未建立 live DB |
| Today priority／Briefing snapshot | Electron legacy path | Live primary |
| Mail／study domain data | 各 domain adapter／source | Kuro Core 只接收 health metadata |
| OMI market truth | OMI | 不搬入 Kuro Core |
| Character／shared memory | 現有 Kuro memory 與未來 Memory Core contract | 不等同 task／observation |

## Observation v1

`Observation` 是帶來源與時間的不可變事實輸入，不是 task、memory 或 AI 結論。

| Field | Meaning |
| --- | --- |
| `observation_id` | Core record identity；不是 provider identity。 |
| `integration_id` | Producer／adapter identity。 |
| `kind` | Bounded observation type，例如 `source_status`。 |
| `source_ref` | 回到 domain owner 的 reference；不複製 raw domain record。 |
| `title`／`summary` | Bounded、可呈現文字；不得含 secret 或不必要的 raw payload。 |
| `observed_at` | Source 真正觀察時間；未知時為 `null`。 |
| `received_at` | Kuro 收到 observation 的時間。 |
| `availability` | `available`、`partial`、`missing`、`offline`、`auth_required`、`unknown`。 |
| `declared_freshness` | Producer 宣告的 `current`、`stale` 或 `unknown`。 |
| `connection` | `connected`、`disconnected`、`auth_required` 或 `unknown`；不代表資料 current。 |
| `valid_until` | Current observation 的有效期限；current 時必填。 |
| `idempotency_key` | Integration scope 內的 stable duplicate key。 |
| `limitations` | Bounded warning／限制，不得靜默丟棄。 |
| `details` | 最多 32 KiB 的 JSON metadata；明顯 secret key 會 fail closed。 |

### Status projection

```text
connection ────────────────────────────────┐
availability ───────┐                      │
declared freshness ─┼─ effective freshness├─ UI / AI context
valid_until + as_of ┘                      │
                                           ┘
```

- `connected` 只描述 transport；TTL 過期後仍可投影為 `freshness=stale`。
- `partial`、`missing`、`offline`、`auth_required` 優先保留 availability 語意。
- `partial + stale` 由 `availability=partial` 與 `freshness=stale` 同時表達；單一 `status` 只作簡化投影。
- `missing` 不會因 details 中的 count 是 `0` 而轉成 current 或 empty-success。
- 沒有 timezone、source time 或 bounded validity 的 current observation 會被拒絕。

## Persistence v1

- SQLite schema 使用 `PRAGMA user_version=1`。
- `observations` 以 `(integration_id, idempotency_key)` 唯一。
- 相同 key、相同 semantic hash 是安全重試，回傳原 observation identity。
- 相同 key、不同 semantics 會拋出 `IdempotencyConflictError`，不使用 last-write-wins。
- 每次 ingest 使用 `BEGIN IMMEDIATE`、WAL、busy timeout 與 transaction，並有並行 duplicate test。
- DB path 必須由呼叫端明確提供；package import 不會建立檔案或啟動服務。

## Context projection v1

`KuroCore.context_snapshot()` 產生 `kuro.core.context.v1`：

- 以呼叫端提供的 `as_of` 動態重算 freshness。
- 預設不包含 `details`。
- 同時回傳 connection、availability、freshness 與簡化 status。
- 目前只提供 observation context；尚未加入 task、attention、policy 或 action。

## Decision trace v0

Decision trace 用於 replay 與模型／規則比較，只保存：

- run／trace／decision kind identity。
- observation references 與 selected references。
- model provider／model name、policy version、config digest。
- bounded output summary、duration 與 aggregate metrics。

不得保存 raw prompt、token、cookie、credential、完整信件、附件、chat、memory 或 raw market/account payload。

## Legacy Briefing adapter

- 只讀 `snapshot.sourceStatus`、source id、status、updated time 與 bounded limitations。
- 不複製 mail messages、body、attachment、study records 或 domain payload。
- Probe 只允許 loopback `http`、無 credential、精確 `/briefing` path，且不寫 DB。
- Per-source TTL 仍需由後續 settings／adapter contract 定義；目前 probe 預設一小時並允許顯式 override。

## 尚未實作

- Task、Attention、Action、Policy、Confirmation、Audit authoritative schema。
- Migration v1→v2、backup、restore、retention、reconciliation。
- Persistent shadow runner、scheduler、loopback API 與 launcher lifecycle。
- Legacy-vs-Core priority comparison、feedback events 與離線 replay runner。
- Electron／Open-LLM-VTuber runtime adoption。

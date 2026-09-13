# 本機時間表已實作 contract 與複查入口

2026-09-12。使用者先授權 M0–M3，後續授權完成 M4–M6 與重啟桌寵測試。證據與限制見 Progress.md。

## Owner 與儲存

Core schema 升為 3。原 Observation／DecisionTrace 資料保留；正式本機 schedule 不透過 Observation.details 或 Electron Briefing 保存。

- `schedule_items`：current payload、revision、cancelled、cutoff、materialization cursor／ordinal、lineage。
- `schedule_revisions`：追加 mutation audit，和 current 更新同一交易。
- `schedule_mutations`：全域 request idempotency key 與 payload digest／原回應。
- `schedule_occurrences`：原定日期 identity、展開的 payload、完成狀態、exception／cancelled、DST skip reason、UTC 查詢索引。
- `schedule_notification_deliveries`：due、channel、狀態、租約／fencing、snooze 與顯示標題。
- `schedule_preferences`／`schedule_notification_audit`：勿擾偏好與配送狀態歷程。

每次寫入使用 BEGIN IMMEDIATE；expectedRevision 不符回 409。相同 key／相同 payload 重送回原回應，相同 key／不同 payload 拒絕。單次編輯不重算其他例外，完成紀錄不被模板修改覆寫。

初次初始化使用 transaction-bound DDL，避免 executescript 提前提交。v1 → v2、v2 → v3 各自使用 SQLite backup API 產生 `<db>.pre-vN-<random>.bak`，交易失敗回退該階段；未知新版本 fail closed。正式 DB 已由 Launcher 初始化至 v3。

## 本機 item

```json
{
  "title": "日文學習",
  "notes": "",
  "kind": "study",
  "timezone": "Asia/Taipei",
  "allDay": false,
  "start": "2026-09-14T20:00:00+08:00",
  "end": "2026-09-14T21:00:00+08:00",
  "trackCompletion": true,
  "recurrence": {"frequency": "weekly", "interval": 1, "weekdays": [0, 2]},
  "notification": {"enabled": false, "minutesBefore": 10, "allDayTime": "09:00", "channel": "panel"}
}
```

- kind：event／study／deadline。deadline 只帶 due，不混用 start/end。
- 全天：日期 start/end（end exclusive），或期限 due 日期。
- 時區是必填 IANA 名稱；datetime offset 必須符合該 zone 的 wall time。UI 由 Core status 取得預設時區；prepare 在 backend 轉換表單 wall time。
- recurrence 可 null，或 daily／weekly／monthly，interval 1–120；weekly weekdays 0=週一…6=週日；until inclusive 與 count 擇一。
- weekly interval 以 anchor 所在週一為週邊界；monthly 使用 anchor 日號，缺少該日的月份跳過。
- DST gap 的手動輸入拒絕；展開 occurrence 記 `dst_gap`，count 包含該原定 occurrence。generated fold 選較早 fold=0。
- title 上限 300 字、notes 2000 字、每次 request 64 KiB。
- 一個通知偏好隨系列 payload 保存，單次 exception 可覆寫；勿擾偏好獨立保存。

## API

所有 route（包含 status）需 `Authorization: Bearer <session-token>`，不接受 Origin；只 bind 127.0.0.1。token 不經 argv／renderer／URL。

| Method／route | Request | Result |
| --- | --- | --- |
| GET `/status` | 無 | service、contract、schema、PID、sourceRoot、Launcher session instanceId、materialization 狀態 |
| GET `/v1/schedule/item?id=...` | id | current item、revision、cancelled、cutoff、lineage |
| GET `/v1/schedule/view` | start、end（exclusive）、timezone、可選 limit/offset | versioned local schedule view |
| POST `/v1/schedule/mutate` | action、idempotencyKey、confirmed:true、其餘 scoped fields | current record；future update 另有 successor |
| POST `/v1/schedule/materialize` | through: ISO 日期 | evaluatedDays、complete；每次最多 3660 evaluated days |
| POST `/v1/schedule/prepare` | item（可含本地 datetime） | 驗證並轉換成 canonical item，不寫入 |
| GET `/v1/schedule/notifications` | 無 | preferences、最近 100 筆紀錄與 hasMore |
| POST `/v1/schedule/notification-action` | claim／authorize／ack／dismiss／snooze／preferences | 狀態或偏好；renderer 只允許最後三種 |
| POST `/shutdown` | 空 object；Launcher 專用 | stopping；不暴露到 Electron IPC |

mutation action：create／update／cancel／complete／skip／reopen。

- create 只帶 item、confirmed、key。
- 其他動作帶 id、expectedRevision；update 帶完整 replacement item。
- scope：all／this／future。this/future 必須带已 materialized 的 occurrenceDate。
- complete/skip/reopen 只允許 scope=this，且該 occurrence 啟用 trackCompletion。
- future 在原定日期拆分；回傳 successor，舊系列保存 cutoff。遇到無法安全映射的例外／已完成歷史回 409，不自動解決。
- 取消 tombstone 保留，沒有硬刪除 route。

錯誤：400 invalid_request、401 unauthorized、403 confirmation_required、404 not_found、409 conflict、503 core_unavailable。unsupported action 拒絕；不把失敗回成成功空清單。

## 投影與 materialization

view range 1–366 日，limit 1–500，hasMore／nextOffset 明確表示分頁。回傳每個 occurrence 的 item、state、timeState、overdue、stable identity、revision。

- 今日 timed/all-day 使用區間相交；昨日开始但今日未結束包含在內。
- deadline 不捏造開始時段；日期型期限在該日結束才逾期。
- 追蹤完成的逾期項目在之後範圍仍列出，直到完成／略過／取消；多年項目不因 lookback 被丟掉。
- 已完成歷史只在與查詢範圍相交時返回；完成狀態不等於時間狀態。
- GET 用 read-only connection 與一致 snapshot，不建表、不展開、不刷新、不配送。
- materialize 是獨立 command；背景 worker 每 5 秒推進 UTC 今日 +10 天並評估通知。寫入後先回傳保存結果，若同步投影失敗加 projection=pending，背景續試，不把已保存誤報為失敗。
- 不同時區邊界採保守 coverage：cursor 必須超過 view end +1 日；手動 materialize 至 view end +1 即可保證 coverage。未完成回 incomplete，不把 items=[] 當無安排。
- DST skip 數量與 limitation 可見；外部來源固定 `not_configured`，不假裝同步成功。

## Launcher 與 Electron

- canonical 設定：`core.enabled: true`、`core.port: 23569`、`core.timezone: Asia/Taipei`、`core.db_path: ${ROOT}/local_state/core/work.sqlite3`。
- 23569 在 M0 查詢時未見 listener；仍會在每次啟動重新檢查與 exclusive bind，不採用未知既有 service。
- `local_state/` 已忽略，正式與 shadow DB 不混用。port 只在 YAML 指定，其他元件由設定／環境取得。
- Launcher 開啟 Pet 前可啟動 opt-in Core，失敗只記錄 Core unavailable；profile 切換不關 Core，Launcher close 才停止自己持有的 child。
- readiness 核對 service/schema/contract/PID/sourceRoot/session identity。CoreRuntime session identity 在同一 Launcher 的 child restart 間保留，PID 重新核對。
- Core DB 有 OS lease，跨 port 第二個 service 也拒絕；Windows listener 使用 SO_EXCLUSIVEADDRUSE。
- Electron main client 每次操作先核對身分，只有 Work Panel main frame 可使用 `work-panel-schedule` IPC。
- preload 提供 `kuroWorkPanel.schedule(action, payload)`；時間表清單／表單讀寫 Core。Mail builder、Briefing normalization、Today classifier 與來源篩選已退出 legacy Calendar。
- disabled 時清除繼承環境中的舊 Core connection，避免意外沿用。

## 通知狀態機

預設每筆提醒關閉；全域勿擾 22:00–08:00，時區取 Core 設定。pending → ready 或 suppressed；desktop 配送需 claimed（20 秒租約）→ authorize → dispatching → delivered／failed／unknown。Electron 的 show 事件代表 OS 接受展示，不代表使用者閱讀。

逾期 30 分鐘的 candidate 記 missed，不集中補發。claimed 租約逾期可重新領取；dispatching 逾期記 unknown，不自動重送。取消／完成／改期依 scope 撤銷舊候選，配送前重查；規則 key 綁 occurrence 的時間與通知偏好，其他 instance 完成不會讓已送通知重送。

面板可標已讀或 snooze 1 分鐘至 7 日；inactive occurrence 不可 snooze。OS 與 DB 無分散式原子交易，authorize 後至 OS show 間仍有極短競態，不承諾 exactly-once。

## 驗證與後續

測試入口：`tests/test_schedule_core.py`、`tests/test_schedule_api.py`、`tests/test_schedule_runtime.py`、`tests/core_client.test.cjs`。完整結果見 Progress.md。

另有 notifications Python／Node tests、Calendar cutover regression、隔離 Electron DOM／截圖 smoke。外部 Calendar 同步、OAuth、語音提醒與 AI 自動寫入仍屬後續範圍。

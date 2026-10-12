# W1–W5 當次 24-method ownership／freshness／audit 清單

本表取代舊 coverage 的「本輪證據」部分。來源：pinned `types.ts::WorkPanelBridge`、`owner-bridge.ts::makeOwnerBridge/OwnerTransport`、`qt_web_protocol.py::RequestBroker/validate`、`qt_web_adapter.py::prepare/dispatch/_owned_call/receive`。24 方法名由 frontend regression 和 pinned interface 逐一核對。

共同 transport：Web → narrow QWebChannel Wire.submit → GUI RequestBroker → 原 QtOwnerAdapter；worker snapshot/queued completion，不從 worker 讀 chat QObject。contract、request ID、expected client/actor/context/history/revision、payload bounds、12 pending、10000 session IDs、20s timeout（profile95s）、duplicate/stale/unknown fence 共用。寫入未知不重試；native confirm 綁 payload 並在 modal 後重新核對 identity。不存在 durable 全域 action ledger；不能把本地 broker correlation 稱為完整 production audit。

S＝本輪 source/disposable test PASS；U＝native WebEngine／正式 runtime proof UNVERIFIED。共同證據 `ValidationSummary.json` 列最新 suite/log；native 只有 `native-W3` import blocker。所有行仍是 S/U，沒有宣稱正式上線。

| 方法 | 原有 owner／程式位置／transport | 讀寫與 side effects | freshness／fence | audit lineage／proof |
| --- | --- | --- | --- | --- |
| schedule | `_owned_call` → controller → Core HTTP | 下表；read、prepare、mutate 分開 | Core contract、revision/key、confirm；禁止 materialize | Core mutation/notification receipt＋broker ID；S/U |
| getState | `_owned_call` → controller runtime status＋GUI chat snapshot | 讀；不啟服務 | 失敗撤銷 capture snapshot，保留 offline | scoped reply／runtime source；S/U |
| getData | `_owned_call/today_projection` → controller → GET /v1/today | 讀；不 refresh、不排序 | generatedAt/asOf/complete/sourceStates/limitations；context 換時清cache | Core workId/evidenceRef＋reply ID；S/U |
| getChatState | dispatch/chat_state → 同一 QtRuntimeChatClient | 讀 GUI cache | identity、historyReady、connected、turn state | client/context/history＋event；S/U |
| getChatHistory | dispatch/_history_result → 同一 client 的 timeline cache | 讀，無 private file fallback | 未載入不假造 transcript，scope change 清空 | scoped cached transcript；S/U |
| getProfile | _owned_call → controller registry＋WS snapshot | 讀 | selected 與 effective 分開 | registered conf/project/model/thinking；S/U |
| applyProfile | prepare/_owned_call/_reconcile_profile → 既有 controller lifecycle | confirm 後 profile 設定/啟動 | 等新context、connected＋historyReady、effective相符；unknown不重送 | broker ID/目標與WS effective；正式restart未做；S/U |
| getHistories | dispatch/receive → chat.request_history_list → qt-primary WS | list＋fetch 已選 history；不新建 | server correlation＋identity；不把任意history當選取 | history.v1 request ID；S/U |
| createHistory | dispatch/receive → chat.create_history(force_new=True) → WS | 建新 synthetic/owner history；明確UI intent，無OS confirm | 等 server new-history-created | WS request ID/context；S/U |
| selectHistory | dispatch/receive → chat.select_history → WS | 切選取；無OS confirm | server response/current selection fence | WS request ID/history UID；S/U |
| deleteHistory | prepare/dispatch/receive → chat.delete_history → WS | native confirm；取消無送出 | actor/context 在 modal 後仍一致；server success 才完成 | WS request ID＋native decision；S/U |
| getMemories | prepare/_owned_call → controller → canonical Memory manager | 讀 JSON/index，無第二store | connected===true＋historyReady===true；actor/digest reviewed snapshot；offline撤銷 | conf UID/content_digest，讀失敗不是空成功；S/U |
| memoryAction | prepare/_owned_call → 原 Memory manager | add/status/delete/compact，native confirm | 同上＋260字＋expected_conf_uid/digest；compact全digest；重連需重讀 | canonical JSON與derived SQLite/digest；S/U |
| getTools | _owned_call → read_tool_policy_summary | 唯讀；無 discovery/elevation | error/offline；confirmation_available=false | policy owner summary，無mutation endpoint；S/U |
| sendText | prepare/_submit_text → 同一 chat.send_text → WS | 一次送出，必要時先new history；不呼叫第二LLM | ready/idle/context；6附件、單4MiB/總8MiB、MIME/size/base64 | scoped submit accepted≠completed；S/U |
| refreshMail | _owned_call | 拒絕；無 refresh side effect | canonical contract GAP | explicit unavailable，無provider fallback；S/U |
| getMailMessage | _owned_call | 拒絕；不讀private mail | body contract GAP | explicit unavailable；S/U |
| control | prepare/dispatch/_owned_call → chat interrupt 或 controller Pet gateway | interrupt無confirm；其他allowlist變更confirm | captureAvailable/actor/history；inner capture ok；拒绝/stale不送 | scoped submit＋Pet回應；device/lifecycle fixture unavailable；S/U |
| closeWindow | dispatch → 原QMainWindow.close | 僅window lifecycle | 不新增tray/owner | fixture close/brokerClosed；native未觀測；S/U |
| minimizeWindow | dispatch → 原QMainWindow.showMinimized | 僅window state | 同一owner | correlated reply；native未觀測；S/U |
| toggleMaximizeWindow | dispatch → 原QMainWindow state | 僅window state | 同一owner | correlated reply；native未觀測；S/U |
| onState | OwnerTransport/getState結果 → listener | 訂閱/取消；不寫owner | context/revision event fence | reply/event identity；S/U |
| onData | Core讀回結果 → listener | 訂閱；不provider refresh | same-context stale可見，跨context清空 | Core evidence＋transportStale；S/U |
| onChatState | 既有chat信號 → GUI queued slot → Wire.event | 訂閱；不建WS | scoped stream/tool/control，忽略unscoped/old history | event identity/tool ID；S/U |

## Schedule 子動作

| action | canonical route | 讀寫／revision／audit |
| --- | --- | --- |
| status | GET /status | 唯讀；核對Core與nested Schedule contract |
| view/item | GET /v1/schedule/view 或 item | 唯讀bounds/date/timezone/ID；不materialize |
| prepare | POST /v1/schedule/prepare | 純validation；實際DB前後 bytes 相同 |
| materialize | 無 Web dispatch | 明確拒絕；Core既有scheduler是唯一owner |
| mutate | POST /v1/schedule/mutate | native confirm、expectedRevision（更新）、idempotencyKey、Core transaction/receipt |
| notifications | GET /v1/schedule/notifications | 唯讀、無tick；提供consumer contract與revision |
| notification-action | POST /v1/schedule/notification-command | 僅dismiss/snooze/preferences；native confirm、revision/key、receipt、cache用後失效 |

QtScheduleDelivery 唯一 claim→authorize→ack；Web 沒有 claim/delivery authority。真 OS notification 尚未驗。

## 偏好與缺失 contract

`owner-preferences.ts` 僅五種展示值，session memory、不持久、不寫 QSettings；原 Qt QSettings 仍持久 compact 唯一 owner。原版 localStorage API 被有界相容層承接，禁止 secrets/token/PII/authoritative state。測試逐 key/value、restart empty、source scan；native setter/bootstrap仍需實機確認。

ToolPolicy mutation、Mail body/refresh、Study jump、未完整 lifecycle 沒有可安全暴露的canonical contract，維持 GAP。不得以原renderer按鈕存在推定有能力，亦不恢復Electron legacy/:23568。

# WorkPanelBridge 方法與 ownership

原版24 methods 全由 owner-bridge.ts 明列；共同 QWebChannel envelope→GUI RequestBroker→QtOwnerAdapter，具 actor/client/context/history/revision/request ID/timeout。下表有測均指 synthetic/source contract，**各列 production WebEngine live proof 都 UNVERIFIED**。

| 方法 | 唯一 owner／transport | 結果、權限與測試 |
| --- | --- | --- |
| schedule | controller→Core HTTP | 下表；candidate/WS-HTTP/notification/Schedule tests |
| getState | controller runtime/diagnostic＋GUI chat snapshot | 真實 owner status，offline不造ready；thread/offline tests |
| getData | controller→GET /v1/today | canonical raw＋formatting，order/freshness/limitations；adversarial/HTTP tests |
| getChatState | 既有 QtRuntimeChatClient GUI cache | scoped text/tool/identity；candidate/WS |
| getChatHistory | 同一 chat 的載入 timeline cache | 不讀私有 history file；未載入為空；history/binding tests |
| getProfile | controller registry＋chat effective snapshot | public conf_uid/project_id映射owner keys；profile/R2 |
| applyProfile | controller set selections/start_profile→既有 lifecycle/WS | native confirm，等待新 context/effective actor/project/model/thinking；candidate/R2，真restart未做 |
| getHistories | chat.request_history_list→同一 qt-primary WS，再 fetch 目前選中 history | correlated list+timeline；actual WS/R1/R4 |
| createHistory | chat.create_history(force_new=True)→WS | UI意圖、無OS confirm、等server結果；candidate/WS |
| selectHistory | chat.select_history→WS | 無OS confirm，identity fence；candidate/WS |
| deleteHistory | chat.delete_history→WS | native confirm/cancel/actor fence；candidate/WS |
| getMemories | controller.read_memory_records(strict=True)→原manager | actor/digest snapshot；read error不假空成功；candidate/R2 |
| memoryAction | 原 controller add/status/delete/compact→Memory manager | review/expected_conf_uid/digest，compact全digest，260字；candidate/R2 |
| getTools | controller.read_tool_policy_summary→原ToolPolicy | 唯讀、無permission escalation；candidate/R2 |
| sendText | 同一chat.send_text→qt-primary WS | 普通send無confirm；空history先create；6附件/單4MiB/總8MiB/type/base64；accepted≠complete；candidate/WS/IME Node |
| refreshMail | 缺canonical refresh contract | unavailable/disabled，無provider/legacy fallback；negative test |
| getMailMessage | 缺canonical body contract | unavailable，無private mail storage fallback；negative test |
| control | interrupt→chat；Pet/perception→原controller/gateway | explicit allowlist；interrupt無confirm，其他變更confirm；capture history fence；candidate/G5/G6 |
| closeWindow | 現有QMainWindow.close | 原close/tray lifecycle；binding有測，native未驗 |
| minimizeWindow | 現有QMainWindow.showMinimized | 無第二window；binding有測，native未驗 |
| toggleMaximizeWindow | 現有QMainWindow state | binding有測，native未驗 |
| onState | getState回應/owner event→Web listener | revision fence/unsubscribe；frontend |
| onData | Core read result→Web listener | transportStale，不刷新provider；frontend/candidate |
| onChatState | 既有chat signals→GUI queued slot→channel event | scoped text/tool/control，忽略unscoped frame；actual WS/candidate/frontend |

## Schedule 子動作

| action | route／owner | 邊界 |
| --- | --- | --- |
| status | GET /status | contract驗證、唯讀 |
| view | GET /v1/schedule/view | bounds/date/timezone、唯讀 |
| item | GET /v1/schedule/item | 指定ID、唯讀 |
| prepare | POST /v1/schedule/prepare | Core純validation、不mutate |
| materialize | 不dispatch | 原版refresh也拒絕；既有Core scheduler owner執行 |
| mutate | POST /v1/schedule/mutate | native confirm/revision/key/原Core transaction |
| notifications | GET /v1/schedule/notifications | 唯讀transaction，capability/preferencesRevision/item revision、不tick |
| notification-action | POST /v1/schedule/notification-command | dismiss/snooze/preferences，read contract+revision/key/native confirm；用後cache失效，不retry unknown |

claim/authorize/ack 僅既有 QtScheduleDelivery→Core notification-action；Web 不接手配送。

## Settings 與缺口

保留 original main.ts 的六類 DOM/CSS：助理 assistant（profile/model/thinking）、對話與記憶 conversation（History/Memory）、語音與感知 perception（camera/screen/mic，scope fence）、工具與權限 tools（唯讀ToolPolicy）、桌寵與外觀 pet（outfit/expression/game/ignore mouse/reset/move/retry）、進階診斷 diagnostics（runtime/source/local presentation preferences）。缺contract的restart/stop/Mail refresh disabled。原控制位置不重設計；所有native interaction仍待驗。

未知 mutation 不自動重送，broker 保守阻擋後續 mutation，需人工查核／重建候選 session；目前沒有自動 reconciliation 功能。Tool writes、Mail body/refresh、Study jump、未具完整contract的lifecycle誠實不可用。沒有第二 business manager、DB/query、WS、tray、notifier 或 Electron Work UI。

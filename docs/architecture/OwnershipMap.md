# Kuro 責任地圖

2026-10-09 source 現況；正式採用狀態見 [G8Checkpoint](../agent-runs/qt-ui-convergence-20261007/G8Checkpoint.md)。Source checks 與桌面 acceptance 分開。

| 能力 | Canonical owner／source | Consumer 與邊界 |
| --- | --- | --- |
| 啟動、second launch | launcher_qt.py | visible Qt、QtActivate event；無 WorkPanel activation |
| Tray、close、quit、restart | qt_app.py | Qt；無 Electron tray |
| Service lifecycle | qt_controller.py、CoreRuntime、MailPollerRuntime | 既有 owned child handles；不操作共享中央 Voice |
| Chat、attachments、history UI | Qt + qt_chat_client.py | qt-primary WS；文字不依賴 Pet |
| Conversation、tools、policy、memory truth | Open-LLM-VTuber runtime | Qt 是 UI；tool result/persona 不給權限 |
| Core API host | core_app.py、api_server.py | Launcher/Qt；token 不給 Pet |
| Schedule state、quiet、lease、retry | schedule_* | Core SQLite schema 3 |
| Notification display | qt_notifications.py | claim → authorize → Qt showMessage → ack；unknown 不重播 |
| Work、Attention、Today | Core work_*、today_*、attention_* | /v1/today → Qt Today；無 Electron classifier |
| Mail provider、rules、preferences | local_mcp/mail_tools_server.py | policy 不變；explicit mail.refresh producer |
| Mail background polling | mail_poller_runtime.py → local_mcp/mail_poller.py | Launcher 一個 owner；private lock 防雙 poller |
| Mail status/work handoff | mail_status_handoff.py、mail_work_handoff.py | bounded atomic writers；Core bounded readers |
| Study truth／projection | external producer／Core adapters | Core GET 不 refresh，不複製 progress algorithm |
| Live2D、motion、expression、audio、geometry | pet-electron | 一個 Pet BrowserWindow，pet-local :23567 |
| Media capture | Pet capture → Qt submit | Pet 無 conversation trigger；history binding、防 replay |
| 模型 descriptor | Launcher presentation_state → set-presentation | local-model path allowlist；無 :23568 poll |
| Market truth | OMI | Kuro 保留來源限制，不自行重判市場 |
| Central Voice | 外部 runtime | Kuro 只用既有 consumer，不 stop/restart |

## 已移除與未完成

WorkPanel/Reader/Briefing renderer/HTML/preload/IPC/control routes、Qt dead methods、Launcher Control server、Electron business startup 均沒有可達 production consumer。完整 imports/require/routes/HTML/preload/IPC/config/tests/fallback/bridges inventory 見 [G7Checkpoint](../agent-runs/qt-ui-convergence-20261007/G7Checkpoint.md)。

35 個 manifest 檔案中 10 個因 OS access denied 尚在磁碟；這是 deletion blocker，不是另一 owner。Core Today、Mail/Study bounded contracts、Schedule fencing、Qt history/memory 路徑維持。沒有新增 service、cache 或 gateway。

Rollback 必須恢復同一組 source/consumer，不能同時啟用雙 owner。使用本機 ignored source archive 保留被刪除檔案的既有 WIP；歷史 Git HEAD 本身不足以還原本輪起點。

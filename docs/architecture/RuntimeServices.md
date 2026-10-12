# Runtime services

2026-10-09 source 現況。G8 尚未正式 ACCEPTED，詳見 [checkpoint](../agent-runs/qt-ui-convergence-20261007/G8Checkpoint.md)。

| 服務 | 設定入口／預設 port | Lifecycle owner | Readiness 證據 |
| --- | --- | --- | --- |
| Qt Desktop | launcher_qt.py，named mutex/event | 本機使用者／Qt | visible window、second launch、tray／quit 必須實機驗收 |
| Conversation Runtime | Open-LLM-VTuber，23456 | Launcher | profile/session identity、qt-primary WS、文字回應 |
| Pet Electron | pet-electron/src/main.js，23567 | Launcher child | service/protocol/PID/instance/root；renderer/model readiness 另外判斷 |
| Core | kuro_core_service.py，23569 | CoreRuntime | kuro.core.api.v1、PID/instance/root、nested Schedule schema 3 |
| Mail poller | local_mcp/mail_poller.py | MailPollerRuntime | configured enabled、owned handle、private OS lock |
| Bridge | 既有 bridge config | Launcher | 既有 health/contract |
| Central Voice | 外部設定，18890 | 外部管理者 | Kuro 不 stop/restart，不把 TCP listener 當推論 readiness |

`:23568` 已沒有 canonical listener 或 config。Pet 每五秒 capability refresh 不連此 port；Pet child 不接收 Core/Launcher token 或 Mail handoff env。

## Startup 與 teardown

Qt 首次啟動可见，second launch 喚回同一 Qt。startup_auto_start=false 仍顯示 Qt，但不自動啟動 profile。Core/Mail 在現有 profile startup owner 啟動，不隨 Pet window 建立而偷偷啟動。Qt Chat 透過 Runtime，Pet crash/absent 不改成 Electron conversation frontend。

X 隱藏至 tray；tray unavailable 時保留視窗。明確 Quit/restart 停止 Qt timers、notification worker、chat connection 與 owned child handles。Central Voice 共享服務不在 teardown 範圍。

Core 先 bind、再檢查 DB lease/schema；unknown listener 不 adopt/kill。Core/Mail settings 是 handoff enabled/path/TTL/size 的唯一 config；目前 Mail/Study 均 disabled。驗收必須分開記錄 disabled、configured missing、current、stale、provider failed；不得為展示而啟用私有 provider。

## 通知

Core 擁有 notification eligibility、preferences、quiet hours、lease、revision fence 與 audit。Qt 只執行 claim/authorize/display/ack；showMessage 返回只證明 OS API handoff，不能證明使用者看見通知。Crash、timeout 或未知送達不得直接重播。

## 本輪 runtime 證據

隔離 Core child/HTTP、Qt offscreen、loopback WS 已驗證；正式常駐 stack 未啟動。隱藏 Electron fixture 的 renderer/GPU 子程序啟動失敗，實際 Live2D／裝置／tray／通知／cold boot 尚未通過。[人工驗收](../agent-runs/qt-ui-convergence-20261007/G8ManualAcceptance.md)提供具體步驟，不修改 logon/registry。

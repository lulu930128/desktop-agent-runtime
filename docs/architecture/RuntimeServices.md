# Runtime services 與生命週期

下表是 `kuro_launcher.settings.yaml` 與 source 的預設設定，非即時 listener inventory。改設定後必須重新核對 effective config；不能只按 port 停程序。

| 服務／入口 | 預設位址 | Lifecycle owner | Identity／驗證面 | 停止與降級 |
| --- | --- | --- | --- | --- |
| Qt Launcher／`launcher_qt.py` | 無公開服務 port | 本機使用者啟動的 Launcher | executable、root、profile、source revision、child handles | 日常 Work Panel 與背景 operator 分工；shutdown 清理自有 child |
| Launcher control／`work_panel_api.py` | `127.0.0.1:23568` | Launcher | 每次 session bearer token；受限 API；Electron main 保存 token | renderer 不持有 token；特定 writes 經原生確認 |
| Kuro Core／`kuro_core_service.py` | `127.0.0.1:23569` | `CoreRuntime` | `/status` 帶 token；service `kuro-core`、contract `kuro.core.schedule.v1`、schema 3、PID、instanceId、sourceRoot | 優先 `/shutdown`，失敗僅停止持有 handle 的 child；未知 listener 拒絕沿用 |
| Pet control／Electron `src/main.js` | `127.0.0.1:23567` | Launcher 管 child；Electron 管 windows／tray | service `kuro-pet-control`、protocol、PID、instance、renderer readiness | 沿用／關閉前驗 identity；隱藏視窗不等於程序停止 |
| Conversation／Open-LLM-VTuber | `127.0.0.1:23456` | Launcher `services.py`／controller | executable、fork source root、readiness、`/client-ws` | LLM 失敗不應失去 Schedule／Work Panel；不能用 HTTP 200 代替對話驗收 |
| Bridge／`bridges/deeplx_bridge.py` | `127.0.0.1:1188` | Launcher orchestration | effective config、child/listener、對應 translation／spoken contract | 保留原文與錯誤，不自行補 domain 結論 |
| Central Voice Runtime | `127.0.0.1:18890` | 外部中央工作區 supervisor | `/health` 的 `voice-runtime`／protocol 1、selected voice、model_loaded、last_inference | Kuro 僅 consumer；不停止、重啟或新增第二引擎；不可用時文字降級 |

`9981` 僅是 legacy 設定回退值，舊引擎已移除；不能只改 port/mode 宣稱可回退。不要使用 `9881`；`18790` 屬其他服務。`local_translator/server.py`、`compose.yaml`、`00_kuro_bootstrap.ps1` 是 helper／歷史實驗，不是現行預設 stack。

## Core 的正式啟動鏈

`QtLauncherController` 建立 `CoreRuntime`；建立 Electron child environment 時呼叫 `start()`，再傳 `KURO_CORE_URL`、`KURO_CORE_TOKEN`、`KURO_CORE_INSTANCE`。Token 只經程序環境到 Electron main，不進 renderer、argv、文件或 Git。

`ScheduleServer` 先取得 exclusive listener 與 `<db>.service.lock`，再執行共享 schema initialization。啟動後背景 worker materialize occurrences 並計算 notification。Launcher 比對 PID、sourceRoot、instance、schema／contract；Electron 每次 call 驗證 service／contract／schema／instance。

DB lease 防止兩個正常 ScheduleServer 共用 DB；它不攔截任意 Python／SQLite writer。`materialization` 與 `notificationScheduler` 是獨立狀態，不能將 identity 正確當成 scheduler 全部正常。

## 核對與恢復順序

1. 讀取目前 settings 與 Launcher component log，確認 enabled、port、DB 路徑與 profile。
2. 核對 exact executable、working root、owned PID／parent、listener 與 instance；確認 source／policy／renderer build 的採用版本。
3. 透過既有 owner 的診斷 surface 核對 readiness。Core `/status` 需要 token；不要把 token 貼入 shell history 或輸出診斷檔。
4. 只重啟已確認的 component；Central Voice 交由其 owner 管理。重啟後再次驗證 identity、persisted state、API、UI 與必要 provider evidence。

`GET :23567/status` 只提供該 surface 的狀態；`GET /briefing` 包含私人 snapshot，不能保存或 commit 原始回應。單一狀態碼無法證明工具、語音與全部功能正常。

## 證據範圍

- Source：本輪核對入口、imports、設定及 lifecycle；未啟停正式程序。
- Schedule adoption：引用 [2026-09-12 M4–M6](../agent-runs/kuro-local-schedule-core/Progress.md)，包含當時正式 DB、重啟與配送證據；不是本日 live check。
- MCP：正式 security source 已存在，A8 未全部完成，見 [M0 Progress](../agent-runs/mcp-trust-security-m0/Progress.md)。
- Voice：本輪 targeted checks 與歷史合成／播放證據分列於 [TTS Progress](../agent-runs/tts-lifecycle-20260913/Progress.md)，人工聽感另驗。

資料保存與 rollback 見 [CorePersistence](CorePersistence.md)；產品目標不取代上述實際接線。

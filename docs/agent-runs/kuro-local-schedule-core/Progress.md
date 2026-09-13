# 本機時間表交付與複查紀錄

## 最新交付：M4–M6（2026-09-12）

使用者授權「繼續把後面都完善」，並明確允許重開桌寵。M4 介面、M5 提醒與 M6 本機採用已完成下述驗證；使用者主觀體驗複查仍由使用者進行。以下歷史 M0–M3 區塊保留當時狀態，不代表目前設定。

| 階段 | 已完成結果 | 證據 |
| --- | --- | --- |
| M4 | Core 時間表 CRUD、日期範圍、系列範圍、完成／恢復／略過、草稿衝突、提醒偏好；退出 legacy Calendar | 正式工作面板新增成功；隔離 Electron DOM、窄視窗與 screenshot；Calendar cutover regression |
| M5 | schema 3、quiet／snooze／catch-up、lease／fencing、dispatch audit、Electron OS 配送 | fake-clock、並行 claim、ack 遺失、取消競態；正式實例 ready → claimed → dispatching → delivered 各 1 次 |
| M6 | Core enabled、正式 Launcher adoption、正常關閉與一次程序樹 crash／重啟、持久化、文件／回退 | 正式 DB quick_check=ok、schema=3；重啟後安排仍在、delivered 未重送；Chat runtime 重新 listening，Mail／Study 原 snapshot 仍可讀 |

### 本輪執行結果

- `test_schedule_*.py`：39 tests PASS，包含 API post-commit projection failure regression。Core 啟用後將舊 disabled-only 測試改成明確關閉設定的回退驗證，再完整通過。
- `test_kuro_core_*.py`：16 PASS；`test_work_panel_api.py`：6 PASS；`test_pet_lifecycle.py`：6 PASS。共 67 Python tests。
- `core_client.test.cjs`：4 PASS；`schedule_notifications.test.cjs`：2 PASS；`schedule_cutover.test.cjs`：1 PASS。共 7 Node tests。
- `npm run check:renderer`、`npm run build:renderer` PASS；Python compile、Electron node check PASS。
- `tests/schedule_renderer_smoke.cjs`：Electron exit 0，12 個情境 PASS：空清單、提醒子服務失敗、今天跨午夜換日、590px 長標題、跨日 ongoing、雙提交、409 草稿、明確重讀版本、完成／恢復、offline、restart persistence、取消。
- 該 smoke 使用 temporary profile／DB／port，真實 SchedulePanel、preload、restricted IPC、HTTP 與 Core 子程序。不是正式資料證據。產物：`launcher_logs/schedule-validation/{result.json,narrow-schedule.png,conflict-draft.png,offline.png}`，已檢視截圖，忽略於 git。
- Build 原有 Live2D script 未加 type=module 警告仍存在，未新增依賴或修改 Live2D。

### 正式 runtime 證據

- YAML `core.enabled=true`、23569、Asia/Taipei；正式 DB `local_state/core/work.sqlite3` schema 3。runtime 在啟動時驗證 Core contract、PID、sourceRoot、instance。
- 第一次正常關閉舊 Qt 控制台後，以 `launcher_qt.py --work-panel` 啟動：Launcher 63452 → Core 22916／Electron 54360／LLM 28780。
- 原生工作面板建立 `[驗證] 本機時間表與桌面通知`：全天 9/12–9/13（exclusive）、14:00 提前 10 分鐘、desktop channel。Core 持久化配送 audit 顯示 delivered；這是 Electron show callback 的 OS 接受證據，未宣称使用者已閱讀或已看到 toast 截圖。
- 第二次控制台 reveal 有 handled log 但沒有可操作視窗，改以再次核對的 Launcher 63452 exact process tree 停止來驗證 crash recovery；沒有使用 image-wide kill。
- 重新正式啟動後：Launcher 62944 → Core 14860／Electron 11516／LLM 33868，各自預設 port listening。安排仍存在，delivery/audit 各階段仍各 1 筆，未重送，SQLite quick_check=ok。
- 共用 Central TTS 18890 從頭到尾維持 PID 28380，parent 47888，未停止。
- 正式 UI 與既有 Mail／Study snapshot、Chat 連線恢復已核對；沒有發出新的 LLM 查詢、外部 Mail refresh 或 study provider 更新，不把舊 snapshot 說成最新 provider 證據。

### 邊界與限制

- 本次完成 local schedule adoption，Observation／一般工作優先序仍在原本 shadow migration 階段。
- Google Calendar／OAuth、語音通知、AI 自動排程寫入未接入。
- OS 通知和 SQLite 無法原子提交，unknown 不自動重送；實體睡眠／喚醒以 fake-clock 等價情境測試，未讓使用者電腦實際休眠。
- 正式環境不保留可操作的測試安排；取消保留 audit。未 commit／push。
- 測試項目以單次取消結束：occurrence cancelled=1、通知 dismissed，正式今日 view items=0、coverage=complete。最後透過既有 reload-frontend command 採用含午夜／提醒失敗提示的最後建置。
- 操作、故障診斷與保留資料的回退方式見 [Usage.md](Usage.md)。

## 歷史：前四階段交付

2026-09-12（Asia/Taipei）。使用者授權的前四階段已完成 source／targeted tests／隔離 service 驗證，停在 M3。

## 已完成範圍

| 階段 | 結果 | 證據 |
| --- | --- | --- |
| M0 | 完成 | [Contract.md](Contract.md) 定義 item、API、時間、系列、ownership、錯誤、設定與回退 |
| M1 | 完成 | schema 2 migration／backup／restore、current＋revision、冪等、並行衝突、完成與例外保存 |
| M2 | 完成 | interval overlap、all-day、deadline、過期未完成、DST、weekly/monthly/count/until、bounded cursor、系列拆分、只讀 view |
| M3 | 完成 | loopback API、session token、exclusive port／DB lease、Launcher child lifecycle／identity、Electron restricted IPC |
| M4 | 未開始 | 工作面板 CRUD／新清單與 legacy Calendar cutover |
| M5 | 未開始 | 通知 eligibility／quiet hours／snooze／delivery 狀態機及桌面配送 |
| M6 | 未開始 | 正式 runtime 啟用、產品操作與通知驗收 |

## 驗證結果

以下均為本輪實際執行；測試使用 synthetic payload 與 temporary DB，不讀私人行程、不呼叫外部 provider。

| 指令／檢查 | 結果 |
| --- | --- |
| `python -m unittest discover -s tests -p 'test_schedule_*.py'` | 28 tests PASS（本 repo envs/kuro-llm310/python.exe） |
| `python -m unittest discover -s tests -p 'test_kuro_core_*.py'` | 16 tests PASS |
| `python -m unittest discover -s tests -p 'test_pet_lifecycle.py'` | 6 tests PASS |
| `python -m unittest discover -s tests -p 'test_work_panel_api.py'` | 6 tests PASS |
| `node tests/core_client.test.cjs` | 4 tests PASS |
| 變更 Python 的 `py_compile` | PASS |
| main.js／briefing-preload.js／core-client.js 的 `node --check` | PASS |
| `npm run check:renderer` | PASS；同步補齊 fallback bridge 的 schedule unavailable 回應 |
| `git diff --check`、新增文件 UTF-8／連結／whitespace | PASS |

共 56 Python tests、4 Node tests。沒有跑 renderer build、實際 Electron UI、真實通知或正式 runtime，因本批停在 transport，沒有 M4 可視改動。

`node --test` 原先被環境禁止建立 test runner 子程序（spawn EPERM）；改用 `node tests/core_client.test.cjs` 執行同一套 node:test，4 個測試確實執行並通過，沒有略過測試。

## 隔離 runtime 證據

- `test_schedule_api.py` 使用 loopback ephemeral port 驗證 JSON API、auth、Origin 拒絕、malformed input、409 conflict、service restart 與 persisted view。
- `test_schedule_runtime.py` 真正使用 Launcher 的 CoreRuntime 啟動 repo Python 子程序，驗證 PID、sourceRoot、session identity、停止／重啟及資料恢復。
- 第二個相同 port listener 啟動失敗，不建立另一份 DB；同一 DB／不同 port 也被 OS lease 拒絕。
- token 不出現在 subprocess argv；Electron 每次請求先驗證 service identity，其他 window/subframe IPC 被拒絕。
- 測試子程序與服務已由 cleanup 關閉，正式 service 未啟動。

## 測試中修正的問題

- Windows HTTPServer 預設 reuse 行為不足：改 SO_EXCLUSIVEADDRUSE，禁止同 port 第二個 owner。
- 既有 schema creation 使用 executescript 有 implicit commit：改 transaction-bound DDL，避免半完成 schema。
- 單次完成對通知撤銷的範圍太大：改依 this/future/all scope 撤銷。
- Core lifecycle 的 log handle 改由自己持有與明確關閉，避免重啟時留下檔案 handle。
- Core readiness 不只檢查 schema number，也驗證必要 table/column。

## 目前設定與資料邊界

- `core.enabled: false`。23569 只在 YAML 定義；啟動時重新驗證 owner。
- 未建立／升級正式 `local_state/core/work.sqlite3`；正式路徑已 gitignore。
- 未改 Mail snapshot builder 或 Calendar consumer，兩者留 M4 一起 cutover，避免半途移除現有路徑。
- preload/TypeScript 僅新增 transport，畫面仍沿用既有資料。
- 未啟用 Google Calendar、OAuth、語音、通知或外部寫入。
- 未 commit／push；所有本批變更保留供複查。

## 已知限制與後續

- 長年 recurrence catch-up 分批；coverage incomplete 必須由 M4 UI 明確顯示。
- 帶 exception／已完成歷史的時間規則修改若無法安全映射，回 conflict；M4 需呈現可理解的處理流程，不自動丟失資料。
- Notification preferences 與 delivery schema／invalidation 已具備，尚無實際通知 scheduler。`/status` 明示 not_implemented。
- Core opt-in 接線驗證通過不代表已採用正式 runtime；舊 Electron process 不會自動獲得新 session connection。
- 原 README／docs 整理工作沒有被本批覆寫；本次實作開始時只剩本任務計畫未追蹤。Roadmap 僅補局部採用說明。

下一步由使用者複查 M0–M3，確認後再進 M4；本輪不自行擴大範圍。

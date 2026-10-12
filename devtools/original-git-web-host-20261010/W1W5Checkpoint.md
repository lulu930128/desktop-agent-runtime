# W1–W5 實作與驗證 checkpoint

2026-10-10。已實作到 W5 的 feature-off candidate；**W1 仍 FAIL，W2–W5 不宣稱 Gate PASS**。未做 W6/W7、正式切換、Widget 刪除、service restart、commit 或 push。docs/agent-runs 目錄新增 checkpoint 寫入失敗，故交付於本 task 目錄；未改 ACL。

## Gate 分項

| Gate | Code implemented | Tests passed | Windows runtime independently verified | Blocking |
| --- | --- | --- | --- | --- |
| W1 | 真實 Today selectors、computed geometry/font/line-height/text rect/input bounds/Intl；必要節點缺失即 FAIL；deterministic comparison、Windows relay | geometry 1、deep geometry 2、deep comparison 3、parity collection 6、diagnosis 3、smoke helper 8，均 exit 0 | **否**；既有真實 Edge/Qt 證據保留，未新增 deep measurement 實機證據 | **FAIL**：Today +3px、native date intrinsic width 根因未證明；第二 viewport、三 DPI、History/native interaction/security 未完成 |
| W2 | 單一既有 QMainWindow 的子 WebView；custom scheme/allowlist/off-record/permission deny；明確 QWebChannel 協定；handshake 後才 import main | actual build + AssetBundle round-trip/逐檔 tamper 4；protocol suite；typecheck/build exit 0 | **否**；正式 QtWebChannel import exit 1 | custom scheme、root JS、CSP/WebChannel/navigation/security runtime **UNVERIFIED** |
| W3 | 同一 QtRuntimeChatClient Chat/interrupt/tool timeline/History CRUD；identity/revision/request fences；GUI queued worker completion；附件/IME/unknown | candidate、frontend；真正 Qt client→disposable WS 與 Core HTTP 2 項；G3/R1/R4 exit 0 | **否**；Qt Essentials offscreen WS 不等於 WebEngine/native UX | 串流外觀、History drawer、native picker/IME/capture/confirmation 待驗 |
| W4 | 原六 Settings 綁既有 controller；profile 等 effective WS；Memory digest/actor/260字/confirm；Tools 唯讀；Pet/perception 原 gateway | candidate/R2/G4/G5/G6 及 Node owner suites exit 0 | **否**；未操作個人 profile/memory/裝置 | 真實 profile restart、native確認、裝置權限與 Pet 未驗；缺 contract 的 lifecycle controls disabled |
| W5 | Core Today canonical order shim；Schedule revision/key/confirm；materialize 永拒；受控 Core 通知 command 沿用 transaction/receipt；Mail/Study truthful unavailable | adversarial order、materialize negative、通知 9（HTTP/409/concurrency/replay）、Schedule 44、R3/G8 exit 0 | **否**；全為 synthetic/disposable，Core 未 adopt/restart | runtime acceptance 未完成；Mail body/refresh、Study jump 缺 canonical contract |

最終 **27 個 test suites、272 tests 均 exit 0**；typecheck、原版 build、candidate build 各 exit 0。正式 Addons probe 為獨立 **exit 1 blocker**。逐 suite 實際 argv/cwd/count/exit、source SHA、檔案 inventory 見 `W1W5Evidence.json`；24 methods 對照見 `W1W5MethodCoverage.md`。

## W0、檔案與證據

- 本輪開始 main、HEAD `af83df273602be3a616d6567855ea71d61a9ace7`、404 dirty entries、index 空；未沿用 Plan 的舊 412 計數。
- `.runtime/w1-w5-20261010T080647Z/Before.json` 保存 1223 個現存非 ignored source/WIP 檔案 SHA、status/index 與六 original SHA。六 originals 另比對 Git `995c23c7c8d1be62000229d58610d2214f3bb745:pet-electron/renderer/...` bytes。
- 既有檔案僅改六個：本目錄 `geometry.js/capture_parity.py`、`kuro_launcher/qt_controller.py`、`kuro_core/schedule_api.py/schedule_notifications.py`、`tests/test_g8_runtime.py`。各 preimage 已保存，其餘 baseline SHA 不變。既有 G7 35 路徑仍 absent。
- `ScopedPreimageDiff.patch` 相對本輪 preimage，避免把 HEAD 以前的 dirty WIP 混入本次 diff。新檔 inventory/SHA 另列 Evidence；未修改六份原始 main/styles/model/types/schedule/html。
- 舊 `W1TodayParityCheckpoint.md`、`diagnose_parity.py`、PNG/JSON 均未覆寫。baseline 未全面 hash ignored runtime evidence，不能將 source snapshot 稱作完整 runtime 備份。

## W1 保留 FAIL 的原因與 Windows relay

既有 `.runtime/parity-msedge-1-20261010T071240461324Z/ParityResult.json`：Edge154/Qt Chromium140；Today local-schedule.y 493.921875/496.921875，差3px，changed pixels5.08%；Chat/Settings DOM/tokens 等同但像素差1.75%/2.11%。這些資料不證明 Today root cause 或全 Gate PASS。

instrumentation 對照 original DOM：`.today-frame > header`、header 下 `.section-kicker/.today-question/.today-summary`、`.today-primary > section > .block-heading`、`.priority-list/.empty-state/.local-schedule` 與 date input。量測 margin/padding/border/font/line-height/text range/client/offset/scroll width，不動 DOM/CSS margin/input type。缺必要節點 capture/comparison 都 FAIL；synthetic DOM tests 不等於實際 glyph fallback/native shadow internals 已量到。

本輪 isolated `.venv` 的 `ImportProbe.json`：Codex 身分讀取 PySide6/PIL/playwright 為 PermissionError13。正式 `envs/kuro-llm310` probe exit1：`ModuleNotFoundError: No module named 'PySide6.QtWebChannel'`。沒有安裝 Addons、改 ACL、關 sandbox/GPU 或啟動 GUI。

一般 Windows 使用者桌面 PowerShell：

```powershell
Set-Location C:\project\desktop-agent-runtime
& .\devtools\original-git-web-host-20261010\Invoke-W1WindowsRelay.ps1
```

relay 先建立新 smoke receipt，再跑 Edge scale1/1.25/2，各含1280×720與1380×860；`--collect-geometry-drift` 保留 FAIL，不放寬判定。它是 W1 preview relay，**不是 W2 custom scheme 驗收**。新 evidence 前不得說 root cause resolved。

## W2 修正與安全邊界

manifest 改在 Vite `writeBundle` 讀取最終 bytes；包含 work-panel.html、兩個 JS、原 CSS 四資源。AssetBundle actual round-trip 比對全部 served files，逐檔 tamper 拒絕；入口必備條件未放寬。無 sourcemap；module graph 禁 preview-bridge/synthetic.json/qt.ts/baseline.ts。qwebchannel.js 由 Qt resource 在 host 注入記憶體 allowlist，不開任意 qrc/file access。

WebChannel 只註冊 Wire 的 submit/response/event，不公開 worker slots。GUI 先 snapshot identity，worker completion 以 queued signal 回 GUI fencing。ID 去重/上限、typed allowlist、timeout、unknown 不自動 retry；pending ID 重送（含 malformed contract）不提前 complete 或解除 mutation fence。

`create_candidate(enabled=False)` 不 import Addons。非 fixture 路徑要求 W1/W2 readiness＋既有 owner exclusive handoff；正式 launcher 未引用此 module。無第二 MainWindow/tray/WS/notifier。scheme 必須於 QApplication 前註冊；`kuro-work://app/work-panel.html` 與 root `/qwebchannel.js` **未實機驗證**，不可由 AssetBundle 通過推論可用。實作參考 [Qt scheme](https://doc.qt.io/qtforpython-6/PySide6/QtWebEngineCore/QWebEngineUrlScheme.html) 與 [Qt page permissions](https://doc.qt.io/qtforpython-6.10/PySide6/QtWebEngineCore/QWebEnginePage.html)；正式版本相容性仍待驗。

## W3–W5 裁決

- 普通 sendText/createHistory/selectHistory 不加 OS confirm，以 UI 意圖、範圍 fence、下游 policy 管理；delete/memory/schedule/profile 及 Pet/perception 變更保留 native confirm。renderer confirmed:true 不是授權；accepted 不冒充完成。
- 原 model.priorityItems 會排除 normal/calendar、按 level 重排；後端 projection 不足。candidate resolver 只替換 main 的 model import，原六檔不動；shim 顯示 Core 原序前五項（原版卡片上限），來源清單保留完整順序，不改 level/評分/去重。adversarial fixture 證明 normal/不同 level 的順序；實際 WebEngine DOM 未驗。
- original SchedulePanel.refresh(true) 的 materialize 確實寫入：controller POST→Core `_advance`→ScheduleStore.advance write transaction，插 occurrence/update cursor。增量去重不是授權；adapter 永拒，即使 confirmed:true。既有 Core scheduler owner 自行 materialize，Web read 不代 tick/write。
- 通知 read 返回 opaque content revision；consumer command 僅 dismiss/snooze/preferences，GUI confirm＋revision/key。Core 沿用 schedule_mutations 與既有 notification action transaction 原子驗證/receipt；同 key/payload replay 不重 audit，不同 payload/stale revision 衝突；沒有 schema migration/新 worker/notifier。claim/authorize/ack 留 QtScheduleDelivery。digest 是內容版本，不是全域 monotonic counter；舊 Core 未 advertise contract 即 disabled。
- Tool policy write、Mail refresh/body、Study jump、缺安全 contract 的 lifecycle action 都 unavailable/disabled，未回接 Electron IPC/provider/私有 DB。Today 保留 complete/sourceStates 各軸/timestamps/limitations；read failure 保留舊資料時明示 transportStale。
- 使用 productized-project-workflow、frontend-design 及找到的 ui-ux-pro-max；`design-taste-frontend` 在已搜尋 skills roots 不存在。未改 CSS/spacing，guards 使用原 DOM/classes；不宣稱三項 skill 完整視覺驗收。

## 真實測試紀錄與限制

原始 stdout/stderr、每 command argv/cwd/exit/count 在 `.runtime/w1-w5-20261010T080647Z/validation-1` 至 `validation-6`。同 suite 取最後結果，先前失败仍保存。

- notification 初次8 errors：fixture 把 datetime 傳給既有 ISO-string now contract；僅修 fixture、不放寬 Core。加入真 HTTP/409 測試後9/9。
- G8 初次1 failure：廣義 work-panel scan 匹配 candidate 的兩個精確 HTML literal。僅這兩處例外，仍掃其餘 legacy token，新增 assert Qt origin/正式入口未引用；獨立驗 G7 absence，沒有用字串拼接隱藏 consumer。
- 補修 pending duplicate ID mutation fence 並加 negative test 後 candidate41/41、actual Qt WS/HTTP2/2 重驗。
- 27 suites272 tests 是 synthetic contract/Qt Essentials/loopback/disposable DB，不能替代 native WebEngine/permission/provider acceptance。

重跑（output 必須新目錄）：

```powershell
.\envs\kuro-llm310\python.exe -B devtools/original-git-web-host-20261010/validate_candidate.py --output devtools/original-git-web-host-20261010/.runtime/reviewer-validation-new --only qt_web_candidate qt_web_assets qt_web_transport web_notification_commands
```

不帶 --only 為本輪 bounded31 commands；缺 formal Addons 時 runner exit1，必須分開看每項。Python socket guard 禁外部與正式 ports，TEMP/TMP 在 repo disposable 目錄；不隱含 Electron GUI/LLM/private history/provider。

## Rollback／停止點

保留原 launcher/Widgets 即目前 rollback；candidate OFF，Core 新 route additive，tray API 保留。若後續 reviewer 要撤回本輪變更，只能逐 hunk 對照 ScopedPreimageDiff/preimage SHA，先確認沒有後續 WIP；新檔另審，不能整庫 checkout/reset。

接下來由獨立 reviewer 審查結果與补 W1 root cause/W2 scheme-security-native evidence；未達 W1/W2 readiness 前禁止正式切換。W6/W7 未開始。

## 最後一次逐項 exit

| Suite/command | Tests | 實際 exit | Receipt |
| --- | ---: | ---: | --- |
| typecheck | 不適用 | 0 | validation-1 |
| original-build | 不適用 | 0 | validation-1 |
| candidate-build | 不適用 | 0 | validation-1 |
| formal-addons | 不適用 | 1 | validation-1 |
| qt_web_candidate | 41 | 0 | validation-6 |
| qt_web_assets | 4 | 0 | validation-1 |
| qt_web_transport | 2 | 0 | validation-6 |
| web_notification_commands | 9 | 0 | validation-4 |
| schedule_core | 19 | 0 | validation-1 |
| schedule_notifications | 10 | 0 | validation-1 |
| schedule_api | 6 | 0 | validation-1 |
| schedule_runtime | 9 | 0 | validation-1 |
| g3_conversation | 27 | 0 | validation-1 |
| g4_qt_core | 15 | 0 | validation-1 |
| g5_desktop | 17 | 0 | validation-1 |
| g6_pet_boundary | 11 | 0 | validation-1 |
| g8_runtime | 3 | 0 | validation-3 |
| r1_history_parity | 22 | 0 | validation-1 |
| r2_settings_parity | 16 | 0 | validation-1 |
| r3_today_schedule_parity | 6 | 0 | validation-1 |
| r4_history_transport | 2 | 0 | validation-1 |
| parity_collection | 6 | 0 | validation-1 |
| parity_diagnosis | 3 | 0 | validation-1 |
| w1_smoke | 8 | 0 | validation-1 |
| qt_web_frontend | 10 | 0 | validation-3 |
| g3_presentation | 7 | 0 | validation-1 |
| g5_desktop_owner | 3 | 0 | validation-1 |
| g6_pet_shell | 10 | 0 | validation-1 |
| test_geometry | 1 | 0 | validation-1 |
| test_deep_geometry | 2 | 0 | validation-1 |
| deep_comparison | 3 | 0 | validation-4 |

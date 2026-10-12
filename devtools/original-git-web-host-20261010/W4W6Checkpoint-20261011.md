# W4–W6 隔離工程檢查點

2026-10-11。停止於 **W6 dry-run / BLOCKED**，等待使用者檢查原始 Web 預覽；沒有開始 W7。瀏覽器原版視覺已由使用者於前輪確認，但不是 Qt 原生工程驗收。

`docs/agent-runs/kuro-original-web-cutover-20261010/Progress.md` 新增寫入遭檔案權限拒絕；未改 ACL 或反覆覆寫，進度完整保存在本 checkpoint。原 Plan 未修改。

## 本輪裁決

| Gate | 本輪實證 | 狀態 |
| --- | --- | --- |
| W1 | task `.venv` 一般與 `-I` import 都在讀取 `PySide6/__init__.py` 遭 PermissionError 13；PIL/playwright 同樣失敗，尚未進入 Qt DLL/GPU/render。Get-Acl 也拒絕讀取，無法確定實際 ACL 成因。 | 歷史 Today +3px/native date **FAIL 保留**；重驗 BLOCKED |
| W2–W3 | 候選資源與 broker regression、真正 QtRuntimeChatClient→disposable WS/HTTP 通過；沒有 native WebEngine/custom scheme/QWebChannel/permission/IME 新實證。 | Native UNVERIFIED |
| W4 | 四個 adapter 缺陷已修；新增 negative、真實 disposable Memory JSON/SQLite owner 測試。 | Feature-off source verified；native UNVERIFIED |
| W5 | Today/通知跨 context 快取已修；36 組 Today order/freshness/complete property cases；真 Core HTTP prepare/read/cancel/no-materialize、mutation replay/revision、通知 transaction 與 synthetic tray 配送。 | Feature-off source verified；native UNVERIFIED |
| W6 | AST 函式行號、import/reference、SHA、保留 owner 與 G7 absence inventory；guard tests 2/2。 | Dry-run 完成；實體 cutover/cleanup **BLOCKED** |

正式 `launcher_qt.py → KuroQtLauncherWindow._build_ui() → WorkCompanionView(QWidget)`、原 VBS、Qt tray、Conversation/Core/Schedule owner 都保留。沒有改 ACL/security/registry、安裝依賴、停用 Chromium sandbox/GPU、重啟正式服務、呼叫 provider、讀寫使用者 DB/history/memory/mail/voice、commit 或 push。

## 修正與 review findings

以下六個缺陷均由新測試在 preimage 重現，修正後通過。此為本 agent 的 source review，沒有獨立 subagent 或 native reviewer 背書。

1. `QtOwnerAdapter.dispatch.complete`：Memory refresh 失敗仍保留舊 reviewed snapshot；改成撤銷，後續 mutation 需重新讀取成功。
2. 同處：runtime status 失敗仍保留 captureAvailable；改成撤銷，不能靠先前裝置狀態開始 capture。
3. 同處：mic-submit 只驗外層成功與 capture 存在；改驗內層 `result.ok is True`，裝置拒絕不能送給 Conversation。
4. `_reconcile_profile`：值與新 context 相符，但 disconnected/not history-ready 仍回 effective；現在兩個 readiness 都必須成立。
5. `OwnerTransport`：Today 的 last-known snapshot 跨 context 沿用；現在 identity 變動清空，只允許同 context 的 stale fallback。
6. `makeOwnerBridge`：通知已審核 revision 跨 context 沿用；identity 變動撤銷 snapshot 與 write capability，需重讀。

Memory `changed:false` 原版已有「未變更」提示，不改成假失敗；260 字上限與 actor/content_digest/native confirmation 均保留。未知寫入結果不重送，仍需人工查核／建立新候選 session。

原始 Settings 六分類保持原 DOM/CSS：assistant→controller profile/effective WS；conversation→同一 History/Memory owner；perception→Pet capture/Qt submit；tools→唯讀 ToolPolicy、confirmation queue unavailable；pet→既有 gateway；diagnostics→既有 runtime/source status。原 `W1W5MethodCoverage.md` 的 24 methods ownership 仍適用。缺 canonical contract 的 Mail/body/refresh、Study jump、lifecycle command 不放行。

## 測試與隔離

證據根目錄：`.runtime/w4-w6-20261011T053420Z/`。`validation-1/Results.json`、`validation-2/Results.json` 保存每項完整 argv/cwd/exit/count/elapsed，旁邊為 stdout/stderr。**13 suites、130 tests 全部 exit 0**，另 typecheck/original-build/candidate-build 各 exit 0。

| Suite | Tests | Exit |
| --- | ---: | ---: |
| qt_web_candidate | 41 | 0 |
| qt_web_transport | 2 | 0 |
| qt_web_w4_w5（新） | 9 | 0 |
| qt_web_disposable（新） | 4 | 0 |
| web_notification_commands | 9 | 0 |
| qt_web_frontend | 12 | 0 |
| qt_web_assets | 4 | 0 |
| qt_web_w6（新） | 2 | 0 |
| schedule_core | 19 | 0 |
| schedule_notifications | 10 | 0 |
| schedule_api | 6 | 0 |
| schedule_runtime | 9 | 0 |
| g8_runtime（僅既有 synthetic suite，不是 W7） | 3 | 0 |

新 Python 9 tests 在保存的舊 adapter 上 **4 failures / exit 1**；Node 12 tests 在保存的舊 bridge 上 **2 failures / exit 1**。`NegativePreimageResults.json` 與兩份 `negative-preimage-*.log` 保存重現；以 process-local module substitution 載入 preimage，未覆寫 worktree。

`ImportCommand.json` 捕獲 task `.venv -I` 原生 import 的真正 process exit **2**；仍 BLOCKED。六份本輪 Python source 的 in-memory compile 與局部 `git diff --check` 通過；`ScopedDiff.patch` 對照本輪 preimage，避免把既有 WIP 混作本輪修改。

`validate_candidate.py` 的 Python socket guard 禁外網及正式 ports；TEMP/TMP 在 disposable repo 子目錄。新增 Memory 測試使用 factory temporary directory、真實 canonical JSON 與 derived SQLite，僅替換外部 runtime refresh；不讀正式設定。Core 測試使用獨立 schema-v3 DB、ephemeral loopback port、synthetic token，不啟動第二 scheduler。HTTP read/prepare/cancel/materialize-denied 前後 DB bytes 一致；mutate replay 只有一筆 item/receipt；stale revision 不寫入。原 tray claim→authorize→ack 由既有 QtScheduleDelivery 執行，測試 tray 為 mock，未顯示真通知。

重跑（必須選新 output）：

```powershell
Set-Location C:\project\desktop-agent-runtime
& .\envs\kuro-llm310\python.exe -B .\devtools\original-git-web-host-20261010\validate_candidate.py --output .\devtools\original-git-web-host-20261010\.runtime\review-w4-w6-new --only qt_web_w4_w5 qt_web_disposable qt_web_w6 qt_web_candidate qt_web_frontend qt_web_transport web_notification_commands
if ($LASTEXITCODE -ne 0) { throw 'Source validation failed; inspect Results.json' }
```

## W6 精確範圍與 rollback

`W6Inventory.json` 保存四檔 SHA、class/function start/end line、production/tests/frontend reference inventory；`w6_inventory.py` **只有讀取與新 evidence 輸出，沒有刪除或 cutover 功能**。

| 候選 | 未來允許的最小範圍 | 必須先解除的耦合 |
| --- | --- | --- |
| `qt_work_companion_view.py` | 原 Widgets presentation module | `qt_app.py` 的 WorkCompanionView、ComposerEdit、transcript_html imports/callers，以及 Widgets regression fixtures |
| `qt_work_companion_theme.py` | 原 Widgets theme module | view/theme imports 與樣式使用，不能刪共用 Qt window/tray 樣式 |
| `qt_app.py` | `_build_ui`、Settings/Chat/Memory/Pet/perception/tools builders 與僅服務 Widgets 的 render handlers，逐 symbol review | 保留 QMainWindow、single-instance reveal、close/tray、唯一 chat client/controller、task worker、confirmation、QtScheduleDelivery、lifecycle/timers；先遷移連線再移除 widget 屬性引用 |
| `qt_core_pages.py` | TodayPage/SchedulePage/CoreHealthPage 的 Widgets presentation | 先分離 MAIN_NAV_KEYS/SETTINGS_LABELS 的 consumers；CoreRuntime/QtScheduleDelivery/Store/API 不刪 |

還需審查 candidate bundle manifest/CSP、owner bootstrap、build entry/config、native resource graph、preview entry 與 tests 的去留。原六檔 reference 不成第二 production entry；不重新引入 Electron WorkPanel/Briefing/Reader 或 :23568。G7 manifest **35/35 absent**。

真正 cutover 前要求 W1–W5 每項 native evidence 與人工 approval；現有 Python readiness flags 或 source PASS 不足。切換只能在同一 Qt window 接 WebView、沿用既有 client/controller/tray/notifier，禁止雙掛。需重新驗證原始 hash、當時 WIP/preimage、exact runtime identity、所有 callbacks 和關閉行為，再另批精確删除。正式 VBS 本輪不改。

本輪無 production adoption 可回滾。候選修改的 preimage 在 `preimages/`；回退時先比對 FinalAudit SHA，逐檔／逐 hunk 還原本輪變更，不可 reset/clean/stash/checkout 全庫。未來正式 cutover 必須另存當時 launcher/Widgets 的 exact bytes，失敗只還原該批，不回退其他 dirty WIP，不改 DB。

## W1 一般使用者 shell 定位／安全修復選項

以下在**一般互動式 Windows PowerShell**執行，不需管理員，不改 execution policy 或 ACL。先測既有隔離環境：

```powershell
Set-Location C:\project\desktop-agent-runtime
$taskRoot = Join-Path $PWD 'devtools\original-git-web-host-20261010'
$qtPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$probeOutput = Join-Path $taskRoot ('.runtime\owner-import-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ') + '.json')
& $qtPython -I -B (Join-Path $taskRoot 'w1_import_probe.py') --output $probeOutput
if ($LASTEXITCODE -ne 0) { throw "Import BLOCKED; preserve $probeOutput" }
& (Join-Path $taskRoot 'Invoke-W1WindowsRelay.ps1')
```

若正常使用者也無法讀取原 `.venv`，**不要改 ACL 或覆寫它**。可另建一次性 user-owned env，使用 repo 已固定的 Qt 版本，只診斷依賴是否能在新目錄 import；此選項需下載套件，以下命令本輪未執行：

```powershell
$repairRoot = Join-Path $taskRoot ('.runtime\owner-qt-env-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ'))
$basePython = (Get-Command python -ErrorAction Stop).Source
& $basePython -m venv $repairRoot
if ($LASTEXITCODE -ne 0) { throw 'Fresh isolated venv failed' }
$repairPython = Join-Path $repairRoot 'Scripts\python.exe'
& $repairPython -m pip --isolated install --index-url https://pypi.org/simple --no-cache-dir 'PySide6==6.11.1'
if ($LASTEXITCODE -ne 0) { throw 'Fresh isolated dependency install failed' }
& $repairPython -I -B -c 'import PySide6; from PySide6.QtCore import qVersion; from PySide6.QtWebChannel import QWebChannel; from PySide6.QtWebEngineWidgets import QWebEngineView; print(PySide6.__file__, qVersion())'
if ($LASTEXITCODE -ne 0) { throw 'Fresh isolated Qt import still BLOCKED; preserve traceback' }
```

新 env import 成功只能定位舊目錄或 token 存取差異，不代表已證明唯一根因，更不是 W1 PASS。既有 W1 harness 刻意限定原 task `.venv`；不要改 sys.prefix 或 monkeypatch 躲過此 guard。新 env 若成功，下一輪先正式支援明確 env path/版本/receipt 再量測原 renderer。不要用空白 Qt window、headless、關 GPU、放寬 pixel threshold 替代 native acceptance。

仍缺 1280×720、1380×860 × 100/125/200% DPI × Chat/Settings/History/Today 的同源比較、Today +3px/date root cause、native picker/IME/confirmation、custom-scheme/security 與裝置驗收。

## 使用者預覽／停止點

本輪獨立 SYNTHETIC read-only original renderer：`http://127.0.0.1:64881/work-panel.html?view=chat`；Node PID **63016**，HTTP 200、loopback LISTENING 與 executable path 已核對，保留 server。`PreviewLaunch.json` 保存完整 argv/cwd/port/PID；舊 :4179 不停止。

控制工具失敗：`Restricted read-only access requires the elevated Windows sandbox backend`。獨立 Edge profile 啟動 PID 63644 後退出，stderr：`GPU process isn't usable. Goodbye.`，沒有可见 window proof；不是自動 approval 拒絕，沒有關閉 sandbox/GPU 或 headless 替代。

直接在正常瀏覽器開上述連結，檢查 Chat、Settings 六分類、Chat 的 History drawer、Today/Schedule；顯示 SYNTHETIC，mutations unavailable，沒有正式資料。若 server 已退出，可執行既有安全腳本（建立新 port/profile，只停止它自己建立的 server）：

```powershell
& 'C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010\Open-ReadOnlyBrowserPreview.ps1'
```

**停止於 W6 BLOCKED；等待使用者檢查，不做 W7。** 完整 changed-files/SHA、index/source/WIP 比對與最終 listener/HTTP 狀態見 `FinalAudit.json`。

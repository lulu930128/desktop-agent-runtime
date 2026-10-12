# W6 檢查點：W6.B/C PASS，正式 UI 採用尚未執行

## 2026-10-11 D/E/F 最新交付

已實作 existing-window 接線及 source／隔離回歸；真 native renderer exit49，因此正式 Widgets 保留、未刪除、W7 未開始。完整 receipts、正常桌面 relay 與 rollback 見 [W6FinalCheckpoint](W6FinalCheckpoint.md)。下方「D–F 未開始」保留為前輪歷史，不是目前結論。

## 最新：2026-10-11 官方 wheel overlap ownership 修復與正式安裝

**W6.B/C 已完成。** 正式 `envs/kuro-llm310` 已安裝 Addons 6.11.1；只完成 package prerequisites，不建立 QApplication、不啟正式 GUI。W6.D–F/W7 未開始，VBS／Qt UI owner／舊 Widgets／private backend 未改，沒有提權、ACL 變更、重啟、commit/push。

- 修復與保全 evidence：[w6-overlap-20261011T094355714164Z](.runtime/w6-overlap-20261011T094355714164Z/)。完整逐檔 overlap：[OverlapInventory.json](.runtime/w6-overlap-20261011T094355714164Z/OverlapInventory.json)；原始與嚴格重驗清冊為 `Overlap-before.json`／`OfficialOverlap-verified.json`。
- 正式成功 run：[w6-user-install-20261011T0956528942669Z](.runtime/w6-user-install-20261011T0956528942669Z/)。[PackageGate.json](.runtime/w6-user-install-20261011T0956528942669Z/PackageGate.json) 為 `PREREQUISITES_PASS`；[Preflight-after.json](.runtime/w6-user-install-20261011T0956528942669Z/Preflight-after.json) 為 `PASS_BEFORE_APPLICATION`，`applicationCreated=false`／`productionAdoption=false`。

### 原因與完整交集

17:38 原 run `.runtime/w6-user-install-20261011T0938079724671Z/` 的官方 download exit0，wheel **168,816,308 bytes**，SHA256 **`0d13c4dfd671b050a48e4f8d8ddc724b7248f9c0437e7fc47fdf316278572923`**；官方已保存的 PyPI metadata、archive SHA、內部 RECORD 均相符，backup 逐檔讀回通過。阻塞不是下載／admin 權限，而是舊 `wheel_contents()` 遇任何 existing file 就停止。

核對官方 wheel **1,313** 個檔案、正式 **125** 份 distribution RECORD 與一份 legacy setuptools metadata：共 **64** 個實際重疊（60 `.pyi`、3 `.py`、1 `py.typed`）。全部由 `pyside6_essentials-6.11.1.dist-info/RECORD` 單獨持有，版本／canonical path／RECORD SHA256／bytes／實際檔案 bytes 均吻合。完整清冊包含各路徑、owner RECORD、原檔／wheel 的 hash 與大小、`identical` 及逐檔決策；本次可排除 64、阻擋 0。不修改既有 numpy／Essentials 共三個重複 optional `.pyc` metadata，另存 `ExistingRecordDuplicates-raw.json`，所有 claims 仍保留於 gate lookup。

### 實際安裝與移除所有權

只忽略相同檔案仍會造成雙重 RECORD owner。依 [PyPA RECORD／uninstall 規格](https://packaging.python.org/en/latest/specifications/recording-installed-packages/) 及本機 pip 25.3 實作，採安裝前排除策略：

- 原官方 wheel 保留不動，新建本機 `pyside6_addons-6.11.1-1w6owned-cp310-abi3-win_amd64.whl`，移除 64 個 shared payload 及其 RECORD rows；其餘 **1,248** 個官方 payload 檔案 bytes 全部相同，重建 RECORD，新增 `W6_ORIGIN.json`。
- 本次安裝衍生 wheel SHA256：`1c6ebec9cdefb70231dd8de809060168bfabfcdbc020c8d8ed807d43d8237818`。`InstallWheelReceipt.json`／installed `W6_ORIGIN.json` 明確記錄官方原 SHA 與排除理由，不把衍生 archive 冒充官方原 archive。
- Addons installed RECORD **1,253** 個檔案逐條驗證；與 Essentials 零雙重所有權，64 shared 檔案仍只屬 Essentials。新增 `.py` 亦檢查 pip 隱含 `.pyc`／`.pyo` 移除路徑。
- 未知／多 owner、不同 bytes、空白或錯誤 owner hash/size、版本不同、缺檔、malformed／duplicate RECORD、大小寫 alias、symlink／junction／reparse redirect、原/衍生 wheel 或 receipt 不一致均拒絕。prepare→install 重驗全體 ownership metadata，不以先裝原 wheel 再改 live RECORD 的方式修補。
- `QtPreimage.zip` 的備份／hash/readback 保留；失敗安裝仍不自動卸載。Rollback 須 `install.json` exit0、idle、exact derived installed RECORD／payload hash／單一 owner、原 Qt bytes 不變才放行；部分安裝或 guard 不符停止人工審查。正式環境未執行 rollback，disposable fixture 的真實 pip uninstall 已驗證。

### 驗證與正式執行證據

| 項目 | 本次結果 |
| --- | --- |
| 修補前重現 | `prepatch.json`：舊 gate 對已合法 owned 的同 bytes fixture 拒絕，1 error／exit1 |
| 最終 Python 回歸 | `final-source.json`：**43 tests PASS**（既有 resume 14、W6 9、新 ownership 20），三份 Python syntax compile PASS |
| PowerShell | `relay-tests/Results.json`：**5 idle guard cases PASS**、AST PASS；合計 **48 tests PASS**，保留原 28 cases |
| 真實 disposable pip | 新 fixture venv 中 install→檢查 RECORD→uninstall；Essentials 全部 bytes、shared `.py` 及 optimization bytecode 保留；零正式卸載 |
| 正式 idle | 成功 run 的 `ProcessSurvey-before.json`／`ProcessSurvey-preinstall.json` 都 formalCount=0、unknownCount=0 |
| 正式安裝 | `-Wheel` 使用原已下載 wheel，全程 no-index／no-deps／no-compile；install exit0、只有 Addons 6.11.1 delta；未再次下載 |
| 套件／來源 | 三套件同為 6.11.1；pip check before/after exit0；七個 module imports PASS、六個已載入 Qt DLL 全部位於正式 env |
| pre-app | `schemeRegistration=PASS_BEFORE_APPLICATION`、未建立 app、無 Qt override |
| 保全 | `FinalAudit.json`：原 470 dirty entries 保留，仅新增 ownership test 使 dirty=471／Git-visible=1,322；index／HEAD／六 renderer／G7 35 absent、原 28 receipts 的 bytes/hash/mtime、2,598 個 Essentials/shiboken 檔案 bytes、PowerShell relay 均不變 |

所有 before/after probe 與 process receipts 仍 `.casefold()` 唯一；JSON 使用 exclusive create，command stdout/stderr 也改為 exclusive，遇舊 receipt 在執行 subprocess 前拒絕。`FinalAudit.json` 重新以最終 source 驗 installed ownership，並保存六個 scoped source/docs 的 hashes 與 diff；沒有 unrelated changes。

兩次中途停止也完整保留：`w6-user-install-20261011T0953032812885Z` 在寫入探針停止（Windows NamedTemporaryFile 的另一 handle 讀回受 delete-sharing 阻擋），經 `probe-regression.json` 實際重現後改同 handle 讀回並新增真實可寫 fixture 測試；`w6-user-install-20261011T0955102472770Z` 在 preinstall idle survey 發現短暫 unknown Python PID72656 而拒絕。兩次均無 pip install；沒有終止程序，沒有覆寫 receipts。成功 run 通過修正後探針與新的 idle gate。

回歸重現（從 repo root；更換最後 mode 名稱，避免覆寫 logs）：

```powershell
& .\envs\kuro-llm310\python.exe -I -B .\devtools\original-git-web-host-20261010\.runtime\w6-overlap-20261011T094355714164Z\run_tests.py review-rerun
```

**不需再安裝。** 未經本 gate 的 raw-wheel reinstall/upgrade 仍可能重建雙重 ownership，不在本次保證範圍；移除 Essentials 本身也會移除 Addons 的必要依賴。保留本次 receipts／原 wheel／衍生 wheel／backup 供日後有授權的維護；下一個 UI gate 不由本次 prerequisites PASS 自動授權。

安裝完成後額外 `-AuditOnly`（`.runtime/w6-user-install-20261011T1003269495647Z/`）記錄 formalCount=0、unknownCount=1（PID64748，path unavailable），因此該次唯讀 survey 為 BLOCKED。沒有後續套件操作，也未終止程序；這不改寫成功 run 安裝前兩次 idle PASS 或既有 W6.B/C package 證據，但不能宣稱結尾全系統 idle 已證。此最後文件補充的 UTF-8／scoped diff／SHA 見 `FinalDocumentAudit.json`；程式與正式套件以 `FinalAudit.json` 為準。

## 最新修復：2026-10-11 Windows preflight receipt 大小寫碰撞

本次只完成工程修復。`snapshot()`／`verify()` 的 command 名稱改為 `preflight-before-process`／`preflight-after-process`，分別產生 `.json`、`.stdout`、`.stderr`；probe 仍寫 `Preflight-before.json`／`Preflight-after.json`。兩組名稱經 `.casefold()` 後不同，JSON 保持 `open("x")`，`rollback()` 仍只以 `install.json` 的 exit0 作為第一道 guard。沒有全域 receipt 改名，也沒有修改 PowerShell relay。

Evidence：`.runtime/w6-fix-collision-20261011T092742570326Z/`。

- 修補前 preimage 實跑 before／after 兩個 regression：**2 errors，exit1**，兩者都是 Windows `[Errno 17] FileExistsError`；詳見 `prepatch-tests.log`／JSON。不是只檢查 source 字串。
- 修補後 `test_w6_resume.py`：**14 tests PASS**（原8＋新增6）。新增 cases：`test_before_blocked_probe_keeps_distinct_casefold_receipts`、`test_after_blocked_probe_keeps_distinct_casefold_receipts`、`test_after_synthetic_success_reads_probe_not_process_receipt`、`test_probe_and_process_json_refuse_overwrite`、`test_missing_or_failed_install_json_refuses_before_uninstall`、`test_successful_install_json_allows_only_mocked_rollback`。成功安裝／rollback 僅為 mock；未對正式環境執行。
- `tests/test_qt_web_w6.py`：**9 tests PASS**；`test_w6_relay.ps1`：**5 synthetic idle-guard cases PASS**；兩份 PowerShell AST 與兩份 Python syntax compile PASS。合計 **28 tests PASS**，不含刻意失敗的 prepatch 2 tests。
- 真實唯讀 rehearsal：`prepare()` 完成 Qt backup/readback、pip list/freeze/check/version、before probe 與獨立 process receipts；在官方 metadata 呼叫前由 mock 明確停止，**沒有網路／wheel 下載／套件寫入**。另跑真實 after probe command，兩次均 exit2、`BLOCKED`（Addons 仍缺），沒有 `PackageGate.json` 或 `install.json`。`Rehearsal.json`／`rehearsal/` 不代表完整 prepare 或 prerequisites PASS。
- `Before.json`／`FinalAudit-verified.json` 保存 1,321 個 Git-visible 路徑、470 dirty entries、HEAD／index SHA、六個 renderer 對原 Git commit 的 SHA、G7 35 absent 與正式既有 Qt 套件 SHA。原失敗目錄 `.runtime/w6-user-install-20261011T0922091159507Z/` 的22個檔案以內容 SHA／大小／mtime 核對，保留原始名稱與內容；本輪只改本 checkpoint、package gate 與 regression tests。
- 初版 audit 把 `git diff --no-index --check` 的正常差異 exit1 誤判失敗，原結果保留為 `FinalAudit.json`。另用乾淨／尾端空白 fixture 實測 exit1／exit3（`DiffCheckCalibration.json`），修正判定後重跑；只有無診斷訊息且 exit0/1 才通過。

本輪測試使用正式 Python 的 `-I -B`，disposable fixtures／log／compile output 均放本次 evidence。重現命令（從 repo root）：

```powershell
& .\envs\kuro-llm310\python.exe -I -B .\devtools\original-git-web-host-20261010\.runtime\w6-fix-collision-20261011T092742570326Z\run_tests.py postpatch-retry
```

使用新 mode 名稱可保留既有測試 log（例如 `postpatch-retry2`）。完整測試名稱、stdout／stderr 與前後 source diff 留在本次 evidence。

使用者可在正常 Windows PowerShell **重跑原本同一個命令**；relay 每次建立新的 `.runtime/w6-user-install-<UTC>/`，不必刪除或改名舊 receipts：

```powershell
& 'C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010\Invoke-W6AddonsRelay.ps1'
```

此使用者命令仍包含既有的 Addons 下載／安裝 gates；本輪 agent 未執行。正式 Qt GUI、W6.D/E/F、private backend、W7、commit/push 均未開始。

## 最新：2026-10-11 使用者正常 Quit 後續作

Evidence：`.runtime/w6-resume-install-20261011T0905184749243Z/`。本輪起點 1315 Git-visible paths／464 dirty paths，main/HEAD/index 與交接一致。正式 Kuro 程序新盤點為 **0**，unknown Python/pip **0**，Kuro/Pet listeners 消失；中央語音 :18890 PID2732 仍存在。未停止任何程序、未啟正式 profile。

| Gate | 本輪結果 |
| --- | --- |
| W6.A | PASS：新的 path/PID/startUtc/parent/listener survey，另實跑新 relay 的 AuditOnly |
| W6.B | **DOWNLOAD_BLOCKED**：pip list/freeze/check/version 保存，check exit0；Essentials/shiboken6 6.11.1 的 218421883-byte ZIP 已逐檔 hash 讀回。官方 wheel 已在 PyPI 確認；sandbox urllib 一般/提權均 WinError10013，PowerShell 連線也失敗；有界可讀 cache 無驗證 wheel、使用者 pip cache Access denied。零 Addons 安裝 |
| W6.C | 當次正式 preflight exit2：缺 Addons/三個 Web modules/DLL，scheme NOT_RUN；既有 Qt origins 正常。不能以 relay static tests 宣稱安裝完成 |
| W6.D | source 準備：新 transitive owner/observer map、具體接線／cleanup／auto-connect 風險與負例測試。四 owner 各一 lexical constructor；53 bindings、36 有 Widget 可達路徑。**實際 owner handoff 未執行** |
| W6.E | existing-window WebEngine native **UNVERIFIED**；未建立或執行可冒充正式 acceptance 的 harness |
| W6.F | **BLOCKED，零 Widgets 刪除**；原正式入口／requirements／VBS／host/adapter bytes 保留；停 W6，W7 未開始 |

新 [正常 Windows 安裝 relay](Invoke-W6AddonsRelay.ps1) 和 `w6_package_gate.py` 只處理正式 package prerequisite。它保存新 baseline、驗官方 JSON SHA／wheel METADATA／Requires-Python／cp310-abi3-win_amd64／檔案 collision，立即 preinstall idle 後用 local wheel `pip --isolated --no-deps --only-binary=:all: --no-cache-dir --no-index --no-compile --no-user --prefix <formal>`。安裝後要求只有 Addons delta、舊 Qt bytes 不變、pip check、正式 preflight/scheme PASS。失敗不改 global、ACL、DLL、VBS 或啟動服务；退出非零留 receipt。自動 package-write 分支在 sandbox **未執行**。

離線驗證：既有六 suites **76 tests exit0**；新增 package refusal／metadata/tag/hash/collision／owner graph **8 tests exit0**；PowerShell **5 synthetic idle-guard cases exit0**，合計 **89 cases**。PowerShell AST PASS。精確 argv/exit/log 见 `ValidationSummary.json`。檔案／index／原六 Git pin／G7 35 absent／套件 SHA 最終結果以 `FinalAudit.json` 為準。[接線實作準備](W6OwnerWiringPlan.md) 明確記錄下一批必要修改，不把 inventory 當 handoff。

此前舊程序表和舊授權阻塞為歷史，不再要求使用者重做 Quit。

## 最新續作：2026-10-11，W6.A 正常退出受阻

新授權允許精準關閉已核實正式 env PID 與安裝 Addons。以下是新盤點，不沿用旧 PID 假設；下方舊 source/staging 結果只是歷史證據。

Evidence：`.runtime/w6-execution-20261011T0840480172257Z/`。

| Gate | 本次結果 | 未達 exit |
| --- | --- | --- |
| W6.A | `Get-Process` + `NtQueryInformationProcess` + netstat 核實四個正式 env 程序與 Launcher-owned Pet；合成 WM_QUIT callback PASS | Pet 已授權；正式 EnumWindows 一般/提權皆失敗，GUI thread 不可驗、Core idle 未證。零正式關閉／終止，env 尚未 idle |
| W6.B | 未開始 pip snapshot/download/install | W6.A idle gate 未通過；沒有部分安裝或套件 rollback |
| W6.C | 未執行本次正式 preflight | 尚未安裝；不能引用前輪結果作本次 PASS |
| W6.D | 已讀既有 window/host/adapter 與 observer 圖、保全 source | 正式依賴門檻未通過，未改入口／owner 接線 |
| W6.E | 未建 existing-window harness／未執行 native acceptance | UI 工具失敗不等於 WebEngine 失敗，也不等於 native PASS |
| W6.F | 零 Widgets 刪除，保留正式回滾 | W6.E 與人審未成立；W7 未開始 |

四個正式程序的 executable 都在 `C:\project\desktop-agent-runtime\envs\kuro-llm310`：

| PID | executable | startTime UTC | parent PID | 核實角色 |
| --- | --- | --- | --- | --- |
| 52840 | pythonw.exe | 2026-10-11T05:08:43.8778212Z | 51300 | launcher_qt.py，Qt Launcher/tray |
| 9080 | python.exe | 2026-10-11T05:08:53.0372909Z | 52840 | kuro_core_service.py，Core :23569 |
| 49664 | python.exe | 2026-10-11T05:08:53.9688545Z | 52840 | uvicorn deeplx_bridge:app，Bridge :1188 |
| 1712 | python.exe | 2026-10-11T05:08:56.1090943Z | 52840 | run_server.py，Conversation :23456 |

中央語音 PID2732/PID2796 為 GPT-SoVITS env，明確排除；Pet listener PID51660 不在正式 Python env。未讀私人 DB/history/mail 或任何 token。初次短暫 PID73692 路徑不可見，後續已消失，沒有對它操作。CIM 一般及 require_escalated 唯讀查詢均 HRESULT 0x80041003；原生唯讀查詢成功，未修改 ACL/registry/security。

正常 Quit source 為 `qt_app.py::quit_application -> cleanup -> controller.close`；`qt_controller.py::close -> stop_profile` 會 stop Pet，再在 finally 呼叫 Core `stop`，Core 以既有 token/session 做 `/shutdown`。未從外部擷取 token。沒有 Core drain/active-write 證據時，不強制中斷 Core。

Windows Computer Use 初始化失敗：`node_repl kernel exited unexpectedly`，stderr `windows sandbox failed: Restricted read-only access requires the elevated Windows sandbox backend`。這是工具環境失敗，**不是 automatic approval reviewer rejection**；沒有送出 UI input，不使用自製 UI 自動化或安全設定繞過。

### 使用者追加授權後的有界替代實測

使用者已明確授權 Launcher-owned Pet 隨正常 Quit 停止，以及唯讀 Win32 EnumWindows 和獨立 synthetic `PostThreadMessageW(WM_QUIT)` 測試。此明示授權優先於一般 UI skill 的替代操作限制；不擴大到正式未驗 GUI thread、token 擷取或強殺 Core。

- `ProcessSurvey-3.json`：Pet PID51660，`pet-electron/node_modules/electron/dist/electron.exe`，start UTC `2026-10-11T05:09:07.4242411Z`，parent52840；Pet 子 PID52204 parent51660；:23567 listener PID51660。四個正式 Python 身分未變。
- 新 `w6_quit_probe.py` 的發送路徑只接受自己 `Popen` 建立且仍存活的合成 child；`--survey-pid` 純唯讀，無發送能力。沒有 import launcher/config/controller/Core 或讀私人資料。
- 命令：`envs/kuro-llm310/python.exe -I -B devtools/original-git-web-host-20261010/w6_quit_probe.py --output <run>/synthetic-quit-1`。獨立 child PID46140，GUI thread58836，native `windows`、Qt6.11.1；同一 hwnd/PID/thread 核對後 post accepted，`aboutToQuit -> synthetic_controller_close_called -> exec_returned`，exit0，watchdog=false，elapsed0.609s。`synthetic-quit-1/{Ready.json,ChildResult.json,Receipt.json,child.stdout.log,child.stderr.log}` 保存結果。
- **這只證明合成 callback，不證明正式 controller.close/Core shutdown。** 正式 PID52840 `--survey-pid` 一般兩次及重新核對 exe/startTime 的 require_escalated 唯讀一次均 EnumWindows failure（WinError0）。首次 error 僅在 command stderr；修正 helper 將後續失敗寫成 `LauncherWindows-2.json` 和 `LauncherWindows-elevated.json`。不能把空結果當正式無視窗，只能說本工具無法取得。
- 正式 Core `/shutdown` 要求現有 session token；status 沒有 DB idle/drain 證明。未讀取 process environment/token、未接觸 DB。`core_runtime.stop` 的 timeout fallback 可 terminate，不能在未證 writer 安全時宣稱保證 graceful。故沒有發送正式 WM_QUIT，也沒有強殺任何正式 PID。
- 按使用者最新指示停止，交手動系統匣 Quit，不等待、不重啟。B–F 仍未通過；安裝與正式接線未開始。

下一步與唯讀重驗見 [W6Handoff.md](W6Handoff.md) 最新段落。現有正式 Widgets、requirements、VBS 與 package env 未改動；最終全 WIP/index/原六/G7 核對見當次 `FinalAudit-final.json`。初版 `FinalAudit.json` 因把 Git 的 LF→CRLF warning 當成 diff error 判為 false；已核對只有換行提示，改用單次 `git -c core.autocrlf=false diff --no-index --check` 驗原始 bytes，未改 Git config 或檔案換行。

2026-10-11。本輪停止 W6。使用者已接受原版 Web 視覺；不追逐 pixel-perfect、不改原六檔。**未在正式 KuroQtLauncherWindow 採用 Web、未 retire 正式 Widgets callbacks、未刪 Widgets、未開始 W7／commit/push。**

## Gate 裁決

| Gate | 當次結果 | 裁決 |
| --- | --- | --- |
| W6.0 source/WIP/owner inventory | exact preimages/index/status/diff；4 個 retirement candidates、6 檔 AST graph；native receipts 重新讀取；Git pin/G7 核對 | source PASS；active launcher loaded-source identity UNVERIFIED |
| W6.0 formal dependencies | Python3.10.12、Essentials/shiboken 6.11.1；缺 Addons 及三個 Web modules；已載入 Core/Gui/Widgets DLL 均在正式 env，Web DLL 未載入；process exit2 | **HARD BLOCKER** |
| W6.1 owner assets／scheme／guard | 原 config 建置 4 assets、lineage/CSP/hash/tamper 檢查；晚於 QCoreApplication 的 registration 被真 Qt test 拒絕；readiness 字串不能授權 host | source/staging PASS；positive native registration UNVERIFIED |
| W6.1 existing-window adoption | 正式 entry 不 import host，現有 VBS/launcher/qt_app 不改；無第二 UI/WS/controller/notifier | **BLOCKED，未執行** |
| W6.2 observer retirement | imports/calls/self-attributes/signals/timers/reverse callers 完整靜態清冊及分組接線計畫 | 計畫 PASS；實際 retire **BLOCKED** |
| W6.3 legacy deletion | 舊 Qt presentation 保留；G7 35 個舊 Electron 路徑保持不存在 | **BLOCKED，零刪除** |
| W6.4 regression | 20 suites／231 tests 全部 exit0；另 typecheck、original-build、candidate-build exit0；新 owner build/verify exit0 | source/disposable PASS；正式 native/release UNVERIFIED |

## 實際改動與位置

| 檔案 | 位置／改動 |
| --- | --- |
| `kuro_launcher/qt_web_host.py` | `register_candidate_scheme` :42，拒絕 app 後註冊、重複同設定可重入、衝突拒絕；`create_candidate` :60，任何 non-fixture enabled call 都拒絕，readiness 不再授權 |
| `devtools/original-git-web-host-20261010/w6_inventory.py` | `source_graph` :23，AST calls/self attrs/observers/reverse caller；`native_receipts` :53 保留 absent 欄位，W3 不回填 W5；移除「W1 FAIL 因而一概未驗」舊阻塞理由 |
| `tests/test_qt_web_w6.py` | :38 起新增 readiness spoof、實際 QCoreApplication 晚註冊、graph、owner bundle、資產/manifest/lineage tamper、extra file、wrong interpreter 負例，共9 tests |
| 新 `w6_preflight.py` | `probe` :24；exact interpreter/prefix、package/module/loaded DLL origin、version、unsafe override 名稱、pre-app registration；無 QApplication/controller/config/env file/private state |
| 新 `build_owner_bundle.py` | `lineage` :29、`verify` :51、`build` :75；Git pin、toolchain/lock SHA、immutable content-addressed assets、來源變動拒絕、現有產物不覆寫、沒有 activation pointer |
| 新 `assets/qt-owner/.gitignore` | 忽略生成的 fingerprint 目錄，不追蹤編譯輸出；唯一 source 仍原 devtools frontend |
| 新 `W6Plan.md`、`W6Handoff.md`、本 checkpoint | 執行／退役／future gate、exact PowerShell no-install probe/build、可選 user-run Python3.10 staging remediation、rollback |

既有三檔局部 diff 位於 evidence 的 `diff-qt_web_host.py.patch`、`diff-w6_inventory.py.patch`、`diff-test_qt_web_w6.py.patch`。完整 added/changed/deleted + postimage/preimage SHA 以 `FinalAudit.json`／`ScopedDiff.patch` 為準。

## Evidence 與實測界線

當次根目錄：`.runtime/w6-source-20261011T080046Z/`。

- `Before.json`、`index-before.bin`、`status-before.bin`、`tracked-before.patch`、`staged-before.patch`、`preimages/` 保存 main/HEAD、457 dirty entries 與修改前 bytes。`FinalAudit.json` 獨立重新雜湊全部 baseline、原六 Git blobs/index/G7，不能以最終 dirty 總數代替保全。
- `W6Inventory-final.json`：`qt_app.py` 有24 import statements、1395 self attribute occurrences、1708 calls、70 connect/disconnect/start/stop/singleShot occurrences；view 277 calls/12 observers，Core pages 562 calls/15 observers。這是 AST occurrence 數，**不是** runtime instance/connection count。詳列 line/owner/read-store/reverse self calls；不涵蓋反射。
- `FormalPreflight-final.json`、`ProcessReceipts.json` 及 stdout/stderr：正式探測 exit2，owner verify exit0。`CandidatePreflight.json`：sandbox task Python3.13 import PermissionError13、exit2；未啟 GUI/sidecar。無安裝、ACL/registry/security override。
- `ActiveRuntimeMetadata.json`：CIM 拒絕存取。`FormalExeProcessMetadata.json`：Get-Process 觀察到 PID52840 的 executable 為正式 pythonw，但無 argv/loaded-source 證明，**不能證明該程序就是採用本次 source 的 launcher**。未 contact/restart 此程序。
- `OwnerBuild-2.json`／`OwnerVerify.json`：`assets/qt-owner/e9be6378eedc80e070e51c65f48c125634555558d2b75d84d26ec855940729d8/`，4 compiled assets、同一 owner config；manifest/owner-build 記來源/工具鏈 SHA。staging 不代表正式採用。
- `validation/Results.json` 保存23項命令的 cwd/argv/exit/count/elapsed 與各 log；20 test suites 合計231（重跑不重複加總）。`w6-final/Results.json` 為最終9個 affected tests exit0。第一輪 W6 inventory 約104秒，改以 AST unparse 避免重切完整字串後約2秒；不是 skip tests。
- frontend 14 tests 包含全部24 bridge methods 顯式綁定、hello 前無 dispatch、無 fallback、same-context stale 保留／跨 context 清除、notification revision 失效、unknown timeout 不重送。IME 是合成 event source test，**不代表真鍵盤 IME acceptance**。
- disposable Core/Memory tests 驗 GET/prepare/cancel bytes 不變、materialize 拒絕、revision/idempotency/duplicate、canonical JSON/SQLite、唯一 QtScheduleDelivery claim→authorize→mock tray→ack。沒有真正 OS notification、provider/LLM/mail/stock order。
- G3/G4/G5/G6/G8 Python 為27/15/17/11/3；Pet Node G3/G5/G6為7/3/10。其餘 Web/Schedule suites 見 Results。G8 是隔離 regression，沒有執行 W7 release。

最新使用者 native W5 receipt 重新核對：Qt6.11.1/offTheRecord、bridge/shell、brokerClosed/chatThreadStopped=true、serviceExit=0、nativeChecksFailed=false、exit0。W3 關閉欄位不存在。receipt 記載 host SHA 是本轮 preimage `8fe7a152…`，所以它證明上一版 fixture 正常；**不冒充本轮 modified host 的 native proof，更不是正式 main window tray/lifecycle 證據**。既有 user visual acceptance 保持有效。

## 失敗／限制與後續

- `docs/agent-runs/.../W6Plan.md` 新增遭寫入失敗，文件改存目前 task 目錄；未改權限。這是 filesystem failure，不是 automatic approval reviewer rejection。
- 初次 snapshot 的 PowerShell stdin 編碼損失導致中文 VBS 路徑讀取失敗，UTF-8 重試在任何 source 修改前完成。首次 owner build 已生成檔案但 cp950 stdout 印出 Vite 符號失敗；改 UTF-8 後新 fingerprint build/verify 通過。未封存的第一次 compiled 輸出保留 ignored、沒有入口引用，不清理使用者資料。
- 未建立假 formal readiness receipt；沒有另開正式 Web/Widget application、第二 WS/notifier/controller/DB/service。原 controller/ChatClient/QtScheduleDelivery/正式入口 bytes 保留。
- 下一步只跑 [W6Handoff.md](W6Handoff.md) 的正常使用者 prerequisite probe；選擇修復環境後，仍需 exact formal-runtime existing-window native harness 與原地 observer handoff，才有資格刪舊 Widgets。這部分尚未實作／未驗收，不宣稱 W6 完成。
- rollback 按 [W6Plan.md](W6Plan.md)：核对 postimage、逐 hunk 還原三個修改檔；保護其餘 WIP/index。正式服務/DB/VBS 不需回滾。W6→W7 必須另經人審，本輪停 W6。

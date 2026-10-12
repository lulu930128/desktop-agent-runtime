# W6 PowerShell 交接：W6.B/C 已通過，不啟用正式 UI

## 最新 D/E/F 接力

**不要重跑下方 Addons installer。** existing-window 接線及 source／隔離回歸已完成，但 native renderer exit49，Web 互動 gate BLOCKED。請使用 [W6FinalCheckpoint](W6FinalCheckpoint.md) 的正常桌面 relay：只測隔離真視窗及一次 restart，不切正式入口、不讀 private profile。Widgets 保留，W7 未開始。

## 最新 ownership 修復：使用已完成下載的官方 wheel

**正式安裝已完成，不需重跑。** 成功 run 為 `.runtime/w6-user-install-20261011T0956528942669Z/`：`PackageGate.json`／`Preflight-after.json` PASS，原 Essentials/shiboken bytes 不變。以下離線命令僅保留為日後有授權、且 Addons 尚未安裝時的接力方式。

2026-10-11 17:38 的下載已完成（168,816,308 bytes），當次阻塞是 64 個 Essentials-owned 同位元檔案，並非下載權限。完整清冊與正式執行結果見 [W6Checkpoint](W6Checkpoint.md) 最新段落。下方「NETWORK_DENIED／尚未下載」僅為歷史。

需要接力且 Addons 尚未安裝時，只用正常 Windows PowerShell 的離線命令；不需要 admin、不再次下載：

```powershell
& 'C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010\Invoke-W6AddonsRelay.ps1' -Wheel 'C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010\.runtime\w6-user-install-20261011T0938079724671Z\wheelhouse\pyside6_addons-6.11.1-cp310-abi3-win_amd64.whl'
```

若最新 `PackageGate.json` 已 PASS，**不要重裝**；只交付該 run receipts，停在 W6.B/C。relay 會拒絕已存在 Addons。保持 Kuro 關閉；本次不繼續 W6.D–F/W7。

relay 保留官方原 wheel SHA provenance，產生獨立 `install-wheel/*-1w6owned-*.whl`：64 個 shared 檔案繼續只由 Essentials RECORD 持有；Addons wheel／RECORD 均排除它們。`WheelReceipt.json` 保存全 overlap 與 ownership manifests，`InstallWheelReceipt.json` 保存原/衍生 SHA、衍生 RECORD、排除清冊；installed dist-info 的 `W6_ORIGIN.json` 也保留來源。禁止直接 pip 安裝原 wheel，否則重新引入双重 ownership。

安裝前 backup readback、再次 idle、ownership/hash 重驗、create/read/delete 探針任一失敗即停止。`WriteAccess.json` 的 `phase` 區分 CREATE、WRITE_READBACK、DELETE_ON_CLOSE；Windows temporary file 使用同一 handle 讀回，避免 delete-sharing 假性拒絕。失敗 receipts 不覆寫、沒有自動回滾。回滾仍使用該 run 的 `RollbackPlan.json`：必須 install exit0、idle、exact derived installed RECORD、無重疊、原 Qt bytes 不變；guard 不成立不執行 uninstall，不用整包 backup 強行覆寫正式環境。

## 最新：使用者已正常 Quit；執行一次正常 Windows 安裝 relay

在**正常使用者互動式 Windows PowerShell**執行下列單一命令；執行期間保持 Kuro 關閉。已有安裝授權，不需要再同意一次；本輪 Codex 因 NETWORK_DENIED 尚未安裝。

```powershell
& 'C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010\Invoke-W6AddonsRelay.ps1'
```

腳本先重新確認正式 env 閒置，保存全新 pip list/freeze/check、Qt metadata/module origins/byte backup；從官方 PyPI metadata 選唯一 `pyside6_addons-6.11.1-cp310-abi3-win_amd64.whl`，以正式 Python 的 isolated pip no-deps/binary-only 下載 task wheelhouse。核對 [官方 PyPI](https://pypi.org/project/PySide6-Addons/6.11.1/) SHA256 `0d13c4dfd671b050a48e4f8d8ddc724b7248f9c0437e7fc47fdf316278572923`、METADATA/version/Requires-Python/internal tag／collision 後，再做 idle survey 與 local wheel 安裝。只新增 Addons，不 upgrade Essentials/shiboken，不使用 global/conda／代理或安全設定繞過。

成功須 exit0 並產生新 `.runtime/w6-user-install-<UTC>/PackageGate.json` 和 `Preflight-after.json`：`PREREQUISITES_PASS`、`PASS_BEFORE_APPLICATION`、同正式 env modules/Qt DLLs、pip check exit0、僅 Addons delta。**這仍不是 W6.D/E/F 或產品驗收。** 腳本不改 requirements／VBS、不啟正式服務／UI、不刪 Widgets。

失敗時 exit2 且保留 `*-process.json`、pip stdout/stderr、Failure receipt，不自動重試網路或回滾。把 console 最後顯示的 evidence 路徑交回即可。套件已成功安裝但驗證失敗時，`RollbackPlan.json` 提供同腳本 `-RollbackRun '<evidence path>'` 命令；該命令仍先 idle，再檢查舊 Qt bytes、exact Addons version/RECORD，才只 uninstall 新增 Addons。部分安裝沒有有效 RECORD 或既有 Qt 已變動時直接拒絕，需檢查 receipt，不能直接刪 DLL 或覆寫整個 env。

可選 `-Wheel '<既有官方 wheel 完整路徑>'` 用離線檔；仍須命名、官方 pinned SHA、內部 metadata/tag 全部符合。`-AuditOnly` 只做新 idle survey，不做 pip／網路／env 寫入。兩個正常 relay 不會同時執行 package writes（task-local exclusive file lock）。

Codex 已執行 AST、synthetic precondition 負例與離線 owner regression；沒有聲稱 sandbox 已完成安裝。當次 evidence：`.runtime/w6-resume-install-20261011T0905184749243Z/`。下一輪先讀新 `PackageGate.json`、新 process survey、套件及 DLL 身分，然後依 [W6OwnerWiringPlan.md](W6OwnerWiringPlan.md) 進行同一 QMainWindow 接線與隔離 native 驗收。W7 不在此命令範圍。

下列內容為前輪歷史；「先手動 Quit」已完成，不需照舊段落重做。

## 最新續作：2026-10-11 正常退出接力

本輪已允許關閉核實正式 env PID、Launcher-owned Pet 和限定 Addons 安裝；不必重新詢問這些授權。Windows UI 工具初始化失敗。後續使用者授權的有界替代實測已證 synthetic WM_QUIT 觸發 aboutToQuit/cleanup 並 exit0，但正式 PID52840 EnumWindows 一般/提權皆失敗，無可信 GUI thread，亦無正式 Core idle 證據。未向正式程序送 WM_QUIT、未強殺 Core。

依使用者指定，現在停止自動關閉，不等待或重啟。請從 Kuro 系統匣選 **Quit Kuro**；這包含已授權的 Kuro-owned Pet。X 只隱藏，不能代替 Quit。中央語音不屬於此操作。下段是退出後的唯讀重驗。

正常退出後，在一般 PowerShell 做唯讀重驗（只寫新 receipt，不 kill、不 pip）：

```powershell
Set-Location -LiteralPath 'C:\project\desktop-agent-runtime'
$w6Run = Join-Path $PWD 'devtools\original-git-web-host-20261010\.runtime\w6-execution-20261011T0840480172257Z'
$w6Survey = Join-Path $w6Run ('ProcessSurvey-user-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ') + '.json')
& (Join-Path $w6Run 'Survey.ps1') -OutputPath $w6Survey
$w6Observed = Get-Content -LiteralPath $w6Survey -Raw -Encoding UTF8 | ConvertFrom-Json
if ($w6Observed.formalCount -ne 0 -or $w6Observed.unknownCount -ne 0) {
    throw 'W6.A BLOCKED: formal consumers or unidentified Python/pip remain; no pip'
}
Write-Output "Idle survey only; agent must recheck immediately before pip: $w6Survey"
```

重驗只證明當次程序清冊；不能據此宣稱已安裝或正式 Web 採用。後續仍按 [W6Plan.md](W6Plan.md) W6.B–F 執行：新套件快照、官方 wheel/hash/tags、安裝前再次 idle、僅 Addons 6.11.1、正式 preflight、existing-window source/native，再決定精準退役。下方前輪 staging 命令是歷史備用，不取代本次限定正式 env 安裝流程。

目前正式 Python 3.10.12 / Qt Essentials 6.11.1 缺 Addons；所以舊 Widgets/VBS 保留。下列第一段只有 imports、讀取 source、建置／驗證 generated assets，不啟服務、不碰 private state、不安裝。preflight exit2 是 BLOCKED，不得修改 receipt 或塞 readiness PASS。

## 1. 正常 Windows 使用者重驗（無安裝）

```powershell
Set-Location -LiteralPath 'C:\project\desktop-agent-runtime'
$w6Task = Join-Path $PWD 'devtools\original-git-web-host-20261010'
$w6Python = Join-Path $PWD 'envs\kuro-llm310\python.exe'
$w6Evidence = Join-Path $w6Task ('.runtime\w6-user-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ'))
New-Item -ItemType Directory -Path $w6Evidence -ErrorAction Stop | Out-Null
& $w6Python -I -B (Join-Path $w6Task 'w6_preflight.py') --output (Join-Path $w6Evidence 'FormalPreflight.json')
$w6ImportExit = $LASTEXITCODE
Write-Output "Formal prerequisite exit=$w6ImportExit (0 is not adoption approval)"
# 可獨立完成 staging；正式 import 缺少不影響此步。
& $w6Python -I -B (Join-Path $w6Task 'build_owner_bundle.py') --output (Join-Path $w6Evidence 'OwnerBuild.json')
if ($LASTEXITCODE -ne 0) { throw 'Owner build BLOCKED; preserve receipt and incomplete directory' }
& $w6Python -I -B (Join-Path $w6Task 'build_owner_bundle.py') --verify --output (Join-Path $w6Evidence 'OwnerVerify.json')
if ($LASTEXITCODE -ne 0) { throw 'Owner bundle verification failed' }
& $w6Python -I -B (Join-Path $w6Task 'w6_inventory.py') --output (Join-Path $w6Evidence 'W6Inventory.json')
if ($LASTEXITCODE -ne 0) { throw 'Inventory failed' }
Write-Output "Receipts: $w6Evidence; stop before formal cutover/deletion"
```

不要透過修改 `PYTHONPATH`、DLL PATH、複製 `.pyd` 或 task venv 到正式環境修補。probe 同時驗 module origin、三份 distribution 精確版本、Qt version/library path、Windows 已載入 Qt DLL origins；只在全部成立且未建 QApplication 時呼叫 scheme registration。Qt 官方要求先註冊再建 application，見 [官方文件](https://doc.qt.io/qtforpython-6/PySide6/QtWebEngineCore/QWebEngineUrlSchemeHandler.html)。

## 2. 可選：使用者自行建立同 Python 的一次性 dependency staging

此段**會下載套件並寫入新的隔離 env**，本輪 agent 沒有執行。只在你決定執行下載／環境驗證時用；不改正式 env、VBS、registry/ACL/global packages。`PySide6-Addons 6.11.1` 官方套件包含所缺三模組，Windows x64 wheel 支援 Python 3.10；[Qt Project 的 PyPI 發行頁](https://pypi.org/project/PySide6-Addons/6.11.1/)。

```powershell
# 先執行第一段設定的變數；每次選新目錄，不覆寫既有 env。
$w6Stage = Join-Path $w6Evidence 'python310-qt6111'
if (Test-Path -LiteralPath $w6Stage) { throw 'Choose a new staging env; never overwrite' }
& $w6Python -I -B -m venv $w6Stage
if ($LASTEXITCODE -ne 0) { throw 'Staging venv failed; do not change ACL or official env' }
$w6StagePython = Join-Path $w6Stage 'Scripts\python.exe'
& $w6StagePython -I -B -m pip --isolated install --index-url https://pypi.org/simple --only-binary=:all: --no-cache-dir 'PySide6==6.11.1'
if ($LASTEXITCODE -ne 0) { throw 'Staging Qt install failed; preserve output' }
& $w6StagePython -I -B (Join-Path $w6Task 'w6_preflight.py') --expected-prefix $w6Stage --output (Join-Path $w6Evidence 'StagingPreflight.json')
if ($LASTEXITCODE -ne 0) { throw 'Staging imports/identity/registration BLOCKED' }
```

成功只證明 Python3.10 與完整 Qt 可在新 env 相容，**仍不能證明正式 env 已修復**。不要將這個 env 改成 VBS 的 executable。正式 env 若要修復，需先停止並確認所有使用它的正式程序、保存環境回復方案，再以同版 Addons 做依賴審核；本輪不包含這個操作，也不提供自動修改正式 env 的腳本。將 `FormalPreflight.json`、`StagingPreflight.json` 交回 reviewer 決定下一批範圍。

## 3. Candidate 新 source 的 native relay（仍非正式 owner）

本輪 sandbox 的 task `.venv` import 再次 PermissionError13；一般使用者舊 W5 已成功，這兩件事不衝突。若需要核對本輪 scheme guard 修改後的 candidate，可在正常桌面跑：

```powershell
$w6Candidate = Join-Path $w6Task '.venv\Scripts\python.exe'
& $w6Candidate -I -B (Join-Path $w6Task 'w6_preflight.py') --expected-prefix (Join-Path $w6Task '.venv') --output (Join-Path $w6Evidence 'CandidatePreflight.json')
if ($LASTEXITCODE -ne 0) { throw 'Candidate import BLOCKED; no GUI or sidecar launch' }
& (Join-Path $w6Task 'Open-NativeCandidate.ps1') -Checkpoint W5
```

此 runner 只管理自身 synthetic window/sidecar，原版 chrome X 會結束 fixture；**不是**正式 window 的 X→tray acceptance。只輸入 synthetic 內容，參考 [native checklist](NativeCandidateReview-20261011.md)。不能拿 W3 沒有 close fields 的 receipt 當關閉成功，不能拿舊 W5 source SHA 當本輪 host native proof。

## 4. Source 回歸與正式採用資格

```powershell
& $w6Python -B (Join-Path $w6Task 'validate_candidate.py') --output (Join-Path $w6Evidence 'validation') --only typecheck original-build candidate-build qt_web_candidate qt_web_assets qt_web_transport qt_web_w4_w5 qt_web_disposable qt_web_w6 web_notification_commands schedule_core schedule_notifications schedule_api schedule_runtime g3_conversation g4_qt_core g5_desktop g6_pet_boundary g8_runtime qt_web_frontend g3_presentation g5_desktop_owner g6_pet_shell
if ($LASTEXITCODE -ne 0) { throw 'Source validation failed; inspect per-suite logs/Results.json' }
```

正式採用還需：同一正式 executable 的 native WebEngine + **existing KuroQtLauncherWindow** 隔離 harness（尚未實作），單一 tray/client/notifier、X/reveal/Quit、second launch/restart/cleanup、late worker/identity/unknown 結果、原 local scheme security。現在只有 prerequisites 與 staging，沒有可安全啟用的 W6 正式切換命令。這些 evidence 通過後才原地切換並同批 retire observers，之後按 reverse imports 刪 Widgets。最後停 W6 人審；W7 release 必須另行授權。

回滾：正式入口沒變，無須改 VBS／DB。若要回退本輪 source，核對 `FinalAudit.json` postimage 和 `.runtime/w6-source-20261011T080046Z/preimages`，逐 hunk 還原三個既有檔；新 helper/docs 可留存，不用刪資料。若 SHA 不同，先比對後續 WIP，禁止 reset/clean/checkout/stash。

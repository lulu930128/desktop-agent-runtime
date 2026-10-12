# W1 正常 Windows PowerShell 接力 — 2026-10-10

**本輪交付：smoke runner 與部分 parity 接力可供人工執行；Gate W1：UNVERIFIED；W2–W7：NOT STARTED。**

使用者已在互動 Windows PowerShell 實測 task `.venv`：QtWebChannel、QWebEngineView、PIL.Image、playwright.sync_api 四項 import PASS；回報 PySide6／Qt 6.11.1、Pillow 12.3.0、Playwright 1.63.0，且無 sandbox／GPU override。此證據屬於使用者的正常 session；前輪 Codex `lulu\codexsandboxoffline` 對套件檔案的 PermissionError 13 不代表使用者環境未安裝，也不能否定該 session 的 import 結果。

本輪沒有再重試 package import、install 或 ACL，也沒有啟動 GUI。Codex 完成的是 source review、syntax／stdlib-only contract tests；Qt 真正 load／render／PNG／WebChannel 證據必須由下方正常 PowerShell 命令取得。使用者的 import PASS 不代表 renderer PASS。

## 唯讀 host 審核與修改範圍

`qt_preview_host.py` 保持不動：使用 task `.venv`，unnamed/off-the-record profile，只允許 dist 內資源與 qrc WebChannel script；拒絕其他導航、新視窗、下載、權限和檔案選擇；只註冊 synthetic PreviewProtocol。它在 capture 時有 20 秒內部 deadline，量測 page ready、bridgeRequests 與 geometry，再抓取 Web viewport。這些是 source-level controls；實際 sandbox、resource 拒絕、WebChannel payload 及畫面仍需 runtime 證據。

本輪四個變更檔案：

- 新增 `w1_smoke.py`：正常 PowerShell 接力 runner，沿用未改動的 host `--capture --view chat/settings`。
- 局部修補 `capture_parity.py`：必須先有當前 source/build 的 smoke receipt；Windows Qt 與 headed Chrome／Edge 比較，移除 offscreen；對齊實際 DPI／locale／timezone、保留失敗 receipt，明列未涵蓋項目。
- 新增 `test_w1_smoke.py`：只使用 stdlib，不 import Qt／PIL／Playwright、不啟動 GUI／網路。
- 新增本 checkpoint。

六個原始 Git renderer、host、protocol、geometry.js、正式 Qt／Core／Pet、正式 env、master Plan、原受阻 W1Checkpoint 均未修改。沒有 stage／commit／push、服務重啟或 ACL 變更。

## 第一階段：最小 Qt smoke

請在**正常互動 Windows PowerShell**執行。Qt 測試視窗會短暫出現，保持在同一螢幕，不移動、不縮小；不需管理員，不會安裝任何套件。

```powershell
Set-Location C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010
$run = Join-Path $PWD ('.runtime\w1-smoke-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
& .\.venv\Scripts\python.exe -B .\w1_smoke.py --output $run
if ($LASTEXITCODE -ne 0) { throw "W1 smoke 未通過，請檢查 $run\SmokeResult.json 與同目錄 logs" }
$smoke = Join-Path $run 'SmokeResult.json'
```

執行順序固定，任何一步失敗即不啟動後续步驟：

1. 拒絕繼承的 WebEngine security／GPU／debug／DPI override，不改其值、不弱化設定。
2. `w1_preflight.py` 核對 main／W0／staged／六份 source，保存本次 WIP snapshot。
3. 在相同 task Python 重跑 `w1_import_probe.py`，將執行身分所見的實際 import／versions 保存到本次目錄。
4. 使用既有 repo Node／TypeScript／Vite，check 並 build 隔離 frontend；不執行 npm install、不動正式 renderer-dist。
5. 依序執行既有 host 的 Chat 與 Settings，logical viewport 1280×720、**原生 Windows DPR**。這一步不是宣稱 100% DPI；實際值由 DOM 測量。
6. 驗證 host exit、Windows platform、off-the-record、render ready、6–100 次 bridge requests、原版 CSS tokens、所選頁面正尺寸、Settings 六組、font loaded、locale/timezone。Pillow 實際解碼／驗證 PNG，檢查非零 bytes、尺寸等於 viewport×DPR、opaque、非單色，保存 pixel extrema／standard deviation／SHA256。
7. 再核對 source／index／task 外 WIP；保存 `SmokeResult.json`，不將 smoke PASS 等同 W1 PASS。

每個 child 有 timeout；Qt 上限 30 秒，typecheck／build 各 60 秒。timeout／中斷時只針對本 runner 建立且仍存活的 exact child PID 做 process-tree cleanup，不按 image name、不碰既有 Kuro／Bridge／Pet。程序 stdout、stderr、命令、PID、exit 與 cleanup exit 都保存在本次目錄。

產物包含 `chat.png/json`、`settings.png/json`、兩份 `*.validation.json`、各步驟 `*.process.json`／logs、imports、before／after 與 SmokeResult。缺圖、單色圖、尺寸不符或 host FAIL 都不能得到 smoke PASS。非單色只證明不是空白，**不證明外觀正確**；仍須 reviewer 看圖。

## 第二階段：browser／Qt 部分 parity 接力

只在上方 smoke exit 0 後，在**同一 PowerShell**執行。第一個 command 先跑 100%，任何 mismatch／error 即停止：

```powershell
& .\.venv\Scripts\python.exe -B .\capture_parity.py --smoke-result $smoke --channel chrome --scale 1
if ($LASTEXITCODE -ne 0) { throw '停止：先審查 parity receipt、截圖與 logs' }
```

確認第一份 evidence 可用後，再接 125%／200%（全部仍只屬於 W1）；若選 Edge，把 `chrome` 改為 `msedge`，不會下載瀏覽器：

```powershell
foreach ($scale in @(1.25, 2)) {
    & .\.venv\Scripts\python.exe -B .\capture_parity.py --smoke-result $smoke --channel chrome --scale $scale
    if ($LASTEXITCODE -ne 0) { throw "停止：DPR $scale parity 未通過" }
}
```

每次寫入全新的 `.runtime/parity-<channel>-<scale>-<UTC timestamp>/`。沿用 installed Chrome／Edge executable，Playwright disposable profile、`chromium_sandbox=True`、headed mode；只允許 ephemeral localhost fixture origin。Qt 使用原生 Windows platform，保留其 sandbox／GPU 預設。

`QT_SCALE_FACTOR` 是原生 DPR 的乘數，因此 child-local multiplier 用「目標 DPR ÷ smoke 實測原生 DPR」。不改 Windows DPI 設定；實際 Qt DOM DPR 必須再次符合目標，viewport／locale／timezone／fontStatus 也必須等於 browser，否則 fail-fast。若換螢幕或改 display scaling，重新 smoke。來源與 bundle fingerprint 變動也會拒絕重用舊 smoke。

本接力僅保留既有 **Chat／Settings／Today（含 Schedule）的兩個 viewport，共 6 對 screenshot／每個 DPR**。會儲存 browser、Qt、diff PNG、DOM geometry／tokens／font、RGB MAE／RMS／changed fraction、browser 既有互動結果和 host log。

**這不是完整 W1 矩陣**：獨立 History screenshot pair、Qt interaction／native keyboard／IME、runtime resource／navigation／download 拒絕探測與人工 visual reviewer 都列在 `ParityResult.json.pending`。本輪遵循「先沿用既有 host 做最小 smoke」，沒有擴寫 host 去假裝補齊這些項目。`captureStatus=PASS` 只表示這六對 capture/comparison 程序完成；`gateW1` 仍為 `UNVERIFIED`，沒有設定可自動接受像素差異的門檻。W1 完整 PASS 必須補齊缺口及 reviewer 判斷，不能直接進 W2。

已核對官方 API 語意：[Qt DPI 乘數說明](https://doc.qt.io/qt-6.8/highdpi.html)、[Playwright launch 與 sandbox](https://playwright.dev/python/docs/api/class-browsertype)。沒有以 mock 冒充 native keyboard 或以 screenshot 非空冒充 visual parity。

## 本輪 Codex 驗證

- 七項 stdlib-only contract tests：metadata／有效 DPR、拒絕安全或 DPI override、六個 Settings groups、locale／timezone／font 不一致、stale smoke、Chat 失敗後不得跑 Settings，通過。測試中的子程序與 render 結果為顯式 mock，非 runtime 證據。
- 三份 Python helper/test 的 AST syntax、UTF-8／whitespace 與 task diff check 通過；不需要也未執行 production build/tests。
- before／after source guard、test logs 與 machine-readable authoring result 保存於 [.runtime/w1-relay-authoring/](.runtime/w1-relay-authoring/)。
- 真實 Qt smoke／Pillow decode／browser／pixel comparison：**本輪未執行，待使用者正常 session 執行**。沒有 Gate W1 PASS。

# W1 收斂與人工檢查點（2026-10-11）

**W1 維持 FAIL；本輪新 host 的 Windows native 採證 UNVERIFIED。停在 W1，等待獨立 review 與使用者測試。**

本輪只修改此隔離目錄的 W1 host、採證／診斷 helper、relay、tests 與本文件。六份 original frontend 檔案不改；正式 Qt Widgets launcher、feature-off candidate、W2/W3 與 W4–W7 均未推進。沒有 production attach、provider、DB、notifications、WS、安裝、ACL/security/registry 變更、commit 或 push。

## 真實採證及診斷

原始證據完整保留，不回填新欄位或修改狀態：

- `.runtime/w1-windows-relay-20261011T0600306155125Z/smoke/SmokeResult.json`：smoke PASS／gateW1 UNVERIFIED。
- `.runtime/parity-msedge-1-20261011T060043991596Z/ParityResult.json`：FAIL；6 pairs。
- `.runtime/parity-msedge-1.25-20261011T060117760663Z/ParityResult.json`：FAIL；6 pairs。
- `.runtime/parity-msedge-2-20261011T060151435666Z/ParityResult.json`：FAIL；第一對 viewport 不符，沒有完成 comparison row，仍有原始 Edge／Qt metadata。

這些實機 receipt 記錄 Edge **154.0.4258.62**、PySide6／Qt WebEngine **6.11.1**、Qt UA Chromium **140.0.0.0**。它們證明舊 host 在正常 Windows 使用者環境執行過；不是本輪修改後 host 的 native 驗證。

### Today：已定位的直接原因與尚未證明的底層原因

1280×720／100% 的 kicker 兩端 y 都是 133：Edge `10月11日星期日`、高 12px；Qt `10月11日 星期日`、高 15px。兩端 font stack 都是 `"Cascadia Mono", SFMono-Regular, Consolas, monospace`、font-size 10px、line-height normal、margin-bottom 7px，padding/border 為 0。Range text rect 高度都是 11px，但 Edge y133／Qt y136。

因此 **header 中第一個多出高度的 line box 是 kicker**；question y152／155、schedule y493.921875／496.921875 跟著下移 3px。這是可由現有 DOM 證據支持的直接 layout 原因，不是下游 margin 漂移。原版 `model.ts::formatFullDate()` 使用相同的 `Intl.DateTimeFormat('zh-TW', {month:'long',day:'numeric',weekday:'long'})`，字串差異在格式化輸出已可觀察。

目前**不能**把 3px 唯一歸因於空白、ICU/CLDR 版本或特定 fallback 字型。computed family 與 `document.fonts.check()` 都不證明實際 glyph font；UA Chromium 版本也不等於 ICU 版本。新增 `typography.js` 只讀原文字、codepoints、逐字 Range、固定日期的 Intl parts/resolvedOptions，以及 detached canvas 的有／無空白、字族與 ascent/descent metrics；不替換原 DOM 文字或 CSS。canvas 數值仍不是 DOM line-box 因果實驗。實際 fallback glyph 字型與 ICU 版本明確 UNVERIFIED。

native date 的相同 value `2026-10-10` 在 100% 為 Edge **151px**／Qt **139px**；屬於另一個控制項寬度差異，不由 kicker 高度解釋。125% 為 152／138.800003px，Qt border 0.8px／Edge 1px、height 39.200001／40px。未取得 UA shadow control／native picker 證據，不能指定唯一 intrinsic sizing 根因，也不調 input type、width 或 CSS 補償。

### 125%：量化特徵不等於可接受誤差

Chat stage y103／102.80000305175781，composer y617／617.6000366210938；Settings shell y279.78125／280.575。新的 `fractional_diagnosis()` 保留原值、CSS px delta、device px delta、CSS 1/64 grid 與 device 1/64 grid residual，另列非數值的 computed-style／文字差異。

stage Qt 值乘 1.25×64 後距整數約 0.000244，CSS×64 則約 0.200195；composer 對應約 0.002930／0.402344。這是與縮放後 layout quantization 相容的診斷特徵；**不是**「所有差異只是浮點尾數」的證明。computed border 0.8／1px 也代表 layout 輸入存在可觀察差異。Edge 以 Playwright device_scale_factor 採證、Qt 用 native scale multiplier，兩條縮放路徑並不因 DOM DPR 相等而自動等價。

strict raw geometry 仍要求完全相等；本輪更加入 deepGeometry 的精確比較。diagnostic residual 不參與 Gate 判斷、不做 rounding/tolerance，也不自動接受 font raster 差異。

### 200%：viewport 與 Windows 視窗容量

舊 Qt DOM **1280×711**，Edge **1280×720**，DPR 都為 2。舊 receipt 缺少 QScreen／frame／show 時序，尚不能證實 decoration／available-area clamp 是唯一原因。

新 host 保留 decorated top-level QWebEngineView，記錄 before/after show、resizeEvent、一次 post-show resize、DOM 量測時序，包含 QScreen geometry/availableGeometry/DPI/DPR、widget size/geometry、window/frame geometry/margins、winId、actual JS viewport。只補一次 show 後的 `resize(requested)`，不以額外高度、縮圖、裁切、zoom、frameless 或 fullscreen 掩蓋尺寸問題。fonts.ready + 兩個 rAF 後，至少兩次相隔 200ms 的原始 geometry 相同才採證（最多 8 次，整體 20 秒上限）。

若仍為 711，host 明確 FAIL／exit 1，仍保留真實 widget PNG、metadata 與 timeline；collector 將 host 的 FAIL 保持為 FAIL。容量診斷比較 requested client + 實測 decoration 與 available area；超出表示當下 decorated window 的 available-area 容量不足，仍須 reviewer 查時序才能確認 clamp。**本輪 sandbox 無法執行新 host，不能宣稱 200% 已修復或已量出可達尺寸。** Qt 的 [widget geometry 定義](https://doc.qt.io/qt-6/qwidget.html)、[availableGeometry 定義](https://doc.qt.io/qt-6.10/qscreen.html)、[high-DPI scaling 說明](https://doc.qt.io/qt-6.10/highdpi.html) 是採證欄位的依據，不是本機根因證據。

## 採證完整性與 History

`w1_smoke.execution_fingerprint()` 明列 11 個必須存在的 W1 entry/helper：host、protocol、geometry、typography、geometry diagnostics、capture、smoke、preflight、import probe、PowerShell relay、summary。缺檔直接拒絕。`fingerprint()` 另含 frontend src/fixture、build assets、HTML、Vite/TS/package config；舊 smoke 不可重用。preflight 記錄 `w1ExecutionFingerprint`，前後比對連 task 內 entry 漂移也必須 FAIL。relay 增加整輪 RelayBefore/After，summary 不使用 PowerShell 5.1 ConvertFrom-Json。

測試逐一改動 11 個 fixture 檔，確認 stale smoke 都被拒絕；另證明 task 內 execution hash 漂移時，即使 index/task 外 WIP 完全相同，preflight 仍 FAIL。這提供採證程式及產物的 SHA lineage；沒有宣稱所有瀏覽器、OS 字型、ICU、native dependencies 都是 hermetic/reproducible 環境。

History 使用獨立 context／Qt process，URL 載入 Chat，再真的觸發 `[data-history-toggle]`；量測必須同時證明 `.stage.has-history`、drawer 與 stage／viewport 有正向交集、相關 Web Animations 無 running/pending，以及兩次相隔 200ms 的 raw geometry 穩定。保留原始 rect 和交集，不 move／縮放；無 animation API 時也不當作已穩定。負例涵蓋 class 存在但 drawer 在畫面外、在 viewport 內但 stage 外，以及動畫未結束。Edge 每次穩定性嘗試另存 `*-baseline-stability.json`，失败也保留 raw rect；Qt raw geometry 與時序在 host receipt。Edge／Qt 各存獨立 geometry/PNG，不把 Chat 圖重新命名。matrix 規劃 2 viewports × 4 views × 3 DPR = 24 pairs，fatal viewport/security/readiness 問題仍停止該 run。**本輪新 History pairs 尚未實機執行，UNVERIFIED**；browser click／Qt JS click 也不等於 native mouse/keyboard/IME 證據。

native date picker、IME、native focus/tab、security-negative navigation/resource/download/permission probe 均 UNVERIFIED。既有 synthetic protocol mutator-rejection tests 只證明隔離 protocol，不算 native 安全驗收；未觸發真實 provider／DB／WS。

## 本輪驗證與保全

所有本輪證據在 [`.runtime/w1-convergence-20261011T061607Z/`](.runtime/w1-convergence-20261011T061607Z/)。`Before.json` 保存精確 435 路徑（64 M／34 D／337 ??）、1,253 個現存 source/WIP SHA、index SHA；`Before.diff`／`Index.diff` 及 `preimages/` 保存修改前資訊。HEAD `af83df273602be3a616d6567855ea71d61a9ace7`、main；六原檔對照 `995c23c7c8d1be62000229d58610d2214f3bb745`、W0 與 manifest 相符；G7 35/35 absent。`RealEvidenceHashes.json` 保全上述四組歷史 evidence，`FinalAudit.json` 記錄最終逐檔差異與 hash 核對。

- `validation/Results.json`：typecheck、original-build、10 suites 全 exit 0。
- `validation-followup/Results.json`、`validation-history/Results.json`：manifest／History 補強後，重跑受影響的 suites。合併各 suite 最後結果為 **48 tests PASS**；沒有執行 W2–W7 suites。
- `native-import.process.json`：task `.venv` Python 3.13.9 的 `-I -B w1_import_probe.py` **exit 2**。PySide6、PIL、playwright import 均 PermissionError 13，未到 Qt DLL/GPU/render；不升權或改 ACL。
- `real-evidence-summary.process.json`：stdlib summary 成功讀取舊 JSON，按真實 W1 FAIL 回傳 **exit 1（預期）**。完整資料在 `RealEvidenceSummary.json`，人可讀輸出在 `real-evidence-summary.stdout.log`。
- syntax、PowerShell AST、scoped diff whitespace 與工具版本命令／exit／logs 見 `checks/`。實際 argv、cwd、exit、elapsed 都保存在各 receipt。

離線重跑（output 使用新名稱）：

```powershell
Set-Location C:\project\desktop-agent-runtime
& .\envs\kuro-llm310\python.exe -B .\devtools\original-git-web-host-20261010\validate_candidate.py --output .\devtools\original-git-web-host-20261010\.runtime\w1-review-new --only typecheck original-build parity_collection parity_diagnosis w1_smoke deep_comparison w1_convergence preview_protocol test_geometry test_deep_geometry test_typography preview_bridge.test
```

## 正常 Windows 使用者 relay 與停止點

在正常互動 PowerShell 執行，不用管理員、不改 execution policy、不安裝依賴。沿用 task `.venv`，本機 smoke/typecheck/build 後，各 DPR 自建新證據目錄與 disposable browser context；無舊證據覆寫。

```powershell
& 'C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010\Invoke-W1WindowsRelay.ps1'
```

看新 relay 目錄的 `ReadableSummary.json`、`MatrixExits.json`、`RelayBefore.json`／`RelayAfter.json`，以及每對 `*-diagnostics.json`、`*-qt.json`／PNG。FAIL/BLOCKED 會保留非零 exit；即使 capture 全部成功，gateW1 也只到 UNVERIFIED。summary 的 exit 0 僅代表提供的 receipt 沒有 FAIL/BLOCKED，不是 Gate PASS。

獨立 reviewer／使用者需確認：Today glyph／linebox／date root cause、125% 實際 layout 差異是否可接受、200% requested 與 actual viewport、History 開啟 pair、native interaction／IME／安全負面證據。未確認前 **W1 FAIL 保留；W2/W3 本輪未開始且 native UNVERIFIED，正式 UI cutover BLOCKED。**

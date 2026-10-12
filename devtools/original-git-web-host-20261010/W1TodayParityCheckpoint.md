# W1 Today parity 診斷 checkpoint — 2026-10-10

**Gate W1：FAIL。W2 未開始。** 本輪只讀既有真實 Windows 使用者採證並修改隔離採證 helper；沒有在 Codex sandbox 啟動 Qt、瀏覽器、provider 或 production。使用者正常身分已成功 import/render；Codex sandbox 的 package ACL 限制是另一執行身分，沒有重試安裝、ACL 或 import。

## 證據與範圍

- 原始證據：[ParityResult.json](.runtime/parity-msedge-1-20261010T071240461324Z/ParityResult.json)，captureStatus/gateW1 FAIL，exit 1，停止原因 `Geometry/token mismatch`。
- 有效 smoke：[SmokeResult.json](.runtime/w1-smoke-20261010-150828-233/SmokeResult.json)，smoke PASS，完整 W1 UNVERIFIED。此次只改 capture driver/診斷/測試，實測其 sourceFingerprint 仍與目前 renderer/host/fixture/build 相符。
- 詳細診斷：[Diagnosis.json](.runtime/w1-today-parity-diagnosis/pixels-v2/Diagnosis.json)，含每個 selector/value delta、context、區域像素統計、平移取樣實驗及原證據 37 檔 SHA256 前後清單。
- 以 native `view_image` 檢視 Chat、Settings、Today 各自 baseline/Qt/diff 共 9 張 PNG。這是本輪診斷觀察，**不是獨立 reviewer 驗收通過**。
- stdlib PNG decoder 核對每個像素：既有 diff PNG 等於 abs(baseline RGB − Qt RGB)，三組原始 MAE/RMS/changed fraction 完全一致。未修改或產生替換 screenshot。

## 確認事實

共同 viewport 1280×720、DPR 1、navigator.language `ja`、timezone `Asia/Taipei`、fontStatus `loaded`；HTML `lang=zh-Hant`。Edge version `154.0.4258.62`，UA Chromium 154；Qt 6.11.1、UA Chromium 140。Qt offTheRecord=true、platform=windows。screen 尺寸/色深不同（Edge 1280×720/24，Qt 2560×1440/32），不能把 screen 欄位當作 viewport 不同。

16 個 CSS tokens 三組完全相等，包含原版字型 stack。相同 computed font stack 與 `fonts.status=loaded` **不證明實際 glyph fallback face、字型 metrics 或 rasterizer 相同**。

| View | 既有 measured selector 差異 | changed pixels / fraction | MAE RGB | RMS RGB |
| --- | --- | --- | --- | --- |
| Chat | 無 | 16119 / 0.017490234375 | 0.65512, 0.66074, 0.68319 | 8.90067, 8.73371, 8.66836 |
| Settings | 無 | 19435 / 0.021088324653 | 0.09745, 0.10302, 0.12549 | 1.28943, 1.35916, 1.48987 |
| Today | `.local-schedule.y`: 493.921875 → 496.921875 | 46859 / 0.050845269097 | 3.30658, 3.19858, 3.31499 | 21.23601, 20.17980, 20.67659 |

Today schedule 的 x=122.5、width=1104、height=219.984375 相同，其餘已測 selector 相同。未被 geometry.js 測量的子元素不可推定相同。視覺上 Chat 的部分訊息/時間文字、右側 controls 仍有差異；Settings 主要呈現細小文字邊緣差異；Today 有明顯重疊邊框與區塊位移，日期 input 及後續 toolbar controls 亦不同。

區域取樣為固定 screenshot 座標（不是新 DOM rect），完整範圍見 JSON，分區互不重疊且覆蓋整張圖：

- Today header y=103..260：10710 changed pixels，佔全部差異 22.86%；priority y=260..480：11107，23.70%；schedule y=480..720：22769，48.59%；其餘 shell/rail 4.85%。
- Today 46859 個差異像素中，42726 的最大 RGB channel delta >8，32000 >32。這些只是描述分布的統計，**不是調寬的 acceptance threshold**。
- Chat 差異約 45.11% 位於 messages，27.51% 位於 header；5845 個像素 channel delta >32。不能全部說成反鋸齒。
- Settings 19435 個差異像素中僅 181 個 channel delta >32，配合圖像觀察，與細微 rasterization 差異一致；尚未確認實際字型/繪製根因。

只在數值分析中比較 baseline(x,y) 與 Qt(x,y+3)，不平移 screenshot、不替代原始 gate 統計。三 channel 平均 MAE：

| 區域 | 原始取樣 | Qt +3px 取樣 |
| --- | ---: | ---: |
| Today 大標題 | 14.57952 | 0.37278 |
| Today summary | 4.32419 | 0.11578 |
| priority | 2.94111 | 0.04805 |
| schedule | 5.00155 | 1.42329 |

0/1/2/3px 全部實驗保存於 JSON；以上區域皆以 +3px 最接近。priority MAE 約下降 98.4%，支持上游位移而非單純反鋸齒；Schedule 的殘差較大，與日期 input 自動寬度/toolbar 橫向差異一致。**沒有把對齊後數值當作 PASS。**

## 原版 source trace 與根因界限

- `frontend/src/work-panel/main.ts:1166–1223`：renderToday 依序 append header（date kicker → h1 → summary）、`.today-primary`（priority block）、`schedules.root`。本 fixture priority 是空清單，顯示 `.empty-state`。
- `styles.css:636–650,1331–1397,734–749`：frame padding-top 30px；kicker margin-bottom 7px、data-font 10px，未指定 line-height；h1 margin 0、clamp font-size、line-height 1.17；summary margin-top 18px、12px、flex，未指定 line-height；priority margin-top 40px；block heading min-height 28px、margin-bottom 12px；empty-state min-height 150px。
- `styles.css:22`：schedule margin-top 固定 34px。其 y 依前述 header/priority 正常文件流高度累積。schedule 自身 height 不變且 heading/summary/priority 像素同樣下移 3px，支持差異在 schedule 之前已發生；不能用修改 margin-top -3px 掩蓋。
- `model.ts:99–104`：日期明確使用 `Intl.DateTimeFormat("zh-TW", {month:"long",day:"numeric",weekday:"long"})`，不是 navigator.language `ja`；預設日期為 `new Date()`。圖片日期皆 10 月 10 日，但 kicker 星期前的視覺間距不同，**尚無 textContent/codepoints 證據確認實際字串差異**。
- `schedule.ts:68–71` 建立原生 date input；`styles.css:23–25` 使用 `font:inherit`、width:auto。這會讓原生控制項 intrinsic size 參與 toolbar 排版；兩個 Chromium 世代的差异是一個合理待驗假說，不是已確認原因。

目前最窄的假說是 kicker 或其他 header inline line box 的 normal 行高/字型 fallback 差異，因為 heading 起就出現約 3px 位移。Chromium/ICU 日期格式、原生控制項 metrics、capture settling 也需區分。既有 JSON 沒有 header/kicker/summary/priority 的 rect、各 text node line box、實際 glyph font 或連續時序樣本，**不能從這批證據唯一解出是哪個元素增加 3px**。不以 Chromium 版本不同直接宣告可接受。

## 最小 helper 修改

僅 `capture_parity.py` 新增 opt-in `--collect-geometry-drift`：

- 預設仍在 geometry mismatch 停止。opt-in 才繼續下一 view/viewport，完全精確比對，沒有 epsilon/tolerance。
- 每筆比較先保存 Comparison.json 與 ParityResult.json。任何 geometry mismatch 留下 comparisonFailures、FAIL、exit 1；後續成功或 infrastructure error 不能清除/降級 FAIL。
- tokens 不同/缺少仍立即停止；另外與有效 smoke 的完整 token 字典比對，避免非三個最低限度 tokens 同時缺失被誤判相等。
- import/environment、source/build fingerprint、locale/timezone/DPR/font context、既有 Qt render/bridge/off-record/platform/PNG validation 仍是停止條件；source fingerprint 另在每個 case 前檢查。
- 沒有修改 geometry.js、Qt host、六原始 source、frontend entry、fixture、安全設定或 production。完整 capture 無 drift 仍只能 gateW1 UNVERIFIED；History pair、Qt 互動、原生鍵盤/IME、安全 runtime probes 與 reviewer 尚未完成。

## 本輪驗證與重現

17 個 stdlib/Node contract tests PASS，4 個 Python AST syntax checks PASS，exit 0；[Validation.json](.runtime/w1-today-parity-diagnosis/Validation.json) 與 stdout/stderr 同目錄。fake child failure 測試內故意產生的 FAIL 是測試 fixture，不是真實 Qt 執行。本輪沒有 UI/source/build 變更，因此沒有重建 frontend 或啟動 runtime。

repo before/after guard 見 [.runtime/w1-today-parity-diagnosis](.runtime/w1-today-parity-diagnosis)：main/HEAD W0 af83df273602be3a616d6567855ea71d61a9ace7，六原檔 SHA 與 W0/995c23c7c8d1be62000229d58610d2214f3bb745/manifest 比對；index、task 外 WIP 與 evidence preservation 結果见 FinalAudit.json。無 stage/commit/push。

離線重現（output 必須是新目錄）：

```powershell
Set-Location C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010
.\.venv\Scripts\python.exe -B -m unittest test_w1_smoke test_parity_collection test_parity_diagnosis -v
.\.venv\Scripts\python.exe -B diagnose_parity.py --evidence .runtime\parity-msedge-1-20261010T071240461324Z --output ('.runtime\diagnosis-' + (Get-Date -Format yyyyMMdd-HHmmss-fff))
```

下一步由正常 Windows PowerShell 執行六個 case 的 DPR1 採證（每次自建 timestamp 新目錄，保留旧證據）：

```powershell
Set-Location C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010
.\.venv\Scripts\python.exe -B capture_parity.py --channel msedge --scale 1 --smoke-result .runtime\w1-smoke-20261010-150828-233\SmokeResult.json --collect-geometry-drift
$LASTEXITCODE
```

若仍有 geometry drift，預期完成可採證 case 後 exit 1 / gate FAIL；若遇 fatal validation，立即停止且保留已完成證據。先看 receipt 判斷，不要用「六組都有 PNG」當作 PASS。確認沒有 fatal blocker 後，可分別將 `--scale` 改成 `1.25`、`2`，逐輪人工讀取狀態，不以迴圈忽略錯誤。

若後續要確認 +3px 根因，需另一次 W1 **measurement-only** 採證：兩端同時量測 `.today-frame > header`、`.section-kicker`、`.today-question`、`.today-summary` 及子元素、`.today-primary`、priority `.block-heading`/`.empty-state`、`.local-schedule`、`.schedule-toolbar input/select/button` 的 rect、line-height/font-family/font-size/font-weight/margins、textContent codepoints、date value/Intl resolvedOptions，並在 fonts.ready + 兩個 rAF 後重測驗證穩定性；必要時確認 actual platform glyph fonts。本輪未擅改 Qt host/geometry fingerprint 取得這些新值，也不捏造數據。若修改 measurement fingerprint，必須先產生新的 smoke receipt。

現有資料足以確認 W1 parity defect 與上游位移，仍不足以批准 UI fidelity 或指定字型根因。保留 FAIL，交獨立 reviewer 複查，W2 維持未開始。

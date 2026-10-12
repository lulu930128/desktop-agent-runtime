# W6 第二次 getState 超時：根因、驗證與接力

2026-10-11。只修 W6 owner projection 與 reply completion。正式入口仍是 Widgets，`RELEASE_PIN=None`。沒有新增 service、改 Controller/Pet lock、timeout、retry、sandbox、原版六檔、VBS 或 production profile。

## 證據與根因

新 run：[w6-status-20261011T130913527233Z](.runtime/w6-status-20261011T130913527233Z/)。

1. `UserEvidence.json` 保存使用者兩份 NativeResult、兩份 NativeError 與 RelayResult 的 SHA256。兩輪各 49 PASS、`loadFinished=true`、connections=1、sourceUnchangedDuringRun=true；全部 12 個 source hashes 與本次修改前一致。兩輪錯誤同為 `w6_existing_window.py:312` synthetic Pet 後 `getState` 超時。原始 receipts 未改。
2. `Qt-before.json` 使用真 Controller/Adapter/Port、Qt event queue、isolated Core/WS/Memory 與 synthetic Pet。第二次 status 234 ms 返回，`status_inflight=false`、waiters=0、Broker pending=0。Pet lock acquire/release、read_runtime_status、presentation、diagnostics、queued delivery 與 Broker response 都有 monotonic timing；worker 不在 GUI，結果於 GUI 完成。refresh_status 與明確 getState 同時等待一次 read。此 reproduction 排除 coalescing、Pet lock、worker 未返回、identity cancellation、Broker 20 秒 timeout 為本次必要原因；不宣稱所有可能的其他環境 hang 都已排除。
3. 真實 Adapter 原先把 `presentation_state()` 的 Live2D descriptor 當成 `capabilities.launcher`，原版型別卻要求 lifecycle snapshot（含 `voice`）。原版 `main.ts::renderChrome` 在 WS connected、Pet ready 時讀取 `launcher.voice.state`，缺欄即 TypeError；Pet unavailable 時短路，所以第一次成功。Node regression 直接從原版 AST 取出完整 renderChrome 方法執行，未修改 renderer。
4. `OwnerTransport.response` 原先在通知 onState 前清掉 pending 與 timer；listener 拋 TypeError，`item.done` 永遠不執行，連 25 秒 transport timeout 都無法再完成它。Node regression 在超過原 timer 後仍觀測 orphaned Promise，符合 native harness 的 25 秒超時。原生歷史 receipt 未保存 JS exception stack；此因果鏈由一致 source、真 Qt 輸出形狀及原版 JS 方法重現證明，修後正常桌面驗證仍待接力。

## 最小修正

- `qt_web_adapter.py`：launcher capability 使用既有 `read_companion_diagnostics()`；diagnostics 失敗時傳 `null`，不偽造 voice available。Live2D descriptor 獨立保留為 `presentation`；diagnostics 本身不刪。
- `owner-bridge.ts`：已通過 identity/result 檢查的回應，在 `finally` 完成 Promise。presentation exception 仍拋出，不吞錯、不重送、不更改 owner mutation 結果。
- fixture/probe/native harness：只在 synthetic fixture 加 stage、elapsed ms、GUI thread、waiter 數與結果布林；不記 token、raw status、raw response 或 exception text。native 加入 synthetic lifecycle contract 與全流程 JS listener error gate。原 64 個 required checks 均保留，新增 2 個；錯誤只存 line/column，未記 DOM/訊息內容。

## 驗證

- `fail-before-confirmed/`：新 contract regression 在修前失敗；原版 renderer 分支重現成功；Promise regression 因 orphaned=true 失敗。既有 state test 已改為檢查分離的 presentation，修前另有預期 KeyError。更早的 `fail-before/` 含測試 DOM helper 缺少 text 的建置錯誤，保留但不作根因證據。
- `Qt-after.json`：第二次完成 250 ms、launcherHasVoice=true、waiters/pending=0、connections=1；不是效能 benchmark，前後差值沒有效能含義。
- `targeted/`：相關 suites 與 typecheck PASS。完整回歸以 `full-final/Results.json` 為唯一不重複計數基礎；沿用前次 ValidationSummary 的全部 26 組，新增 3 tests，共 309 tests，typecheck 包含於 26 組。較早的 `full/` 同為 309 PASS；末次重跑原因是 native Live2D 缺席 assertion 同步至獨立 presentation 欄位，並加上 source 防回歸檢查，沒有屏蔽該 check。
- `OwnerBuild.json`：四個資產 STAGING_VERIFIED；fingerprint `dc7ad8b776312ab6c40102591d2bbe822707af44c776032cb041ae2bbfa2402e`，manifest SHA256 `c2920dff0455acfdbee2fcb9ae0a0f42cd1aa6c9d6b1690d54da5e377b765bed`。這是新不可變 staging bundle，不是正式 RELEASE_PIN。
- `native-final/RelayResult.json`：精確正式 Windows Python `-I -B`、真 existing window、順序 restart 兩輪；兩輪 actualExit/reportedExit=2，restartObserved=true。Codex 環境 renderer exit49、loadFinished=false、native **BLOCKED**；未透過提權、安裝、Qt flags 或禁用 sandbox 重試。較早 `native/` 也保存，最終 source identity 以 native-final 為準。

## 原生未驗項目

先前正常使用者兩輪的 PASS 原樣保存。其未到達的項目仍未由修後正常桌面證明：capture-synthetic-owner、notification-dedup-synthetic-display、schedule-item/mutate-replay、subscription-methods、stale-request-rejected、unknown-mutation-fenced、DOM focus、injected IME/composition Enter、三頁 screenshots、loopback-probe-reachable、scheme-network-storage-denied、navigation-denied。

新 Codex pair 在 renderer 啟動即受阻，完整逐項缺項見兩份 NativeResult 的 `coverage.missing`；新增兩個 checks 也未到達。實體中文 IME、DPI/多螢幕/尺寸、OS toast、真 Pet/Live2D/Voice 與人工畫面驗收均 **UNVERIFIED**。source tests 與 synthetic notification display 不替代這些項目；不執行真裝置或 production IO。

## 正常互動式 PowerShell 接力

命令建立全新 scoped run，沿用正式 Addons，不載正式設定、不啟真 Pet/Voice、不用 production ports；只開 SYNTHETIC 隔離視窗，restart 一次後退出。

```powershell
Set-Location 'C:\project\desktop-agent-runtime'
$w6Stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffffffZ')
$w6Out = Join-Path (Get-Location) "devtools\original-git-web-host-20261010\.runtime\w6-status-user-$w6Stamp"
& '.\envs\kuro-llm310\python.exe' -I -B '.\devtools\original-git-web-host-20261010\run_w6_existing_window.py' --output $w6Out
Get-Content (Join-Path $w6Out 'RelayResult.json') -Encoding UTF8
```

只有 RelayResult 真正得到 `AUTOMATED_NATIVE_PAIR_PASS`，兩輪 sourceSha256、bundle、coverage 與當前 source 相符，才可提交下一個 reviewer gate。這條命令不啟用正式入口。若仍失敗，保留 NativeError、NativeResult.syntheticTiming、javascriptErrors、coverage 與原始 receipts；不增加 timeout、不自動 retry、不填入 PASS。

獨立 source/Qt 診斷可用相同正式 Python `-I -B` 執行 `w6_status_probe.py --output <全新 task .runtime JSON 路徑>`；它不建立 WebEngine，也不代表 native acceptance。

## 保全與 rollback

起點 main / `af83df273602be3a616d6567855ea71d61a9ace7`、479 dirty paths。`Before.json` 保存 Git-visible hashes、index、allowlist；`preimages/` 保存本次七個既有檔的 exact bytes。最終 `Preservation.json` 記本輪變更與新檔、index/HEAD/branch、六個 originals/Git bytes、G7 35 absent、歷史 receipts 與 native source/bundle 驗證。新 staging bundle 保留，不覆寫舊 bundle。

本輪 delta 相對 preimages，不能用 HEAD 還原 WIP。只檢查回滾能否套用：

```powershell
git apply --reverse --check -- 'devtools/original-git-web-host-20261010/.runtime/w6-status-20261011T130913527233Z/W6StatusDelta.patch'
```

實際回滾未執行。若未來授權還原，先核對 current hashes 等於 postimages；只還原本次七檔 bytes，並逐一處理本次新增的 probe 與本文。任何 mismatch 都停止，不 reset/clean/stash/checkout、不碰其他 WIP。正式 pin 原本就是 None，不需切 VBS 或 Widgets；沒有 W7、commit/push 或正式採用。

# W6 安全逐軸收據與原生接力

2026-10-11。**原生仍 BLOCKED，尚不能指出使用者原始 FAIL 的唯一或多個子項，也未證明存在 WebHost 防護漏洞。** 本輪完成測試可觀測性、依副作用判定的斷言與負面回歸；正式入口、RELEASE_PIN=None、Widgets/VBS 與 W7 均未改。

## 授權範圍與驗收

只處理既有 W6 WebHost 安全邊界、disposable fixture 驗證與收據。順序為核對原始收據／preimages、補逐軸 evidence、回歸、正式 Python parent/restart、保全核對。禁止讀寫 private profile、操作 Voice :18890、修改原版六 renderer、降低 CSP／asset allowlist／sandbox，亦不提交或推送。

正常 Windows parent/restart 兩輪均須完整通過原 66 個 REQUIRED_CHECKS 及新增四個安全 gates，且 source/bundle 身分一致，才能升級 native gate。Codex 的 renderer 啟動阻擋不等於使用者桌面失敗，也不等於安全防護成功。

## 原始收據核對

基線為 [W6StatusTimeout.md](W6StatusTimeout.md)、[W6FinalCheckpoint.md](W6FinalCheckpoint.md) 及最新 owner bundle。新 evidence 根為 [.runtime/w6-security-20261011T133551558915Z/](.runtime/w6-security-20261011T133551558915Z/)。

`UserEvidence.json` 保存使用者 `w6-status-user-20261011T1323557749487Z` 的兩份 NativeResult、兩份 NativeError 與 RelayResult hash。两輪都是 67 PASS、1 FAIL、native FAIL / exit2、loadFinished=true、connections=1、JS errors=[]；12 個 source hashes 均與修改前相同。唯一失敗 check 是合併的 `scheme-network-storage-denied`，不是已知唯一失敗安全子項；navigation 與 presentation listeners 因 fail-fast 未到達。

原合併 check 要求 `fetch(loopback)` 拒絕、`fetch(kuro-work://app/denied)` 拒絕、`window.open(...) === null`、`localStorage.setItem(...)` throw，且 Python HTTP200 後 server hits 不增加。歷史收據沒有四軸值，不能從合併 false 反推 popup 或 storage 是根因。

## 四軸拆解與副作用

| 軸 | 真正邊界與舊斷言不足 | 新版證據與失敗條件 |
| --- | --- | --- |
| Network | CSP `connect-src 'none'` 與 Requests allowlist；fetch rejection 本身無法排除請求先送出再失敗。 | Python 先驗 disposable loopback HTTP200。記 settled/rejected、probeHitsBefore/After；hit 有增量、fetch resolve、missing 或 timeout 均失敗。 |
| 非 allowlist asset | Fetch 可能先被 CSP／scheme fetch 支援擋住，尚未測到 handler。 | 保留 `/denied` fetch；另以同源 `/denied.js` script subresource 測 allowlist。必須 error 且 settled、host assetBlocked/handlerDenied 增加、沒有新增 asset reply。沒有修改或注入允許資產。 |
| Popup | `JavascriptCanOpenWindows=false`、Page.createWindow 回 None、newWindowRequested 未交給任何 openIn recipient。JS 回傳 null 不是實際 page/window 建立證據。 | 分別嘗試原 denied scheme、about:blank、disposable loopback。記 returnNull/returnUndefined/threw、drain 後 handle 狀態、Qt 拒絕／discard 計數、page/view/window inventory 與 transient creation events；要求沒有新物件／建立事件、沒有可用 handle、主頁未改、沒有 HTTP hit。回傳值只保留診斷，不能單獨過關。 |
| Storage | 正式 owner-bootstrap 已把 `localStorage` 換成五種 allowlisted 展示偏好的記憶體 Map；任意 key 必須被拒。原生 Chromium LocalStorageEnabled=false、off-record profile 與這個 Map 是不同邊界。 | 對不允許的 synthetic marker 記 before/read/writeReturned/writeThrew/after，要求不可讀回。測 sessionStorage/indexedDB/caches 的拒絕。DocumentCreation 在 bootstrap 前讀寫同一 marker，兩次同-profile reload 皆須無殘留；parent/restart 共用 marker 但各用 off-record profile。只保存 absence/throw 布林，不保存內容。 |

Qt 官方文件說明 [createWindow 與 newWindowRequested](https://doc.qt.io/qt-6.11/qwebenginepage.html#createWindow)、[off-record profile](https://doc.qt.io/qt-6.11/qwebengineprofile.html)。這些 API contract 支持將回傳值與副作用分開驗證，**不證明本機舊 FAIL 的根因**。

WebHost 只增加固定 key、thread-safe 的 native counters，以及不呼叫 openIn 的 request observer；未更改任何 allow/block 判斷。沒有新的 HTML callable bridge。CSP、permission/download/filesystem denial、asset bytes、browser settings 與 sandbox 保持原樣。

四個新增 checks 與舊合併 gate 全保留。安全失敗改為 deferred failure，仍使 coverage 與 exit 失敗，但繼續測 navigation。navigation 現在測外部 custom host、同源非 allowlist 與 disposable HTTP URL，要求三次拒絕 callback、原頁不變、HTTP hits 不增加。presentation/listener gate 也必須實際執行；缺項不能 PASS。

## Reviewer 增量：reload 後 JS 錯誤

核對 reviewer 指出的位置時，當時程式在第一次 save 前已有 `evidence['javascriptErrors'] = read('window.w6Errors')`，因此不能宣稱必然 KeyError。可維護性與 missing/malformed evidence 防護仍有改善空間。

現改為 evidence 建構時明確初始化 `javascriptErrors=[]`、`javascriptErrorSamples={}`、`javascriptErrorsComplete=false`，第一次收據即存在。initial、beforeReload、nativeFirst、nativeReload 四份樣本都須是有效 array；任何缺漏／malformed 保持 incomplete，後續空 array 不能洗掉失敗。每次 DocumentCreation 重裝 ErrorEvent listener，再經 Python allowlist 僅保留固定 kind 與整數 line/column。message、stack、source URL 等全部不寫入收據；最終 NativeResult 也使用相同 sanitizer。

`presentation-listeners-no-error` 同時要求四份 evidence 完整、累積 errors=[]、目前頁面實際 array 為空。不能把 missing 當作空陣列，也不清掉前一頁已記錄的錯誤。負面測試涵蓋 reload 後空／非空／missing／malformed、敏感字串過濾，以及執行真正的注入 JS listener 接收合成 ErrorEvent；這是 source/JS 回歸，不宣稱 native reload 已驗證。

## 驗證收據

- `FailBeforeConfirmed.log`：新增「先保存逐軸 evidence、不得跳過後續 gates」回歸在舊 harness 明確失敗。較早 `FailBefore.log` 另含缺少 PYTHONPATH 的四個 import errors，保留但不作安全根因證据。ReviewerFailBefore 保存新增 collector 尚未實作時的三個缺介面失敗，不冒充重現原生 KeyError。
- `validation-final/Results.json`：前次完整 26 組、309 tests 的全部原命令重跑；原 suite 增加 1 個 test，加獨立安全 suite 13 tests，**27 組、323 tests、typecheck 全 PASS**。早期 validation 的 318 tests 保留；末次重跑因 reviewer 修改，不重複計數。
- 負面回歸包括「rejected 但真的有 hit」、「asset fetch denied 但無 allowlist evidence」、「回 null 卻建立 popup」、「write 後 throw」、「跨 reload 殘留」、「缺 evidence」、「JS errors 含敏感內容」均不得通過。直接執行正式 host 的 denial callbacks 及真 owner-preferences/JS probe；未放寬正式設定製造測試。
- `OwnerBuild.json`：最新既有四資產 bundle STAGING_VERIFIED，fingerprint `dc7ad8b776312ab6c40102591d2bbe822707af44c776032cb041ae2bbfa2402e`，manifest SHA256 `c2920dff0455acfdbee2fcb9ae0a0f42cd1aa6c9d6b1690d54da5e377b765bed`；未 rebuild／改資產。
- `native-final/RelayResult.json`：正式 Python -I -B、真正既有 window、parent PID76516 與 restarted PID14000；OS／reported exit 均2、restartObserved=true。兩輪 renderer exit49、loadFinished=false、native BLOCKED；四軸均 NOT_REACHED/null。兩份 SecurityEvidence 明確保留未觀測，沒有填入 true。較早 native pair 也保留。

因此本輪沒有正常桌面四軸 truth data，仍不能指出原始唯一失敗子項、證明 popup API 行為或宣告安全漏洞已修好。不得把 323 個測試或 Qt callback source evidence 升級成 native PASS。實體 IME、OS notification、真正 Pet/Voice/DPI 等原人工限制照舊。

## 正常 PowerShell 單條接力

在正常使用者互動式 PowerShell 執行；使用既有正式 Python、全新 disposable run，完整跑 parent/restart。只啟 synthetic fixture，不讀正式 profile、不碰 :18890，不改 Qt flags、不提權：

```powershell
& 'C:\project\desktop-agent-runtime\envs\kuro-llm310\python.exe' -I -B 'C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010\run_w6_existing_window.py' --output ('C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010\.runtime\w6-security-user-' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffffffZ'))
```

新 run 的 `first/SecurityEvidence.json` 與 `first/restarted/SecurityEvidence.json` 會記四軸、legacyPredicates、hit counts、Qt counters 與 storage/error samples。對照 `NativeResult.coverage`、sourceSha256、bundle 與 RelayResult；只有兩輪全過才是 AUTOMATED_NATIVE_PAIR_PASS。若失敗，保持收據，不調 timeout、不關 sandbox、不移除 required gates。

## 保全與 rollback

起點 main / `af83df273602be3a616d6567855ea71d61a9ace7`、481 dirty paths。`Before.json` 保存 1,332 Git-visible paths 的 exact hashes、index 與修改 allowlist；`preimages/` 保存四個既有檔案。`Preservation.json` 核對新增／修改範圍、HEAD/index、六個 original Git bytes、G7 35 absent、舊收據與歷史 preimages。正式 pin、VBS、Widgets 與其他 WIP 以 byte hash 核對。

只做 reverse 可套用性檢查，沒有實際 rollback：

```powershell
git -C 'C:\project\desktop-agent-runtime' apply --reverse --check -- 'devtools/original-git-web-host-20261010/.runtime/w6-security-20261011T133551558915Z/W6SecurityDelta.patch'
```

未來若授權回滾，先核對 postimages；僅還原四個 preimages 與精確處理本轮新增的 probe、test、本文。任何 hash 不符即停止；不用 HEAD/reset/checkout/clean 覆蓋 WIP。沒有 commit/push、W7 或正式採用。

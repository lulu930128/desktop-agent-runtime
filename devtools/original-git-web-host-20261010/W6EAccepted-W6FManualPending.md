# W6.E 已驗證／W6.F 待人工採用

2026-10-11。裁決：**W6.E automation PASS（AUTOMATED_NATIVE_PASS）／W6.F adoption MANUAL_PENDING／W7 僅限 source、套件及隔離工程 readiness**。沒有正式採用、Widgets 刪除或全部封版。

本輪工作是獨立核對使用者在 21:57 Taipei 完成的 Windows 原生雙輪，再準備未套用的 source pin、負例回歸、退役圖與交接。產品方向依 repo AGENTS 與四份 docs/product 文件：單一 Qt UI、既有 owner、domain truth 不移到展示層。禁止 production main、私人 profile、真裝置／provider、Voice :18890、VBS／shortcut 修改。

## 證據定位與信任範圍

- 使用者原始證據：[w6-security-user-20261011T1357535580236Z](.runtime/w6-security-user-20261011T1357535580236Z/)。完整原件保留。
- 本輪證據：[w6e-review-20261011T140713669061Z](.runtime/w6e-review-20261011T140713669061Z/)。`Before.json` 保存 main／HEAD `af83df273602be3a616d6567855ea71d61a9ace7`、484 dirty paths、1,335 Git-visible paths hashes 及 index SHA。
- 可機器重驗：[candidate-reviewed/W6EAccepted.json](.runtime/w6e-review-20261011T140713669061Z/candidate-reviewed/W6EAccepted.json)，包含逐輪 checks、全部 source SHA、完整 raw tree hashes；[ReleaseCandidate.json](.runtime/w6e-review-20261011T140713669061Z/candidate-reviewed/ReleaseCandidate.json) 包含精確 pin、凍結 assets、dry-run、負例與 proposed patch SHA。
- Raw NativeResult／SecurityEvidence／FormalPreflight 是**未簽署的使用者原生觀測 JSON**。SHA 保全內容，不認證觀測者。Ed25519 只驗 bundle pin；builder self-attestation 不等於外部 publisher trust。
- 本輪 reviewer 是獨立 Codex 子代理讀碼、direct filesystem hash 與限定 source 重驗；原生觀測來自使用者互動式 Windows run，不來自本輪 mock 或自我宣告。工程 reviewer 不能替使用者批准視覺或正式採用。

## W6.E 逐項裁決

| 項目 | 已核對結果 |
| --- | --- |
| Parent／restarted | PID 26172／77220；actualExit=reportedExit=0／0，restartObserved=true，兩輪 native=AUTOMATED_EXISTING_WINDOW_PASS。 |
| Coverage | 每輪 74 個 unique checks 全 true；70 required 與當前 harness AST 完全相等，missing=[]。navigation 另核 deniedCallbacks=3、probeHits 1→1。 |
| Source | 每輪精確 13 路徑以 `Path.read_bytes()` 重算，全部相等；sourceUnchangedDuringRun=true。大檔 qt_app SHA `8d882d0563d44993606a414ef8114e4bb49da55adfcd34d293debb25aaaee4fe`；qt_controller SHA `c75a3a4642ee79252c4bd4ba25800a4f8c90c26aceb25528a8eedada4f075bab`。 |
| Owner／lifecycle | 真 KuroQtLauncherWindow、windows platform、WS connections=1、controllerCloseCount=1、brokerClosed=true。source lexical graph 四種 owner 各一，與 native checks 一致；不將 lexical count 當 runtime proof。 |
| Security | 分離 SecurityEvidence 與 NativeResult.security 完全一致；canonical evaluate_security 重算 network／asset／popup／storage 四軸 true。HTTP 1→1、script blockedByHost=1／unexpectedReplies=0、popupDenied=1／discarded=1／newObjects=0。 |
| Storage／JS | off-record、LocalStorage disabled；展示偏好記憶體層与 native/reload samples 分開驗，marker absent；4/4 JS samples complete，errors=[]。不推論私人 Memory／正式持久化資料已驗收。 |
| WebEngine | 前三次 loadFinished=true；後三次 false 對應 source 中三個被拒 navigation，沒有 renderer exit49 事件。 |
| Qt | 兩份原始 FormalPreflight 精確 Python／7 modules／3 packages／6 DLL origins／pre-app scheme PASS；本輪新 FormalPreflight 亦 PREREQUISITES_PASS，沒有 QApplication、override 或正式入口。 |
| Package ownership | `PackageOwnership.json`：SINGLE_OWNER_PASS，64 shared Essentials files、1,253 Addons RECORD files，來源 wheel/derived hashes 一致；cryptography 46.0.3 位於正式 env。只呼叫 read-only installed_ownership，沒有 pip/install/rollback。 |

原始 first NativeResult SHA `80f87913384f34c9f471471ac9a79251c9424c8ac89de00f9c50793b1548dd9a`，restarted SHA `2917ca17bb5df887f329d16b7ec0a4c11ff6268c1c1ec8cbd3d7e26279c849cd`；兩份 SecurityEvidence SHA 均為 `d3a99c19e711c086341393cda3d1db053e6791e29402e3b5306ce534de043360`。其餘檔案 SHA 見機器證據。

新原生收據同時記下 `legacyPredicates.popup=false`，原因為首次 window.open 回傳非 null，但 drain 後無可用 handle、無新 page/window、Qt 拒絕與 discard 有實證。這證明舊 null-return 斷言在本次情境會誤判。更早的合併 FAIL 沒有四軸，因此不回填其唯一歷史根因、不改寫舊 FAIL。

## Source pin 與回歸

唯一候選 fingerprint `dc7ad8b776312ab6c40102591d2bbe822707af44c776032cb041ae2bbfa2402e`，manifest SHA `c2920dff0455acfdbee2fcb9ae0a0f42cd1aa6c9d6b1690d54da5e377b765bed`。公鑰與 signature 的精確值在 `w6_release_candidate.py::PIN_VALUES`、上述 ReleaseCandidate.json 及未套用 patch；正式程式不 import devtool，不存在第二條 UI 啟用路徑。

兩個使用者 child **沒有 OwnerBuild.json**。實際比較來源是兩份 NativeResult.bundle、canonical `assets/qt-owner/<fingerprint>/owner-build.json`，以及既存 staging `.runtime/w6-security-20261011T133551558915Z/OwnerBuild.json`。由精確值建真正 OwnerBundlePin，呼叫真正 VerifiedOwnerBundle.load；另外核對 builder lineage、六份原版 Git renderer bytes、工具鏈、manifest、CSP 與四個凍結資產。

Dry-run 在記憶體編譯 proposed source，將唯一 RELEASE_PIN assignment 移到 OwnerBundlePin 類別定義之後，呼叫同一 prepare_owner_presentation，在無 QApplication 時註冊 scheme。正式 module 的 RELEASE_PIN 與檔案 bytes 不變。Wrong manifest／signature／public key、複製 bundle 的 asset／manifest／lineage／額外檔案均 fail-closed；asset map 不可修改。既有 w6 suite 另驗 app 建立後註冊 scheme 必須失敗。

`validate_candidate.py --profile release-candidate` 固定包含既有 27 suites 加 release candidate suite，涵蓋真 existing-window source 分支與 security。拒絕空／未知 suite，以及用 --only 削減 release profile；零 Python tests 不能 PASS。constructor regression 使用真 KuroQtLauncherWindow、隔離 Controller/config，僅替换 WebEngine surface，明確屬 source wiring，並非原生 render 驗收。

中途 reviewer 指出的錯誤 child OwnerBuild 路徑已移除；錯誤 evaluator.evaluate 名稱已改 canonical evaluate_security，記憶體舊版的 AttributeError fail-before／現版 pass-after 保存在 `EvaluatorFailBeforePassAfter.json`，另有 canonical evaluator regression。第二輪新增精確 source/package/module/DLL keys/origins 與 navigation 原始計數負例；真原始 receipts 未變。

最終為 **28 suites／331 tests／typecheck PASS**，清單與不重複計數結果見 `ValidationSummary.json`；source compile、diff、originals、G7 35 absent、HEAD/index/WIP/receipts 保全見 `Preservation.json`。獨立 reviewer 裁決見 [W6EReviewerRound2.md](W6EReviewerRound2.md)。

Patch 檢查另發現 Windows text-mode 將 LF 轉 CRLF，早期 candidate-initial／candidate-final patch 因而不能套用；保留歷史輸出，不作正式提案。已改成 exact LF bytes，新增完整 dry-run＋`git apply --check` regression。唯一有效提案是 candidate-reviewed；僅檢查可套用性，未套用。

## 可重現命令與正式採用邊界

以下命令須使用全新 output。只執行 source／isolated validation；不開正式 Kuro：

```powershell
.\envs\kuro-llm310\python.exe -I -B .\devtools\original-git-web-host-20261010\w6_release_candidate.py --output .\devtools\original-git-web-host-20261010\.runtime\<fresh-review>
.\envs\kuro-llm310\python.exe -I -B .\devtools\original-git-web-host-20261010\validate_candidate.py --profile release-candidate --output .\devtools\original-git-web-host-20261010\.runtime\<fresh-regression>
```

正式 pin 現值 **None**，原始 receipt `humanApproval=UNVERIFIED`／`productionAdoption=false` 未變。唯一待人審變更是 [ReleasePin.proposed.patch](.runtime/w6e-review-20261011T140713669061Z/candidate-reviewed/ReleasePin.proposed.patch)，SHA `44323569e3266141a2ce7cae2a567a8f5a43fd89913bae02569ea2ac00eea721`；候選 UTF-8 LF source SHA `bf91caa1f6945b69fd366e05fc73199281d977324e17b14b1c589e12388261eb`。目前正式 preimage SHA `ed65d342f7bdd6fdf7ecdd08f021b8e6797e5c45f873a374eccd0ae8b1d9de41`。

現有 VBS 已是 pythonw → launcher_qt → 同一 KuroQtLauncherWindow，**不需要改 VBS**。flip pin 後的下一次正式 cold start 會讀私人 config/env/logs、可能依 startup profile 啟服務，並開始既有 status/reconcile timers。second launch 僅喚回已存在視窗，不能證明採用新 source；`_ensure_desktop_entry` 只是 tray 不可用時 reveal，並不修改捷徑。

先取得獨立人工視覺驗收與明確正式採用授權，再核 preimages/postimages、重新 package/source/pin preflight、正常關閉已辨識的 owner、以原入口受控冷啟動及驗真 production display。這些步驟本輪均未執行。採用後的 source hash 會因 pin assignment 改變，必須另記 source identity；不能聲稱目前 13-source 原生 receipt 已涵蓋未來改動。無 env/readiness override、雙 Controller／WS、fallback 或第二 UI。

退役與 rollback 見 [W6WidgetsRetirement.md](W6WidgetsRetirement.md)，W7 人工清單見 [W7ReleaseReadiness.md](W7ReleaseReadiness.md)。

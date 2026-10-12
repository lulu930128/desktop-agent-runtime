# W6.F 正式 source cutover checkpoint

2026-10-12，續接取消的 job `504c19e5-7390-4e83-8750-234dad76283a`。本輪只完成保全、隔離驗證、回滾演練與文件；沒有再改產品 source 或既有測試。

**正式 source pin：ACTIVE；SOURCE_CUTOVER_PASS；本輪 native：BLOCKED；PRODUCTION_RUNTIME_UNVERIFIED；封版：NOT ACCEPTED。**

使用者已授權 source cutover，並確認 App 是 Qt 原生桌面 App 內嵌 QWebEngineView 顯示 Git 原始 Work Companion UI。這不構成私人 profile、服務 cold start、provider、裝置或正式 runtime 的驗收。沒有獨立瀏覽器／Web server production path。

## 精確 source 狀態

| 對象 | 本輪確認 |
| --- | --- |
| Repo | `C:\project\desktop-agent-runtime`，`main`，HEAD `af83df273602be3a616d6567855ea71d61a9ace7`。 |
| 正式 release source | `kuro_launcher/qt_web_release.py` 完整 bytes SHA `bf91caa1f6945b69fd366e05fc73199281d977324e17b14b1c589e12388261eb`，與 reviewed ADOPTED_SHA 完全相等。 |
| 切換前 release source | 精確 preimage SHA `ed65d342f7bdd6fdf7ecdd08f021b8e6797e5c45f873a374eccd0ae8b1d9de41`。 |
| 唯一 bundle fingerprint | `dc7ad8b776312ab6c40102591d2bbe822707af44c776032cb041ae2bbfa2402e`，位於 `assets/qt-owner/<fingerprint>`。 |
| Manifest SHA | `c2920dff0455acfdbee2fcb9ae0a0f42cd1aa6c9d6b1690d54da5e377b765bed`。四資產、lineage、Ed25519、immutable asset map 與 CSP 均經現有 verifier 重驗。 |
| Reviewed patch SHA | `44323569e3266141a2ce7cae2a567a8f5a43fd89913bae02569ea2ac00eea721`；reverse `git apply --check` exit 0，沒有在 checkout 執行 reverse apply。 |
| Native source identity | W6E 原始 13-source 集合中只有 release source 是授權 pin delta，其餘 12 個 SHA 未漂移。本輪兩份 BLOCKED native receipt 都記錄採用後 13 個 SHA，且 sourceUnchangedDuringRun=true。 |

完整 13-source SHA、bundle files SHA、入口行號、七檔 pre/post SHA 見 [Integrity.json](.runtime/w6f-resume-20261012/Integrity.json)。SHA 保全 bytes，不認證觀測者；builder signature 不是外部 publisher 信任證明。

正式鏈路是 `launcher_qt.main → prepare_owner_presentation(BASE_DIR) → VerifiedOwnerBundle.load + scheme registration → QApplication → KuroQtLauncherWindow(cfg, web_bundle=verified) → _init_web_presentation → return`。驗證失敗在 QApplication／window 建立前 return 2，不偷偷 fallback。入口仍會先讀 config/env 並設定 log，因此不得直接執行 main 冒充無私態測試。

同一 window constructor 建立原有 Controller 與 qt-primary chat client；Web 分支只接既有 tray／QtScheduleDelivery、status／reconcile lifecycle。它在舊 builder 之前 return，不建立 WorkCompanionView、Today／Schedule／Settings widgets、QSettings presentation state 或舊 widget observers。source/constructor regression 證明接線；本輪沒有取得成功的正式 renderer live proof。

舊 Widgets 的 `qt_app.py` builder tail、`qt_work_companion_view.py`、`qt_work_companion_theme.py`、`qt_core_pages.py` 全保留且 bytes 未變。`RELEASE_PIN=None` 僅為顯式隔離 rollback fixture／歷史 preimage；正式 pin 維持 ACTIVE，未建立並行 production 畫面。

## 驗證與證據

全部新證據位於 [.runtime/w6f-resume-20261012](.runtime/w6f-resume-20261012/)。

| 驗證 | 結果與限制 |
| --- | --- |
| 前次 release regression | 28/28 suites，334 Python/Node tests，typecheck exit 0；逐份官方 log 重新計數。 |
| 本輪 fresh release regression | 28/28 suites，334 tests，typecheck exit 0；[Results.json](.runtime/w6f-resume-20261012/release-regression/Results.json)、[runner exit](.runtime/w6f-resume-20261012/ReleaseRunnerExit.json)。 |
| 額外正式入口測試 | 8 tests／exit 0：active pin、invalid pin fail-closed、None rollback fixture、單次／再次啟動接線。main 的私態與 window IO 均被隔離／替換，不是正式 main live run。 |
| History transport 重驗 | 3 輪，每輪 2 tests／exit 0；屬舊 Widgets rollback fixture，不能代替 Web UI 驗收。數量不與 334 重複累加成 unique coverage。 |
| Log 計數 | [LogCounts.json](.runtime/w6f-resume-20261012/LogCounts.json) 為 LOG_COUNTS_VERIFIED。Python `Ran (\d+) tests?`；Node 支援 `ℹ`／`#`，核 tests=N、pass=N、fail=0。缺失／null test count 拒絕；typecheck 明確為非 test check。 |
| Formal preflight | exit 0／PREREQUISITES_PASS，正式 Python、7 modules／6 DLL origin、scheme pre-QApplication；沒有建立 QApplication。 |
| Source candidate | exit 0／SOURCE_PIN_ACTIVE_VALIDATION_PASS，8 tamper/immutability 負例拒絕，productionAdoption=false。見 [ReleaseCandidate.json](.runtime/w6f-resume-20261012/source-candidate/ReleaseCandidate.json)。 |
| Package ownership | [PackageOwnership.json](.runtime/w6f-resume-20261012/PackageOwnership.json)：唯讀 installed_ownership 重驗 SINGLE_OWNER_PASS，64 shared Essentials files、1,253 Addons RECORD entries。正式成功來源為 `.runtime/w6-user-install-20261011T0956528942669Z`；原 PackageGate PREREQUISITES_PASS、verify-process exit 0。沒有 pip/install。 |
| 回滾 | [RollbackRehearsal.json](.runtime/w6f-resume-20261012/RollbackRehearsal.json)：七檔只在 disposable mirror 做 adopted→pre-cutover→adopted 精確 bytes roundtrip；source compile 不執行，真 checkout 未寫。 |
| 本輪 native | [RelayResult.json](.runtime/w6f-resume-20261012/native/RelayResult.json)：parent PID 47832／restarted PID 53164，actualExit=reportedExit=2／2，renderer exit49，Native JavaScript callback timeout，security 四軸 NOT_REACHED，BLOCKED。shell invocation exit 1，不能冒充 child exit。停止重試，沒有 sandbox／GPU workaround。 |

Fresh runner 沿用既有固定 release-candidate profile，只在記憶體把兩份舊 Widgets 截圖測試的 output-only `ROOT` global 導向新 evidence 目錄；測試 source、assertions、fixtures 與 suite 集合未改。詳見 [run_validation.py](.runtime/w6f-resume-20261012/run_validation.py) 及 [ValidationMethod.json](.runtime/w6f-resume-20261012/ValidationMethod.json)。source regression 中的 offscreen Qt 不是 Windows native WebEngine acceptance。

保留 [10/11 W6E 原始證據](.runtime/w6-security-user-20261011T1357535580236Z/RelayResult.json)：正常使用者 Windows 雙輪各 74/74、actual exit 0、四 security axes PASS。它是切 pin 前的獨立歷史 synthetic native 證據，**不自動轉成切 pin 後 production live acceptance**。歷史 W1 strict pixel geometry FAIL 與早期 W6 FAIL 不改寫。

## 取消後狀態與保全

本輪開始為 491 dirty paths（65 modified／34 deleted／392 untracked）。[Before.json](.runtime/w6f-resume-20261012/Before.json) 保存 1,342 個既有 Git-visible 路徑 hashes、HEAD/index、七檔 adopted preimages、Widgets 與 screenshot 保全。最終以 [Integrity.json](.runtime/w6f-resume-20261012/Integrity.json) 確認本輪既有 paths 無 drift、舊 W6.F evidence 無 drift、W6E raw receipts 無 drift，G7 35 路徑仍 absent。HEAD/index 未改，沒有 commit/push。

前次 baseline→本輪開始的差異為七檔授權 allowlist，加一張 `devtools/git-work-companion-parity-20261010/R4-Chat-offscreen.png`。截圖 SHA 從 `294a771c18c50b4d55bc4e1c7136752e855c1e91f032b23519b0d7b13f155912` 變為 `2a995cae0ec316247f59cd4287e93a6f9a130f1728900a697102785708a3b954`；此差異已在本輪前存在，不推論其他程序的寫入身分。本輪保存後者，不覆寫回舊圖。七檔變更摘要見 [PriorCutover.diff](.runtime/w6f-resume-20261012/PriorCutover.diff)。

前次 `convergence-python.log` 是 UTF-16LE BOM，完整尾端為 43 suites／530 tests、`ok=false`；`test_r4_history_transport.py` exit 1，line 118 等待建立 history timeout。沒有 aggregate OS exit 證據，不宣稱全 convergence PASS。新 release 與三次限定重驗通過，歷史 timeout 根因未證實，作為舊 Widgets fixture 的殘餘穩定性風險保留。log SHA 穩定，沒有重跑全 convergence。

[ProcessBefore.json](.runtime/w6f-resume-20261012/ProcessBefore.json)／[ProcessAfter.json](.runtime/w6f-resume-20261012/ProcessAfter.json)：未見本 repo Python／WebEngine 殘留；本輪兩個 native PID 已退出。受關注的正式 ports 中僅 Voice 18890／PID 2732 有 listener，前後一致，未連線或控制。CIM 拒絕存取，command line／parent lineage 未取得；這不是全機無孤兒程序的完整證明。

初次 package 查錯 `.runtime/w6-addon-install-20261011T0831433534326Z`，缺 WheelReceipt，exit 1；不列為 package PASS。初版 log helper 只識別 Node `#`，false-negative exit 1；只修隔離 helper 後重算 exit 0，未重跑正式測試。[Exceptions.json](.runtime/w6f-resume-20261012/Exceptions.json) 留存兩次證據處理失敗與正確後續結果。

## 註解及舊文件的歷史語意

`launcher_qt.py` 的「Source pin stays None」、`qt_web_release.py` header 與「safe Widgets default」docstring 是舊 gate 說明，**不是目前現值**。依使用者 source integrity 優先指示，本輪不改任何字元，避免破壞 ADOPTED_SHA／其他 12-source native provenance。等新的 native baseline／正式驗收後另案收斂。

10/11 的 W6E／W7 文件所寫 pin=None、patch 未套用屬當日狀態；本 checkpoint 才描述 10/12 source cutover 現況。舊 `.runtime/w6f-adoption-20261012/Prompt.md`／`Plan.md` 含問號編碼損失，原件保留；本文件補足本輪範圍與交接，不覆蓋歷史。

## 精確回滾邊界

七檔清單與每檔 pre/post SHA 均在 Integrity／RollbackRehearsal；pre-cutover bytes 來自 `.runtime/w6f-adoption-20261012/preimages/`，adopted bytes 備份在 `.runtime/w6f-resume-20261012/preimages/`。

1. 回滾前先核對所有目標 current SHA 必須等於 adoptedSha256，所有 backup 必須等於 preCutoverSha256；任一不符就停止，不覆寫後續 WIP。
2. 本輪只演練隔離 mirror。正式回滾需另行明確授權、確認正式 owner 已正常關閉，不能邊運行邊換 source；不殺 shared services。
3. 若需完整 source checkpoint，精確還原七檔，不能用 HEAD/reset/checkout 代替 dirty preimages；不得擴及 VBS、Widgets 其他 source、原 renderer、private state、DB 或 packages。
4. `None` preimage 會改變下次入口選擇，因此不得在本輪套回正式 checkout 或啟動它；它不是錯誤時的自動 fallback，也不允許並行 Widgets production UI。
5. 復原後重新核 bytes、pin/bundle 與適用測試，另做授權後 runtime acceptance。現有 source-only reverse patch check 不證明正式 runtime 回滾成功。

## 外部人工 cold-start gate 與未驗收能力

下列步驟供正常使用者 Windows session 後續執行，**本輪未執行**：

1. 先取得明確的正式 profile／服務啟動授權，列明私人 env/config/log/history/Memory、Core／LLM／Pet 等實際範圍；OMI／Mail／Study、Voice 18890 與真 provider／付費操作不因本 gate 自動獲准。
2. 重驗本 checkpoint 的 source／bundle／package SHA，核當次程序、port owner 及工作目錄。若有舊 owner，用既有正常 Quit 關閉；只喚回舊程序不能證明載入新 source。
3. 從 repo 既有 `桌寵啟動器.vbs` 啟動；VBS／shortcut 不改。記錄新 PID、executable、source/bundle/DLL identity、唯一 native KuroQtLauncherWindow／QWebEngineView 與同一 Controller／qt-primary WS／tray／notifier。無法取得者仍 UNVERIFIED。
4. 驗 Chat／Today／Schedule／History／Settings／Memory 的正常、loading、empty、offline、stale、partial、error／cancel；只在已批准資料範圍操作。驗 second launch 喚回同一視窗、X/tray、Quit/restart、cleanup、無第二 backend／WS／manager。
5. 實體 OS 中文 IME、候選選取、Enter、鍵盤焦點、DPI／雙螢幕、OS toast、Live2D／camera／mic／screen／Voice 均須各自實測記錄；注入 IME、synthetic toast／device 或 PNG 存在不能替代。
6. 保存當次觀測與使用者判定後再決定具體 acceptance 範圍；本文件不預先給 PASS。

一般 tools `confirmation_available=false` 仍 blocked，Mail body／refresh canonical contract 尚未提供；展示層不能提升權限。正式私態、LLM provider、真裝置／Voice、本輪成功 WebEngine rendering 皆未驗收。完整 clean-machine package distribution 也未完成，requirements-qt 仍非完整 Addons／cryptography 安裝方案。

## 獨立 reviewer 最小重查

先唯讀核上述 JSON、source 與 logs。以下只重算檔案證據，不開 GUI／服務，不寫 production；輸出到 stdout：

```powershell
Set-Location 'C:\project\desktop-agent-runtime'
.\envs\kuro-llm310\python.exe -I -B .\devtools\original-git-web-host-20261010\.runtime\w6f-resume-20261012\recount_logs.py
.\envs\kuro-llm310\python.exe -I -B .\devtools\original-git-web-host-20261010\.runtime\w6f-resume-20261012\audit_checkpoint.py
```

本輪只新增本 checkpoint 與 task-local ignored evidence/helpers；產品 source／既有 tests 無新 edits。沒有 Widgets 實體刪除、commit/push、VBS／捷徑／ACL／registry 修改、production service 操作、private DB/history/Memory 操作或 sandbox weakening。

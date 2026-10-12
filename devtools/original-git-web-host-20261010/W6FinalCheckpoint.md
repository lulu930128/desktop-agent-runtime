# W6.D/E/F 檢查點：接線完成，原生 Web gate 阻擋

## 2026-10-11 安全斷言增量：逐軸 evidence，原生仍 BLOCKED

最新正常使用者 `w6-status-user-20261011T1323557749487Z` 的 parent/restart 均 67 PASS、僅合併 `scheme-network-storage-denied` FAIL；兩輪 loadFinished=true、JS errors=[]、單一 WS。歷史收據缺四軸 truth data，不能指出唯一失敗子項。

本輪已保留全部 66 個 required checks，新增四個安全 gates、host denial counters 與 `SecurityEvidence.json`；network/asset/popup/storage 依 settled、實際 hit/creation/read/write/reload 證據判定，合併失敗不再跳過 navigation/listener gate。Reviewer 的 reload error 收集疑慮已補明確初始化、四份樣本 completeness 與敏感內容過濾回歸。完整舊 26 組命令加 targeted security suite，共 27 組、323 tests 及 typecheck PASS。

末次 `.runtime/w6-security-20261011T133551558915Z/native-final/` 真 parent/restart 仍 renderer exit49 / loadFinished=false / exit2，restartObserved=true；四軸 NOT_REACHED，**原生 BLOCKED，未宣稱漏洞修復或完整 PASS**。細節、正常 PowerShell 單條命令、rollback/preimages 見 [W6SecurityBoundary.md](W6SecurityBoundary.md)。main HEAD/index、原 481 dirty WIP、六個 renderer、G7 35 absent、RELEASE_PIN=None、Widgets/VBS 不變；W7 未開始、無 commit/push。

## 2026-10-11 晚間增量：第二次 getState 的定點修正

以下歷史章節與 receipts 保留。最新正常 Windows 使用者 relay 是
`.runtime/w6-native-user-20261011T1258395703761Z/`：兩輪均 `loadFinished=true`、各 49 checks PASS、單一 WS、source 未變；兩輪都在 synthetic Pet 後第二次 `getState` 超時。這已取代「只能觀測 renderer exit49」作為使用者桌面的最新事實，但不是完整 native PASS。

本次新 evidence 根為 `.runtime/w6-status-20261011T130913527233Z/`。source/Qt queue 診斷證明修前第二次 status 在 234 ms 完成、Pet lock 已釋放、waiters/pending 都為零；原版 `renderChrome` 在 Pet ready 時讀取缺失的 `launcher.voice.state`，而 OwnerTransport 在 listener 拋錯前已移除 timeout，造成 Promise 懸空。已將 launcher capability 接回既有 lifecycle diagnostics，並以 `finally` 完成已驗證的 reply，原 listener 例外仍可觀測。沒有調整 timeout、retry、sandbox 或 owner 數量。

完整根因、fail-before/pass-after、驗證數量、native 缺項、安全接力與本輪 rollback 見 [W6StatusTimeout.md](W6StatusTimeout.md)。本次 Codex 的真 native pair 仍是 exit49／`loadFinished=false`、actualExit=2、`restartObserved=true`，因此 **修後 native BLOCKED**。既有正常 Windows 的 49+49 PASS 不改寫，也不沿用為修後 PASS。`RELEASE_PIN=None`；Widgets/VBS 未動；W7、正式採用、commit/push 均未開始。

---

以下為先前 W6.D/E/F 歷史檢查點。

2026-10-11。本輪授權已涵蓋 D/E/F 的必要實作、隔離測試及有證據後的受控切換。本檔取代舊文件的「D–F 尚未開始」狀態；歷史安裝、W1 strict FAIL 與 receipts 不覆寫。

**正式入口維持安全 Widgets。** `qt_web_release.RELEASE_PIN=None`，VBS 未改、Widgets 未刪除。Web 已實作在真正的既有 `KuroQtLauncherWindow` 內，但正式 Python 的 WebEngine renderer exit49、`loadFinished=false`。因此 **W6 整體未通過、W6.F 未執行、W7 未開始、不可封版**。visible/exposed 不代表 Web UI 可用，也沒有使用者 manual approval。

最終整合為 **26 組、306 tests 全通過及 typecheck PASS**；本輪 17 個既有檔案局部修改、8 個新增檔案，無 allowlist 外變更。index／branch／HEAD 不變，六個 original renderer 與 Git bytes 相同、G7 35/35 保持 absent，119 preimages 全數重驗。`git diff --check` 與本輪 delta 的 reverse `--check` 均 exit0；沒有執行回滾。

## 當次證據

證據根：[w6-def-20261011T101655070777Z](.runtime/w6-def-20261011T101655070777Z/)。失敗 receipts 同樣保留。

| 層次 | 證據與結論 |
| --- | --- |
| 基線／WIP | `main`，HEAD `af83df273602be3a616d6567855ea71d61a9ace7`；起始 471 dirty paths、1,322 Git-visible paths。`Before.json`／`Before.diff`／`Index.diff`／`Status.bin`，119 個 exact preimages。 |
| 已安裝 Addons | `PackageReverification.json` 與末次 `PackageReverification-after.json` 均為 `SINGLE_OWNER_PASS`、64 shared Essentials files、1,253 Addons RECORD files；沿用使用者正式安裝 receipt。本輪無 pip、重裝、package/env 修改。 |
| 正式 runtime | `FormalPreflight.json`：Python 3.10.12、Essentials/Addons/shiboken/Qt 6.11.1；7 imports、6 個 loaded Qt DLL 均來自正式 env，scheme pre-QApplication PASS。 |
| Bundle | `OwnerBuildFinal.json`：fingerprint `e5524fb435718b4eef0f23609a8c6d57cbe28693d420e0e09446e8138a277e35`，manifest SHA `c0a185e92791dd212dea18be076dfd5e166691c15557201811639718dc981452`；Ed25519 pin、四資產驗證。 |
| Source／隔離 IO | `validation-final/Results.json`：26 組、304 tests、0 failures，含 typecheck。末次 WS token／fixture 修正由 `validation-reviewed/Results.json` 覆蓋相關 suites；整合結果见 `ValidationSummary.json`，不重複計數舊 tests。 |
| 真 native | `native-reviewed/RelayResult.json`：parent PID53664、restart PID53764，OS／reported exit 均2。兩份 NativeResult 各12個 source hashes 對上末次 source，`sourceUnchangedDuringRun=true`。真 QApplication／KuroQtLauncherWindow／QWebEngineView 依序執行，`restartObserved=true`。 |
| Native 限制 | renderer exit49、JS callback timeout、WS connections=0，總 verdict **BLOCKED**。`coverage.missing` 明列未到達的 Web 互動；blank `last-window.png` 不是視覺驗收。`native-final`／`native-attempt-01/02` 為較早真實失敗 receipts。 |
| 保全 | `Preservation.json`／`W6Delta.patch`／`Status-after.bin`／`postimages/`：本輪 allowlist、index、六個 original renderer、G7 35 absent、既有檔案與 preimages。 |
| Reviewer | `W6ReviewerRound2.md` 保存獨立 read-only 工程複查、修復及末次結論；不等於實機人審。 |

早期 `validation-initial`／`validation-owner-io` 失敗已有後續 regression；native 失敗仍保留，未被 source PASS 蓋過。

## 接線與 owner

- `launcher_qt.py` 在唯一 QApplication 前準備本地 scheme／source pin。預設 None 不載 Addons/assets。沒有 env 或 readiness receipt 開關；舊 `create_candidate` 仍限 fixture。
- `KuroQtLauncherWindow(cfg, web_bundle=verified)` 在現有 central widget 建 WebHost，於舊 `_build_ui`／`_wire_signals`／QSettings／Today／Schedule／Memory／Profile 初始化之前返回。Web 分支沒有隱藏 Widget presentation 或舊 render/read/poll observers；安全 Widgets 分支仍完整保留。
- [既有 24-method 清單](W1W5ClosureMethods-20261011.md) 的 21 requests＋3 subscriptions 經唯一 Wire → RequestBroker → QtOwnerAdapter → 原 controller／QtRuntimeChatClient／Core。沒有第二 WS、Controller、Core、Tray 或 notifier。
- status 與 Today 各自合併 in-flight reads，原 renderer 負責初始化。lifecycle status 保留 Chat auto-connect，Live2D／diagnostics 失敗各自 truthful unavailable；task_finished／restart／Tray／QtScheduleDelivery 繼續由原 owner 負責。本機 logs 進既有 stdout tee，不傳到 HTML。
- Request lifetime 在 timeout／close 後阻止晚到 wait/cache/Chat submit；唯一 QtRuntimeChatClient 用純 Python lock 原子提供 identity＋Event，在 transport 改動身分前撤銷舊 token。worker 只讀 captured token，不讀 Qt QObject。已開始的 mutation 結果未知仍保留 fence、不重送。
- History 使用稳定 submitted request ID，避免快回應清掉 pending 後失去 correlation；queued 舊 connecting/offline 不得取消已連線 request。Native modal nested loop 期間 Quit 不再 dispatch。Core 時間、freshness／partial／missing／unknown、memory digest 與 confirmation 邊界保留。
- Bundle 使用同一份已簽章驗證的 manifest bytes 解析，逐 asset 驗 hash 後凍結。off-record profile、本地 allowlist、CSP、navigation／permission／download／filesystem denial 保留。已裝 `cryptography 46.0.3` 負責 Ed25519；private signing key 不保存，未來正式公鑰必須來自 source pin，不能稱作外部發行商簽章。

`OwnerInventory-after.json` 的 63 connect／41 Widget-reachable 是整份雙分支檔案的保守 lexical graph，包含保留的 Widgets 與 guarded shared methods，不能當 Web runtime observer 數量。Web 互斥建構與唯一 owner 分別有 source 和 native count 證據；本輪沒有刪除舊 source。

## 原生與隔離驗證範圍

真 native 已觀測 windows platform、visible/exposed、唯一 owner、X→tray、正式 activation timer 的 second launch、reveal 同視窗、byte-identical relaunch helper 的隔離 restart、父程序已退出、late callbacks 靜默、冪等 cleanup／Quit。renderer 失敗後仍跑生命週期檢查，不能以此補足 Web 互動 gate。

Harness 包含 Chat／History／Profile effective／Memory native confirm／Today／Schedule mutation／通知去重／capture fixture／Live2D 缺席／identity／unknown／DOM focus／IME 注入／scheme security。`REQUIRED_CHECKS` 少一項不能總 PASS。Network probe 先由 Python 取得隔離 loopback HTTP200，再要求 renderer fetch 拒絕且 server hit count 不增加。通知 display、capture 是 synthetic，OS toast／真裝置與實體 IME 仍未驗。

真 Controller／Qt client／Core HTTP／Memory 的隔離 source tests 已驗通過 Profile effective、History、Chat、capture 合成送出、通知 dedup 及 Core read-no-write。這些不取代原生 DOM bridge 證據。fixture 分開建立/start以處理 partial failure；native child 直到退出都保留隔離 root／network，unit teardown 先 drain owned worker 才恢復環境。

## 正常桌面接力命令

下列命令開啟標明 **SYNTHETIC** 的隔離真視窗，依序 restart 一次並退出。只使用正式 Python，不載 production main/config/private state、不安裝或切正式入口；不加 Qt/GPU/sandbox override，不需 admin：

```powershell
Set-Location 'C:\project\desktop-agent-runtime'
$w6Stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffffffZ')
$w6Out = "C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010\.runtime\w6-native-user-$w6Stamp"
& '.\envs\kuro-llm310\python.exe' -I -B '.\devtools\original-git-web-host-20261010\run_w6_existing_window.py' --output $w6Out
```

`RelayResult.json` 必須是 `AUTOMATED_NATIVE_PAIR_PASS`，兩個 NativeResult 的 source/bundle hashes 須對上待切換 source，才可進正式切換審查。現有 BLOCKED 不提供啟用授權。若仍 exit49，保存 console／termination／screenshot，在正常使用者桌面診斷；不重跑 Addons installer，不以提權、kill、ACL、sandbox override 補過。

## 安全切換與 rollback

本輪安全狀態是 `RELEASE_PIN=None`，正式 VBS／Widgets 不須切回。未來 native gate通過後，reviewer重核 package／source／bundle；在 `OwnerBundlePin` 定義後建立當次正式 source pin，再跑 targeted checks。正常關閉已核實的正式 Launcher 後才用原 VBS 啟動。受控採用與 Widget 精準退役須各自保存新 preimages／receipts；此 source pin 變更尚未執行，也沒有可繞過 gate 的 CLI/env 開關。

本輪 delta 相對 exact preimages，而不是 HEAD。以下只檢查回滾是否仍可套用：

```powershell
$w6Run = 'C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010\.runtime\w6-def-20261011T101655070777Z'
git apply --reverse --check -- "$w6Run\W6Delta.patch"
```

檢查失敗或 current hash 不符 Preservation 時停止，保護後續 WIP。實際回滾依 allowlist 和 pre/postimages 還原本輪 bytes；不 reset／clean／stash、不覆寫私人 state。本輪不執行回滾。

## W7／封版仍缺

W6 未過，W7 掃描與 release-readiness **執行未開始**。以下只列待驗清單：

- 正常桌面原始 Web 主要頁面、History／Memory review／Settings／Today／Schedule、confirm、keyboard／focus／中文實體 IME、DPI／多螢幕／尺寸。W1 已接受視覺差異，但歷史 strict FAIL 不改寫。
- 正式既有 owner 冷啟動／Chat auto-connect／X／tray／Quit／second launch／restart，當次 source／DLL／bundle 身分與單 owner 證據。
- OS toast、真 Pet／Live2D／camera／mic／screen／Voice 人工測試；外部 :18890 owner 未被操作。
- Tool confirm 仍 `confirmation_available=false`；Mail body／refresh canonical contract 仍缺，不能以按鈕或 fixture 宣称可用。
- `cryptography` 正式依賴／封裝 provenance、Widgets 精準刪除 allowlist、rollback、工程 reviewer 最終驗收。
- 私人 Chat／Memory／真郵件／provider 或 LLM quota／OMI 下單／production DB 不屬本輪自測，使用者 manual approval 仍未取得。

沒有 commit／push、正式採用、Widgets 刪除或封版宣告。

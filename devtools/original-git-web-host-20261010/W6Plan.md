# W6 執行計畫：W6.B/C 通過，正式 UI 尚未接線

## 2026-10-11 17:38 下載後：W6.B/C ownership 修復

本計畫已執行至 W6.B/C PASS：`.runtime/w6-user-install-20261011T0956528942669Z/PackageGate.json`。完整結果與保全驗證見 [W6Checkpoint](W6Checkpoint.md) 最新段落；不用重裝，停在本次授權範圍。

本次授權僅限 W6.B/C 套件修復與 no-app preflight；不沿用下方歷史 W6.A–F 的較廣操作範圍。不得啟正式 GUI、改 VBS／Qt UI owner、刪 Widgets、碰 private backend／其他既有 env、提權／ACL／重啟、W7、commit/push。

1. 保全 470 dirty entries／1,321 Git-visible paths、index、原六 renderer、G7 35 absent、舊 receipts 與正式 Qt bytes。查驗已下載官方 wheel 的原 SHA、內部 RECORD、全體 installed distribution ownership 與逐檔 bytes。
2. 同 bytes 僅是必要條件。只接受 exact Essentials 6.11.1 的單一、canonical RECORD owner，排除未知／多 owner／內容不同／缺檔／版本不同／case collision／symlink／reparse redirect。不修改 Essentials RECORD。
3. 原 wheel 保留不動；在新 evidence 建立 build tag `1w6owned` 的本機衍生 wheel，移除已證 shared payload **及其 RECORD 條目**。其餘官方 payload 逐檔相同，新增 `W6_ORIGIN.json` 保存原 SHA 與排除清冊；衍生 wheel 有自己的 SHA，不能宣稱其 archive SHA 是官方 SHA。
4. 安裝前重驗 backup、全體 ownership manifests 與衍生內容，再做 create/read/delete 權限探針。只有既有 idle relay 允許後才以 isolated/no-deps/no-index/no-compile pip 安裝衍生 wheel。verify 與 rollback 均要求 exact installed RECORD、payload hash、單一 owner、shared bytes 不變；部分／失敗安裝仍停止人工審查。
5. 正負回歸含原 receipt collision、原 gate overlap 重現、真實 disposable pip install/uninstall、隱含 bytecode 刪除、寫入拒絕。正式 `-Wheel` 離線驗證後執行 pip check、Web imports、DLL origins、scheme pre-app；結果見最新 checkpoint，不把 source test 當正式 PASS。

RECORD 與 uninstall 依 [PyPA installed-project 規格](https://packaging.python.org/en/latest/specifications/recording-installed-packages/)；本機 pip 25.3 的 `req_uninstall.py` 亦逐條 RECORD 加上 `.py` 隱含 bytecode 計算移除路徑。因此不採先裝原 wheel 再修 live RECORD 的中斷風險流程。Essentials 作為依賴被移除仍會使 Addons 失效；此流程保證 Addons uninstall 不會移除 Essentials 檔案，不是全域 pip 共用檔案 reference counting。未經本 gate 的 raw-wheel reinstall/upgrade 不在保證範圍。

現有 numpy 與 Essentials 共三個重複 optional `.pyc` RECORD 路徑另存清冊，原 metadata 不修改；所有 claims 保留，任何 wheel/隱含 bytecode overlap 仍須通過單一 owner 檢查，不因去重而放行。非 `.pyc` 重複條目拒絕。

## 最新續作：使用者 Quit 後，2026-10-11 09:05 UTC 起

W6.A 新程序盤點通過，套件 baseline/Qt byte backup 已完成。Codex 一般及 require_escalated 的官方 PyPI 連線仍 WinError10013（NETWORK_DENIED），不代表 wheel 不存在；停止網路重試。可讀 conda caches 與 task wheelhouse 未找到指定 wheel，使用者 pip cache 唯讀一般/提權皆 Access denied，不宣稱已查證其內容不存在。

新授權範圍完成一個正常使用者 [安裝 relay](Invoke-W6AddonsRelay.ps1)：新 evidence、idle → package backup → 官方 metadata/hash/tag → wheel → 再 idle → formal-only/no-deps 安裝 → preflight/pip check；非零即停且保留證據，不啟 UI。獨立 `-RollbackRun` 同樣先 idle 且檢查 exact Addons RECORD/舊 Qt bytes；未驗部分安裝不自動刪檔。

W6.D 先做 [原視窗接線準備](W6OwnerWiringPlan.md) 與可執行 transitive observer inventory／負例 regression；不將缺套件的正式入口切到 Web。W6.E/F 仍未通過，零 Widgets 刪除。最新結果見 [checkpoint](W6Checkpoint.md)，單指令見 [handoff](W6Handoff.md)。下列段落保留歷史。

## 2026-10-11 新授權續作：W6.A–F

以下為本次有效順序；下方保留前輪歷史，不再以「未授權安裝／關閉」作為阻塞理由。使用者允許精確關閉已核實的正式環境 Kuro PID，僅安裝 Addons==6.11.1，完成 W6 後停人審，不做 W7 或 commit/push。

本次 evidence：`.runtime/w6-execution-20261011T0840480172257Z/`。修改前 main/HEAD/index 與提供基線一致；1314 Git-visible paths、463 dirty paths，完整 SHA/absence 清單和局部 preimages 已保存。原六 renderer 不改。

| Gate | 操作與必要證據 | 精確 exit／停止條件 |
| --- | --- | --- |
| W6.A | 全新 PID/path/startTime/parent/role、listener 交叉確認；正常 Quit 優先；必要時只以核對身分的 PID/handle 終止；每次操作留 receipt | 所有正式 env consumers 消失且無未知 Python/pip；身分不明、active writer 或關閉超出授權即停止，不進 pip |
| W6.B | 新的 pip list/freeze --all/check、distribution RECORD/version/origin；官方 PyPI TLS wheel metadata/hash/tags、disk、無覆蓋檔案與 rollback；再次 idle check | exact Addons 6.11.1、--no-deps --only-binary；Essentials/shiboken 不變；失敗保存 evidence，僅能在 idle 下回退新增 Addons |
| W6.C | 正式 python -I -B w6_preflight.py；所有模組與 DLL 同 env、三套件 6.11.1、scheme pre-app、pip check delta | PREREQUISITES_PASS 與 PASS_BEFORE_APPLICATION；無新 dependency failure 才可進 source handoff |
| W6.D | 同一既有 QMainWindow 接唯一 WebHost；內容定址 owner bundle 驗證；保留 controller/client/tray/delivery；停止舊 Widget render observers；局部回歸與 preimages | 不建立隱藏 Widgets 或第二 owner；保留可回滾正式 Widgets，不能以 readiness 字串繞過 gate |
| W6.E | 正式 interpreter 上的 disposable existing-window harness；bridge/24 methods/Chat/History/Settings/Today/Schedule/menu/tray/X/Quit/reveal/second launch/late worker/security；不啟正式 profile/provider/DB | source 與 native 分開；GUI 不可達則 BLOCKED/UNVERIFIED 並交付正常 PowerShell relay；不得 offscreen/GPU/sandbox override 冒充 native |
| W6.F | 只有 exact existing-window native proof 及人審成立才精準退役 Widgets presentation；原六 SHA、G7 35 absent、index/全 WIP 獨立核對 | 缺證據則零破壞性刪除、保留 Widgets rollback；停 W6，不做 W7/release/commit/push |

W6.A 後續授權已明確涵蓋 Launcher-owned Pet；不再詢問此項授權。使用者另允許有界唯讀 EnumWindows、合成 WM_QUIT callback 實測；只有正式 GUI thread、精確身分、controller.close 與 Core idle 條件都成立才考慮套用。合成測試通過，但正式 EnumWindows 一般/提權皆失敗，依使用者指定停止，不強殺 Core、不等待或重啟。正常 Quit 改交使用者手動完成。

2026-10-11。使用者本輪已接受原始 Web 視覺；Today 3px／date／DPI 歷史 strict 數值保留，不再阻擋結構遷移，不改寫測試 PASS。W7、commit/push、正式依賴安裝及 runtime 啟停不在本輪。

原指定 `docs/agent-runs/kuro-original-web-cutover-20261010/W6Plan.md` 寫入失敗；依既有 task evidence 慣例把完整 W6 文件放在此處，不改 ACL 或繞過權限。

## 已確認起點與保全

- `main` / `af83df273602be3a616d6567855ea71d61a9ace7`；457 dirty entries。index/status 原始 bytes、tracked/staged diff、全部 Git-visible SHA/absence、16 份 scoped preimages：`.runtime/w6-source-20261011T080046Z/`。首次備份遇 stdin 編碼錯誤；改為 UTF-8 後完成，修改前確認 index/status 未变。
- VBS 固定正式 `envs/kuro-llm310/pythonw.exe`；console sibling 實測 Python 3.10.12、Essentials/shiboken6 6.11.1，但缺 Addons distribution 與 QtWebChannel/QtWebEngineCore/QtWebEngineWidgets。**正式採用／刪除 HARD BLOCKER**。不能注入 task Python 3.13 的 Qt DLL。
- 正式 `launcher_qt.main` → `KuroQtLauncherWindow.__init__` → `_build_ui` → `WorkCompanionView`；QApplication 前沒有 scheme 註冊。保留此入口。
- window 只建一次 controller/client/tray/QtScheduleDelivery；Core 是 Task/Attention/Today/Schedule/notification owner；Conversation/History/Memory/ToolPolicy 與 Pet/Voice owners 不變。
- native receipts 實際在 task `.runtime`：W3 `native-candidate-W3-20261011T0750039855024Z`、W5 `native-candidate-W5-20261011T0751593632426Z`。W5 有正常關閉欄位；W3 沒有。兩者都是 synthetic isolated owner，非正式 window lifecycle。

## Gate 與執行順序

| Gate | 本輪操作 | Exit／停止條件 |
| --- | --- | --- |
| W6.0 | exact backup；AST imports/calls/self-attributes/signals/timers/reverse references；正式無安裝 probe；native/G7/原六 SHA | 缺模組或 origin/version 不符即 formal BLOCKED；不啟正式 launcher、不讀 secret/provider |
| W6.1 staging | 原六 Git SHA 固定；唯一 owner Vite config/bridge/bootstrap；內容定址 `assets/qt-owner/<fingerprint>/` 編譯產物與 lineage；scheme 拒絕 QApplication 後註冊 | 不改/複製原六 source；驗 manifest/hash/CSP/非 synthetic；不接回正式入口 |
| W6.1 採用 | **BLOCKED**，解除依賴及 exact native gate 後才替換 existing window 的 `_build_ui` | readiness PASS 字串不能授權；本輪封住此旁路，host 仍 fixture-only |
| W6.2 | 完成 retirement graph/data-flow；實際正式 observer retirement **BLOCKED** | 必須和正式接線同批移除 Widget callbacks；不能建隱藏 Widgets 再掛 Web |
| W6.3 | **BLOCKED，零刪除** | exact formal runtime/native existing-window startup/shutdown/tray/second-launch/bridge + source review 後才依 reverse imports 精準刪 presentation |
| W6.4 | owner build/typecheck/manifest tamper/preflight negative/source graph/G3–G8/Pet/Core 回歸 | 保存真 exit/count/log；offscreen/disposable 不冒充 native；停 W6 |

## 原地接線／退役清單

`W6Inventory.json` 列每個 class/function 行號、self attribute read/store、call/signal 與反向 caller。這是 AST 語法圖，不能宣稱涵蓋反射/runtime。不能依名稱直接批量刪除。

| 目前路徑 | 正式切換時處理 |
| --- | --- |
| `__init__`: message_received→`_on_chat_protocol_message`、history_operation_changed→`_history_controls_changed` | 改由同一 Port 觀測；舊 render/history/create/send observers 不連接 |
| `_wire_signals`: state/assistant/history/client/error | 移除 Widget-only observers；保留必要 task/log/lifecycle，剝離死 widget 引用 |
| `_build_ui`、Chat/Settings/Memory/Pet/perception/tools、Composer/History/menu/attachments/transcript | Web 原版 DOM + owner bridge 接替，不建隱藏 QWidget 副本、不留可達 fallback |
| `_refresh_workspace_data`、`_refresh_profile_controls`、啟動 today.refresh | 移除 Widgets 初始化讀取；Web 明確 requests → 單一 adapter |
| status timer: refresh_status/expire_history_request/_refresh_core_pages/_ensure_desktop_entry | 保留 timeout/desktop保障；移除 Core pages polling；status completion 不碰 label/Pet widgets，不與 Web 重複讀取 |
| runtime timer→reconcile_runtime | 保留既有 lifecycle；task completion 不依賴已退役 UI |
| auto-empty-history、pending submit、history callbacks | 由唯一 adapter 處理 user intent，避免雙 new-history/send |
| tray/reveal/X/Quit/restart/cleanup | 保留既有 window owner；X→tray；Quit 先封 broker/斷 presentation signals，再停原 timers/client/controller/delivery；tray 不可用仍能退出 |
| qt_core_pages constants/helpers/classes | reverse imports 分離 shared constants 與 presentation；Core runtime/API/store/delivery 不刪 |
| theme／APP_STYLE | 只退役 presentation QSS，保留 window/tray/menu/modal shared style |

資料流：immutable renderer → owner-bootstrap（hello 後 import main）→ 24-method bridge → Wire.submit → RequestBroker（identity/revision/confirm/unknown fence）→ QtOwnerAdapter → 原 controller/client/Core。chat signals → GUI queued Port → Web。Web 無 WS/DB/notification claim-authorize-ack 權限。方法語意見 [24-method lineage](W1W5ClosureMethods-20261011.md)，本輪重新跑測試，不冒用歷史 receipts。

## Native/package 前提與精確停止點

1. 正常 Windows user 用正式 console sibling 跑新 preflight，記錄 executable/prefix/Python/Qt/module origins/distributions。exit0 只代表 import/registration，不能開 cutover。
2. 可由使用者選擇另建同 Python3.10 staging env 驗證同版本完整 Qt；腳本不自動下載/安裝/改正式 env。正式修復須先審核依賴衝突及回復方法。
3. scheme 在 QApplication 前註冊：[Qt 官方順序](https://doc.qt.io/qtforpython-6/PySide6/QtWebEngineCore/QWebEngineUrlSchemeHandler.html)。沿用本地 allowlist/CSP/off-record；拒絕任意 network/navigation/popup/download/permission/storage。
4. 正式 executable + 新 source/bundle fingerprint 下，使用隔離設定/state 測 **existing KuroQtLauncherWindow**：cold start、X/tray/reveal/Quit、second launch、restart/cleanup、late workers/context、one WS/notifier。現有 candidate runner 不能代替此證據。
5. 完成原地接線、source/native review 後才精準刪舊 Widgets；不能以 flag、receipt PASS 或 fixture marker 繞過。

## 回滾與 W7

本輪正式入口不變，無正式 cutover 可回滾；generated assets 未載入，不需刪 staging 恢復功能。source 回退先比對 final SHA/preimage，再逐 hunk；後續 WIP 有差異就停，禁止 reset/checkout/clean/stash。

W7 需 W6 正式 native/刪除 Gate 完成後另行人審與授權，包含真 provider/profile/IME/device/OS notification/Live2D/voice/release。本輪 source/synthetic PASS 不開 W7。

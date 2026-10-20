# W10 單一 Qt Web 桌面主視窗

## 範圍與基準

本輪使用者明確批准退役舊 Qt Widgets UI。初始 `main` 工作樹乾淨；
Git 回滾基準為 `f4980098b46986d0d0b6ca2ef7fbc538732913bc`。
原始檔案 bytes 與 SHA 保存於 ignored
`.tmp/w10-legacy-qt-retirement-20261020/preimage/`、`baseline.json`。
正式 runtime 未重啟；本輪不代表已載入 W10 source 或 native 驗收完成。

## 實際退役

`qt_app.py` 由 3,689 行縮至 291 行。按 AST 方法範圍逐項保留共用方法，
移除 136 個 Widgets builders／callbacks、constructor tail、`APP_STYLE`、
`QSettings`／舊字型載入／Preview／附件／Memory／History 展示 observers；
沒有用「刪除 `_build_ui` 之後所有程式」的方式處理。

物理刪除：

- `kuro_launcher/qt_work_companion_view.py`
- `kuro_launcher/qt_work_companion_theme.py`
- `kuro_launcher/qt_core_pages.py`
- `tests/work_companion_fixture.py`：僅建構退役 Widgets 的 fixture。
- `tests/test_r1_production_view.py`：舊 drawer UI 斷言退役；有效 transport／confirmation／timeline 行為見下表。

完整刪除方法、檔案 before／after SHA 見 [Changes.json](Changes.json)。

## 保留的正式 owner

入口仍為 VBS → `launcher_qt.py` → `prepare_owner_presentation` → `KuroQtLauncherWindow`。
驗證 bundle 與註冊 scheme 在 QApplication 前進行；缺 pin／缺檔／簽章或資產竄改會拒絕啟動。
constructor 的 `web_bundle` 為必要 keyword argument，非 `VerifiedOwnerBundle` 時在建立 QMainWindow／Controller 前拒絕。
`RELEASE_PIN` 的 fingerprint、manifest SHA、公鑰、簽章完全不變；僅刪除 `None` rollback。

保留同一個 QMainWindow、Controller、QtRuntimeChatClient、QSystemTrayIcon、
QtScheduleDelivery、原 icon、Qt.Tool／FramelessWindowHint、native modal／drag、
close／minimize-to-tray、reveal／activation、restart、startup auto-start。
2,500 ms status／data／history expiry timer、10,000 ms runtime reconcile timer、
單一 worker Port、單一 primary WS 及 lifecycle guards 延續既有 Web 分支。
QMainWindow／QMenu／QMessageBox／QSystemTrayIcon 仍由 QtWidgets 提供。

未修改 `qt_web_host.py`／adapter／protocol、Controller／Chat／notifications、
Core／Schedule／Conversation、Pet／renderer-dist、signed assets、bundle builder、
六份原始 Git Web frontend、font／icon、`memory_panel.py`／`ui_theme.py`。

## 測試遷移與歷史證據

| 原有責任 | W10 驗證位置 |
| --- | --- |
| R1 Client request correlation、identity、timeout、late replies | `test_r1_history_parity.ClientTests` 原方法保留 |
| R1 Runtime role／context、idempotency、confirmation、tool timeline | `RuntimeTests` 與 `TimelineTests` 保留 |
| R1 production drawer CRUD、cancel、multiline／tool evidence、同一 primary WS | `test_r4_history_transport` 真實 WS＋正式 Port／Broker／Adapter；`test_qt_web_candidate` confirmation／duplicate／stream fences |
| R4 strict owner read errors、event sidecar delete | 原 `test_strict_owner_read_errors_and_event_sidecar_delete` 方法原樣保留 |
| G4 Core route／query／contract／HTTP conflict | `CoreWrapperTests` 原方法保留 |
| R3 Today stale／invalid、order／evidence；Schedule revision／scope／confirmation | `test_r3_today_schedule_parity.CoreWebTests`；`test_qt_web_disposable` 真實 Core HTTP replay／revision conflict |
| R2 memory digest／actor fence、policy 不放寬 | `OwnerTests` 原方法保留；`test_qt_web_candidate`／`test_qt_web_w4_w5`／`test_qt_web_disposable` 驗證 Web confirmation、stale snapshot、profile adoption |
| G3 直接 Chat／History owner、G6 stale capture | 原 client／backend tests 保留；Web candidate／transport／existing-window／W4-W5 覆蓋新入口與 scope revocation |
| Tray、notification 唯一 delivery、cleanup | `test_g5_desktop` 改成 Web cleanup；`test_g8_runtime` 與 `RealOwnerIOTests` 保留真實 disposable Core dedup |
| W8 icon／Tool／frameless／minimize／reveal／modal | 移植至 `test_qt_web_w10`，增加 bundle 必填、single owner、timers、startup／shutdown |
| G7 35 個既有刪除檔案不復活 | `test_v1_work_companion_view.SourceCutoverTests` 保留 |
| 舊 layout、composer IME、drawer search、Widgets 截圖／標籤／editor serialization | 退役；不宣稱已驗證 immutable Web UI 的 native 視覺或所有操作 |

歷史 `devtools/git-work-companion-parity-20261010/after-source/**`、devtools receipts、
W6／W7／W8 gates 與其 tests 完全不改。它們的固定 source SHA／Widgets rollback
假設不適用 W10；完整排除清單及理由在新 `validate.py` 的
`HISTORICAL_EXCLUSIONS` 與執行 `Scope.json`。W7 `GestureProtocolTests` 仍選入，
其餘 source-bound classes 不選入。未更新舊 SHA 或宣稱歷史 PASS 可覆蓋 W10。

**已知 default-discovery 回歸：** 這四份歷史測試仍位於 `tests/`：
`test_qt_web_w6.py`、`test_qt_web_release_candidate.py`、
`test_qt_web_window_chrome.py`、`test_qt_web_w8.py`。
直接執行 `python -m unittest discover -s tests` 或 `pytest` 會收集它們；
舊 Widgets callbacks／可選 bundle／`None` rollback／固定 source SHA 預期與 W10 衝突。
本輪沒有跑全庫 discovery，也不宣稱全庫 green。新 `validate.py` 是固定明列的
W10 current selector，不接受任意略過 suite 取得 W10 PASS；`--target` 只能產生
development 結果。沒有以 pytest ignore、unittest skip 或改舊 SHA 隱藏此問題。
將歷史測試搬到專用 archive 並整理全庫 discovery 可另案處理；
本輪保留原位置與 bytes，避免改動既有 provenance／歷史 tools 的引用。

## 當前驗證

獨立 profile：

```powershell
.\envs\kuro-llm310\python.exe -B devtools/w10-legacy-qt-retirement-20261020/validate.py --output .tmp/w10-legacy-qt-retirement-20261020/current
git diff --check
```

[SourceBaseline.json](SourceBaseline.json) 固定 W10 source／tests／fixtures／validator
及受保護證據的 SHA；驗證前後都必須一致，缺檔／漂移 fail closed。
測試使用 repo 內 disposable TEMP／TMP、offscreen Qt、ephemeral loopback，
禁止正式 ports／外部 network。Qt surface 為 inert fixture；真實 Qt signals、
QWebChannel Port／Broker 邏輯、WS handler、Core HTTP／SQLite 依各測試執行。
不啟動正式 Qt／Pet／Core／LLM／TTS，不停用 WebEngine sandbox。

狀態：**`W10_SOURCE_ISOLATED_PASS`**，上列命令 exit **0**。
25 個 Python suite／class 共 **267 項**、Node frontend **20 項**，
合計 **287 項 PASS**，無 skip；Python syntax、`git diff --check` 通過。
350 個檔案 SHA 在驗證前後一致，baseline SHA-256 為
`899d40171e92f1e3ab3bdea74a7424f556ca80e8ed19cc40cb25417a8e77d969`。
精確 suite count／exit／耗時見 [ValidationReceipt.json](ValidationReceipt.json)；
完整 synthetic logs 在 ignored `.tmp/w10-legacy-qt-retirement-20261020/current/`。

本輪沒有 frontend source 改動，不重建 signed bundle／renderer；
驗證簽章與六份 Git original lineage、逐檔 tamper rejection 即足以確認資產沿用。
source／isolated PASS 不等於真實 Chromium renderer、Win11 桌面、
provider connectivity 或正式 runtime adoption PASS。

## W11 保留債務

- Mail 尚未完整串通；不改 provider／poller ownership。
- 部分原 Web 控制尚不在 protocol allowlist；維持拒絕，不為 UI 放寬權限。
- 原 Web 附件 caps 與現有 protocol caps 不一致；不在 W10 改 immutable frontend 或擴權。
- 舊前端 `schedule materialize` 呼叫仍遭拒絕；materialization 屬 Core scheduler。
- 首頁各功能「可顯示」不等於全部真實功能連通；裝置、tool policy／confirmation 仍維持現行邊界。

## 後續人工驗收與回滾

使用者稍後自行以正式入口 cold start，核對載入 W10 source、唯一 Qt window／tray／WS、
signed bundle、Chat／History／Today／Schedule／Settings、close／minimize／reveal、
二次啟動 activation、明確 Quit／Restart、auto-start、缺服務降級、native drag／Snap、
多螢幕／DPI／modal，以及原 Live2D／voice ownership。W10 本輪不執行這些正式操作。

若需要回滾，先保存當時新增 WIP，再經使用者授權從上述 Git baseline 或 raw preimage
成組復原本輪 source／tests／三個 UI modules；不能只把 pin 設成 `None`。
signed bundle、builder、Backend／Pet 本輪未改，無需以重建資產替代 source 回復。
不得使用 reset／clean／checkout／stash／rebase 或覆寫私人 runtime state。

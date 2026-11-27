# Qt Web 橫幅修復與簽章包採用

狀態：**Source PASS／Bundle PASS／Isolated Qt PASS／正式 Runtime Pending／Native UNVERIFIED**。
本輪沒有重啟正式 Kuro、Pet、Core 或外部服務，沒有 commit／push。

## 根因與修復

Qt 的正式前端只由 `qt_web_release.RELEASE_PIN` 選取已驗簽的 immutable bundle。
輸入 pin `2ec66143d6aca11dacc9c55a766039a19d86d275f2df91acfd6a63e334566876`
仍包含橫幅。前輪只刪除未採用的 `work-panel/main.ts`／`styles.css` 內容，沒有 build／pin 更新；
即使托盤已載入新版 `qt_app.py`，也不會改變該前端。直接保留那份 source patch 又會違反 builder 的 ORIGINALS byte-exact gate。

- 精確補回 main.ts 的 8 行及 CSS 原配置／尾端 4 行；六份 ORIGINALS 與 commit `995c23c7c8d1be62000229d58610d2214f3bb745` 位元一致。
- 在既有 `owner-presentation.ts` 的 `project()` 中移除所有現存 `[data-runtime-status]` 節點及其按鈕。沿用原 MutationObserver，初始 renderer 載入、狀態更新及後續 DOM 插入皆受涵蓋；沒有新增 observer／timer，無節點時不寫 DOM。
- `owner-presentation.css` 將 workspace 設為 header＋stage 兩列，stage 明確位於第 2 列。`#app` specificity 保證動態載入的原 CSS 不會重新指定第三列；未以 `display:none` 留下互動節點。
- 原 Settings／Diagnostics、Today 來源說明、工具設定、附件說明均保留。
- `qt_web_frontend.test.cjs` 改查 authoritative pin 對應實體 bundle、manifest／asset digest、adapter lineage 與編譯產物；實際 DOM 與幾何由既有 `g2_tools_today_surface.py --banner-regression` 驗證。

## 新版與回退資產

- Fingerprint：`535e20b1159abf091289fd88c289da753aa558037b71d8578a33ccb3903e3bac`
- Manifest SHA-256：`cf70389cd47dea973ec4c050d96684a3a49323de5f8b6b2a8f0ea4342e3f616d`
- 實體目錄：`assets/qt-owner/535e20b1159abf091289fd88c289da753aa558037b71d8578a33ccb3903e3bac/`
- 由未修改的現有 `build_owner_bundle.py` 建立 7 個新檔，Ed25519 簽章／manifest／lineage 自洽；`VerifiedOwnerBundle.load()` 直接 PASS。
- `kuro_launcher/qt_web_release.py` 的四個 pin 欄位已採用此 bundle。隔離 Qt 使用正式 `prepare_owner_presentation(ROOT)` 載入，並拒絕與 RELEASE_PIN 不同的 receipt。
- Build／verify 收據：`devtools/original-git-web-host-20261010/.runtime/kuro-banner-owner-20261024-{build,verify}.json`。
- 原 `2ec66143…` 及全部既有 74 個 asset 檔案雜湊不變；原 pin 直接驗簽亦 PASS。未採用其他目錄中的 newest bundle。

## 驗證與界線

收據根目錄：`.tmp/kuro-banner-owner-20261024/`，總表為 `Status.json`。

| 檢查 | 結果 |
| --- | --- |
| Frontend `tsc --noEmit` | PASS |
| Node frontend＋UI refinement | 25/25 PASS |
| 當前 W10、W8 tray、window chrome／gesture targeted tests | 30/30 PASS，包含現役 bundle lineage 與 asset tamper rejection |
| Python compile：release、保留的 qt_app、surface fixture | PASS，pyc 僅寫 task 暫存目錄 |
| 真實隔離 Qt WebEngine／合成 Core／合成 policy | 65/65 PASS，`surface-window/Result.json` |
| Chat／Today 初始與切頁、狀態更新、重新插入 banner | 節點 0、查看狀態按鈕 0；observer 在移除後收斂 |
| Chat／Today zoom 100／125／150% | 兩列、stage row 2、header→stage 與底部 gap 均為 0 |
| Settings／Diagnostics 與既有 refinement | 正式入口可達；工具確認／取消／readback、來源限制、附件與鍵盤焦點檢查 PASS |
| 舊 bundle、其他 WIP／受保護來源 | 1,433 份基線檔案中僅指定 7 份改變，其餘 1,426 份 byte-exact 不變 |
| Git diff check | PASS；HEAD 未變 |

已人工檢視 `surface-window/chat-no-banner-1.png` 與 `today-no-banner-1.png`，沒有橫幅或空白 grid track。
這是合成資料的隔離 Qt 證據，不是正式使用者 session、實際 DPI 或正式服務驗收。
原 UI refinement 工程紀錄、`qt_app.py`、四份既有 Python test WIP、builder／bootstrap／canonical-model 均保持原位元。

保留的失敗紀錄：第一輪 Node 斷言未涵蓋 Vite 將 `const`／引號轉成 `let`／反引號，已修正測試；第一輪手動指定 offscreen 造成 GPU 訊息與既有鍵盤焦點檢查失敗（`surface/Result.json`）。沿用前輪正常 Qt fixture 環境後完整通過，沒有改安全 flags 或關閉 sandbox。
另一次過廣 Python suite 選取觸及三個歷史 W7／W8 exact-source／固定 pin 斷言，結果見 `PythonTargeted.log`。它們在本輪輸入基線已不相符（W7 固定 `8ba8ea…`，輸入為 `2ec66143…`）；`Status.json` 保留逐檔基線差異。沒有修改歷史 gate、重寫既有四份 tests 或宣稱全套回歸通過。

## 重現命令

在 repo root，以現有 `envs/kuro-llm310/python.exe`，將 `C:\work\Git\cmd` 加入本次程序 PATH；Python tests 的 PYTHONPATH 包含 repo、`tests`、`Open-LLM-VTuber/src`。

```powershell
node pet-electron/node_modules/typescript/bin/tsc --project devtools/original-git-web-host-20261010/frontend/tsconfig.json --noEmit
node --test tests/qt_web_frontend.test.cjs tests/kuro_ui_refinement.test.cjs
.\envs\kuro-llm310\python.exe -B -m unittest test_qt_web_w10 test_qt_web_w8.W8IconTrayTests test_qt_web_window_chrome.ChromeWindowTests test_qt_web_window_chrome.GestureProtocolTests
.\envs\kuro-llm310\python.exe -B tests/g2_tools_today_surface.py --refinement --banner-regression --bundle-receipt devtools/original-git-web-host-20261010/.runtime/kuro-banner-owner-20261024-build.json --output C:\project\desktop-agent-runtime\.tmp\kuro-banner-owner-repeat
```

重跑需選新的不存在輸出目錄。下一次正式 Kuro 正常啟動會依新版 source pin 載入此包；本輪不操作現役程序，正式 Runtime 採用仍待使用者驗收。

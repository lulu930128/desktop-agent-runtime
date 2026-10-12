# G5 Desktop ownership checkpoint

## 2026-10-09 G5→G8 續作查缺

- 初始完整快照：`G5G8InitialPathSnapshot.json`；main / `995c23c7c8d1be62000229d58610d2214f3bb745`，35 modified + 53 untracked，924 tracked paths。記錄路徑與既有 WIP SHA-256，不讀 ignored private payload。
- 唯讀 `netstat -ano -p tcp`：23456/23567/23568/23569 無 LISTENING；18890 PID 42060，未操作。
- G5 source 回歸：`python -B -m unittest discover -s tests -p test_g5_desktop.py -q` 17/17，`test_launcher_entrypoint.py` 6/6，`test_pet_lifecycle.py` 17/17，各 exit=0。repo-root disposable TEMP/TMP、offscreen、no pyc；測後精確清除 temp。
- 真 Windows kernel smoke：隔離 UUID 名稱 mutex/event，第二個 Python process 驗證 duplicate mutex、signal activation、primary consume once，child exit=0。沒有觸發正式 launcher、GUI、讀 config/secrets 或既有桌面。這是 kernel 機制證據，非正式 second-launch 桌面驗收。
- `startup_auto_start=false` reveal、X/tray/reveal/quit、shutdown ordering、notification claim/authorize/display/ack 已有上述 synthetic/offscreen 證據；正式可見 UI、tray、OS notification、cold boot/restart/child adoption 全部仍 UNVERIFIED。正式啟動會讀私人設定並接觸正式 DB，本輪依限制改採隔離 smoke。
- confirmed defect：Pet 每 5 秒呼叫已移除的 :23568 `/v1/runtime`、`/v1/presentation`；須於 G6 改成 pet-local status 與 Launcher 明確 presentation push。
- architecture risk：Pet 殘留 Core token、WorkPanel handlers、Briefing store/Study watcher；G6 移除 active consumer 後，G7 才按 inventory 刪檔。
- confirmed defect：Pet renderer 的 mic submit/interrupt/text 仍能嘗試送 conversation-control 訊息，但 Runtime pet-presentation 已拒絕；G6 需去除 trigger/proxy，Qt 保持唯一對話入口。
- G5 判定：source checkpoint 可續作 G6；runtime adoption 未驗收，不宣称 desktop accepted。Rollback 只回復本 Gate source；不可 git reset/clean 既有 WIP、不可回復正式資料庫。

以下保留原 G5 歷史紀錄。


日期：2026-10-09

狀態：**G5 source-ready；正式 runtime adoption／人工桌面驗收未做。G6/G7 未實作。**

## 完成範圍

- `launcher_qt.py` 保留 launcher mutex，activation event 改為 `Local\KuroDesktopAgentQtActivate`。首次直接 reveal Qt；再次啟動只 signal primary，由 primary reveal Qt。`startup_auto_start=false` 不再阻擋 UI。
- Canonical launcher 不 import／construct／start `WorkPanelControlServer`，不呼叫 `request_work_panel_activation`，不開 `:23568`。這是 source path 證據，未對正式 listener 做 live 宣告。
- `桌寵啟動器.vbs` 不再要求 `renderer-dist/work-panel.html`；仍使用 repo Python 啟動 Qt。
- `qt_app.py` 建立唯一 Qt tray，Show／message click／second launch 都 reveal Qt。X 隱藏到 tray，不關 controller；tray 不可用時保持視窗可見，週期檢查也能找回失去 tray 的隱藏視窗；Kuro menu 提供明確 Quit。
- Quit 先停止 timers／notification delivery，再清理空白 history、disconnect chat、呼叫既有 controller cleanup、hide tray、app.quit。Cleanup guard 防止 aboutToQuit 重複關閉；restart 經 explicit quit，不被 close-to-tray 攔截。Canonical restart 使用 Qt native confirmation；history／memory／Schedule 仍沿用原有 Qt confirmation，不依赖 Work Panel confirmation。
- 新增 `qt_notifications.py`：Core claim → authorize（dispatching）→ Qt 主執行緒 showMessage → Core ack。單一 background worker 持續涵蓋 ack；每個 HTTP request 沿用 CoreRuntime 的 1 秒 timeout，UI dispatch deadline 2 秒。延遲 queued signal 不得顯示過期通知。
- authorize false／conflict 不顯示、不 ack delivered；show failure ack failed；UI dispatch timeout／shutdown ack unknown；ack failure 只記錄 exception type，不在 Qt 重試或洩露 title／lease token。Core 繼續擁有 due、quiet、retry、lease、fencing。
- Qt `showMessage` 沒有 OS delivery receipt；本實作的 delivered 僅表示呼叫正常返回、完成 API handoff，不能證明 Windows 實際展示或使用者已閱讀。OS 靜音／通知中心／click 必須留待桌面驗收。
- Pet child env 先清 inherited `KURO_DESKTOP_OWNER` 再設 `qt`，同時清 stale launcher control token。Electron Qt-owner 模式不 createTray、不 startScheduleNotifications；Pet window、model protocol、Live2D/audio/presentation 保留。Standalone legacy mode 仍可走原 tray／notification code。
- `window-all-closed` diagnostic 的 `trayResident` 使用 `!qtDesktopOwner`，不宣稱 Qt-owner Electron 有 tray。

## 本輪檔案

Source：`launcher_qt.py`、`kuro_launcher/qt_app.py`、`kuro_launcher/qt_controller.py`、新增 `kuro_launcher/qt_notifications.py`、`pet-electron/src/main.js`、`桌寵啟動器.vbs`。

Tests：新增 `tests/test_g5_desktop.py`、`tests/g5_desktop_owner.test.cjs`；更新 `tests/test_launcher_entrypoint.py`、`tests/test_work_panel_activation.py`。保留 G1–G4 與其他既有 dirty changes。

文件：本 checkpoint、`Progress.md`、`MigrationMatrix.md`、`G5DesktopCutoverPlan.md`、architecture 的 RuntimeArchitecture／RuntimeServices／OwnershipMap。

## 最終完整回歸

每個 Python pattern 獨立 process：

```powershell
.\envs\kuro-llm310\python.exe -B -m unittest discover -s tests -p <pattern> -q
```

| Pattern／檢查 | 結果 |
| --- | ---: |
| test_g5_desktop.py | 17/17 PASS |
| test_launcher_entrypoint.py | 6/6 PASS |
| test_g4_qt_core.py | 15/15 PASS |
| test_g3_conversation.py | 27/27 PASS |
| test_runtime_capabilities.py | 8/8 PASS |
| test_kuro_core*.py（含 Study/Mail adapters） | 137/137 PASS |
| test_schedule*.py | 44/44 PASS |
| test_mail_status_handoff.py | 16/16 PASS |
| test_mail_work_handoff.py | 7/7 PASS |
| test_mail_poller_runtime.py | 9/9 PASS |
| test_pet_lifecycle.py | 17/17 PASS |
| test_work_panel_activation.py | 6/6 PASS |
| test_work_panel_api.py | 8/8 PASS |
| Python 合計 | 317/317 PASS |
| node --test tests/g5_desktop_owner.test.cjs | 3/3 PASS（亦包含在下列 83 項內） |
| 全部 tests/*.test.cjs、tests/*.test.mjs，node --test | 83/83 PASS |
| npm.cmd --prefix pet-electron run check:renderer | PASS |
| node --check pet-electron/src/main.js | PASS |
| git -c core.safecrlf=false diff --check | PASS |

Qt tests 使用 offscreen、synthetic controller／tray；Node owner tests 執行 main.js 實際 startup statements，驗證 qt／electron／未設 flag 三種情況，並確認 Pet/model startup 保留。未啟動正式桌面 stack，也沒有真 OS notification delivery。

## 追加 A–D 分批驗證（未改 source、未包 integrity）

依使用者要求，完整回歸通過後另分批保留每個 process exit；失敗時保留 traceback 並繼續其他項目。實際沒有 failure。

| 批次 | 每項 exit code |
| --- | --- |
| A | test_g3_conversation.py=0；test_runtime_capabilities.py=0；test_kuro_core*.py=0；test_schedule*.py=0 |
| B | test_mail_status_handoff.py=0；test_mail_work_handoff.py=0；test_mail_poller_runtime.py=0；test_launcher_entrypoint.py=0；test_pet_lifecycle.py=0；test_work_panel_activation.py=0；test_work_panel_api.py=0 |
| C | 全部 Node tests=0，83/83 PASS |
| D | renderer check=0；node --check main.js=0；git diff --check=0 |

A/B 每個 Python pattern 是獨立 process；A/B/C 各使用新 repo-root disposable TEMP/TMP，finally 驗證 exact parent 後清除。此追加批次沒有混入 integrity 判斷，也沒有 source 修正。Node 既有 MODULE_TYPELESS_PACKAGE_JSON warning 非 test failure；未因此修改 package.json。

## Temp／path-set integrity

- Python 設 `PYTHONDONTWRITEBYTECODE=1`、`QT_QPA_PLATFORM=offscreen`；PYTHONPATH 包含 repo 的 `Open-LLM-VTuber/src` 與 `Open-LLM-VTuber`。
- TEMP／TMP 使用新建 repo-root `.validation-temp-g5-final-9cdc0468f17d4a0699198fe553ac552c`；Node 設 process-local `NODE_DISABLE_COMPILE_CACHE=1`。
- `finally` 先確認 resolved parent 為本 repo root，再精確刪除該 disposable directory。
- 最終完整回歸前後 Git status、tracked/untracked file set、ignored pyc/tmp path set 全部相同；未讀取或 hash ignored private 檔案。
- 先前完整測試本身通過，但 wrapper 在刪除 disposable Node compile cache 前比較 status，導致 integrity failure。已修正驗證順序並重跑全套通過；舊 targeted／regression disposable roots 也已精確清除。
- Source 使用 fileChange／Project Workspace guarded patch 完成受限檔案寫入，未修改 ACL。未 commit／push。

## 未做／後續驗收

- 正式 runtime reload、Windows mutex/event／single-instance 真桌面行為、唯一 tray、OS notification 展示／click、實際退出與 restart 的 owned child cleanup：尚未人工驗收。
- 正式 `:23568` listener inventory 未量測；不能將 entrypoint 的無 listener construction 推論為既有程序已消失。
- Legacy WorkPanel／Reader／Briefing／work_panel_api 模組與 handlers 保留；physical deletion 留待 G7。Live2D render/presentation 架構未更動，G6 未做。
- 未讀寫正式 Core DB／mail handoff，未操作 Central Voice、全域設定或 ACL。

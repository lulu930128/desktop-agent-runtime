# W6 原視窗接線準備：2026-10-11 退出後續作

最新實作、當次 owner inventory 與 source/native gate 見 [W6FinalCheckpoint](W6FinalCheckpoint.md)。本檔以下保留接線前的風險清冊；其中 STATIC_PREPARATION_ONLY／尚未改 source／DOWNLOAD_BLOCKED 不是 D/E/F 當前狀態。

狀態是 **STATIC_PREPARATION_ONLY**。本輪未改 `launcher_qt.py`、`qt_app.py`、host/adapter、requirements 或 VBS，也沒有建立可開啟正式 Web 的旁路。W6.B DOWNLOAD_BLOCKED 不影響本清冊與離線測試；但缺套件時不能聲稱 existing-window native acceptance。

## 本次重新查到的接線風險

`w6_owner_plan.py` 對目前 `KuroQtLauncherWindow` 建立 self-call 可達圖，記錄每條 signal 的來源行、callback、間接方法、Widget attributes 和可能 mutation calls。這補上原 inventory 只有直接 calls 的限制。它不匯入 Qt、不建 owner、不讀設定或私人 state。

目前四個 lexical 建構點各一個：Controller、QtRuntimeChatClient、QtScheduleDelivery、QSystemTrayIcon。53 個 connect expressions 中，36 個經目前 Widget attribute 清單可到達 presentation。這不是 runtime instance proof，也不是完整動態呼叫圖；結果有列限制，不能把計數當獨佔驗收。

新 evidence：`.runtime/w6-resume-install-20261011T0905184749243Z/OwnerObserverPlan-final.json`（包含原始檔 bytes SHA256）。重產命令：

```powershell
& .\envs\kuro-llm310\python.exe -I -B .\devtools\original-git-web-host-20261010\w6_owner_plan.py --output .\devtools\original-git-web-host-20261010\.runtime\<新的目錄>\OwnerObserverPlan.json
```

## 後續局部實作順序

| 現有位置 | 同批變更及必須保留的行為 |
| --- | --- |
| `launcher_qt.main`，QApplication 建立前 | 正式依賴驗證後才加入 scheme 註冊；不改 mutex／activation event／aboutToQuit ownership，不讀 receipt PASS 字串授權 UI |
| `qt_app.__init__` 及 `_build_ui` | 同一 QMainWindow 建一個 Web view；不建立隱藏 WorkCompanionView、TodayPage、SchedulePage、Settings surface。單一 controller/client/tray/delivery 保留 |
| `message_received`、`history_operation_changed`、`_wire_signals` | Widget render/history/create/send callbacks 整組不連接，由現有 Port 的兩條 chat signal 接唯一 adapter；不得新增 WS 或第二 history observer |
| `task_finished -> _on_task_finished -> _apply_status` | 目前間接觸碰 `runtime_detail`、Pet controls、preview。必須把 lifecycle completion 與 Widget render 分離，不能只靠 `hasattr` 避免 crash 或保留 ghost callback |
| `_maybe_auto_connect_chat`、`_connect_chat` | 現在 auto-connect 位於 Widget `_apply_status` 路徑，adapter 自己不負責 connect。收斂時保留 existing client 的連線責任，移除 `_set_chat_status` Widget 依賴；不能刪掉所有 status handling 而導致 Web 永遠離線 |
| status timer、`getState` | 移除 `_refresh_core_pages`、初始化 `today_page.refresh()` 和 `_refresh_workspace_data`。明確區分 lifecycle health 與 Web projection，避免兩條重複 status reads；不得以新增第二 cache 解決 |
| startup auto-start | 現有 `_start_profile` 依賴 pending Widget history state。切換時保留同一 Controller 的 startup intent，與 adapter `applyProfile` 共用有效 profile/lifecycle；新隔離 harness 強制 `startup_auto_start=False`，不跑正式 profile |
| `cleanup`／worker completion | 先關閉 Port broker、斷 presentation bindings、拒絕晚到 callback，再停 timer/delivery、disconnect 原 client、原 controller.close；必須 idempotent。不能只保留 view.destroyed 關 broker，因 QApplication Quit 時可能太晚 |
| X／tray／Quit／second launch | 保留現有 `closeEvent`、reveal、system tray unavailable fallback。Web closeWindow 經 owner.close()；不沿用 candidate X 直接結束程序的語意 |

## 原生 harness 規格與停止條件

套件 gate 成立後，下一批需真正呼叫當時的 `KuroQtLauncherWindow` constructor，使用隔離 config/QSettings/DB、合成 Controller IO、現有 chat client 的 ephemeral WS。不能呼叫 `launcher_qt.main`，因它會載入正式 env/config/logging。不得用第二 QMainWindow 或 monkeypatch 掉 presentation constructor 來宣稱驗過現有視窗。

測 cold start、唯一 QWebChannel/WS/tray/delivery、24 methods、Chat/History/Settings/Today/Schedule、X→tray/reveal/Quit、第二程序用隔離 mutex/event 名稱的 activation、late callbacks、context fencing、read-no-write、notification dedup，並留下 exact argv/source/bundle/interpreter hashes。IME/focus、可見視窗與 native scheme/security 必須由正常 Windows 完成；offscreen/fixture PASS 只記 source/disposable。

正式 source 接線與其 native proof 尚未執行。套件 relay 只到 W6.B/C，不自動跨到 D/E/F。只有 existing-window 完整驗收與人審成立，才按照 graph 精準退役 Widgets；此前保留現有入口和本輪 preimages。W7 未開始。

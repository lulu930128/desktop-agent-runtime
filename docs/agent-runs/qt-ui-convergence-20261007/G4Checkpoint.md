# G4 Qt Core wiring checkpoint

日期：2026-10-09

狀態：**G4 source-ready；G5 未開始。** 本 checkpoint 記錄 source、synthetic regression 與 offscreen Qt construction；不代表正式 runtime adoption 或實機桌面驗收。

## 完成範圍

- `qt_app.py` import 既有 `MAIN_NAV_KEYS`、`SETTINGS_LABELS`、`TodayPage`、`SchedulePage`、`CoreHealthPage`；未重寫或修改 `qt_core_pages.py`、controller wrappers。
- 主 nav、stack order 與實際 widgets 為 `chat / today / schedule`；舊 Briefing builders 不再參與 canonical construction，舊 Briefing 導航 alias 轉至 Today。
- Qt window 初始化讀取 Today，sidebar 使用 Today summary。週期更新只讀可見的 Today 或 Settings Sources；Schedule 於進頁或明確操作時讀取，避免週期重設選取、分頁或編輯內容。
- Task completion 不再呼叫 `refresh_briefing`。Legacy methods 保留；canonical nav、startup data read、periodic refresh 與 task flow 不再讀 `read_briefing_summary` / Pet `/briefing`。
- Settings order 為 `general / appearance / conversation / sources / advanced`，labels 使用既有 `SETTINGS_LABELS`；sources widget 為 `CoreHealthPage`，旧來源設定 alias 亦導向此頁。
- Today 只經 controller `/v1/today`；Schedule view/item/prepare/mutate/materialize/notification-action 全走既有 CoreRuntime request，Qt 未新增 DB/provider/handoff IO。
- Reviewer UX 修正：Qt chat `+` menu 移除 Reader／Briefing 獨立視窗 toggles；保留附件、Mic、Camera、Screen、Browser、顯示桌寵與停止輸出。底層 legacy methods 留待 G7。

## 本輪變更檔案

- `kuro_launcher/qt_app.py`：局部 wiring 與兩個 menu entries 移除；保留既有 G3 dirty changes。
- `tests/test_g4_qt_core.py`：15 項 synthetic tests。
- 本 checkpoint。

## G4 測試涵蓋

- 實際 Qt window nav、stack widgets、Settings order/labels、CoreHealth widget 與 startup Today 讀取。
- 可見頁週期讀取、Schedule 不被週期重設、legacy aliases 與 task completion 不讀 Pet Briefing。
- AST 反向鎖定 canonical methods 不得引用 Briefing read/refresh/builders；僅保留獨立 legacy builders/method。
- Today healthy/degraded empty 語意、來源限制、invalid contract、Core unavailable 清除舊 evidence；完整度未知不包裝成空工作。
- CoreHealth 的 status 與 Today 獨立失敗並保留有效證據。
- Schedule query encoding、全部 controller wrappers、revision/scope/occurrenceDate/action serialization、Core unavailable/conflict/invalid response。
- Editor prepare 後才 mutate；prepare 失敗不提交；lost-response 同內容 retry 保留 idempotency key，修改輸入才換 key。
- 實際 `+` menu QAction 集合不含 Reader／Briefing；四個保留 toggle 的 checked state 與 callback action key 正確。

Offscreen smoke 使用 `QT_QPA_PLATFORM=offscreen`，實際建立 `KuroQtLauncherWindow`、canonical stacks、Core pages、ScheduleEditor 與 chat menu。Controller 使用 synthetic mock；無關的 profile/history/settings builders 與 lifecycle IO 在測試邊界替換。這不是完整實機視覺／互動驗收。

## 驗證結果

每個 Python pattern 使用獨立 process：

```powershell
.\envs\kuro-llm310\python.exe -B -m unittest discover -s tests -p <pattern> -q
```

設定 `PYTHONDONTWRITEBYTECODE=1`；TEMP/TMP 指向 disposable repo-local directory，最後 targeted 使用 repo root 的 `.validation-temp-g4-<unique>`。完整回歸的 PYTHONPATH 包含 repo 的 `Open-LLM-VTuber/src` 與 `Open-LLM-VTuber`。

| Pattern / 檢查 | 結果 |
| --- | ---: |
| test_g4_qt_core.py（Reviewer menu 修正後） | 15/15 PASS |
| test_g3_conversation.py | 27/27 PASS |
| test_runtime_capabilities.py | 8/8 PASS |
| test_kuro_core*.py（含 Mail/Study adapters） | 137/137 PASS |
| test_schedule*.py | 44/44 PASS |
| test_mail_status_handoff.py | 16/16 PASS |
| test_mail_work_handoff.py | 7/7 PASS |
| test_mail_poller_runtime.py | 9/9 PASS |
| test_launcher_entrypoint.py | 5/5 PASS |
| test_pet_lifecycle.py | 17/17 PASS |
| test_work_panel_activation.py | 6/6 PASS |
| test_work_panel_api.py | 8/8 PASS |
| 全部 tests/*.test.cjs 與 tests/*.test.mjs，node --test | 80/80 PASS |
| npm.cmd --prefix pet-electron run check:renderer | PASS |
| Python UTF-8 / in-memory compile（wiring 階段） | PASS |
| git -c core.safecrlf=false diff --check | PASS |

完整回歸於 menu 修正前通過，當時 G4 為 14/14；menu 修正後依指定範圍只重跑 G4，新增 QAction 反向測試後為 15/15，未重跑其他回歸。

### Integrity

- 最後 targeted 前後 Git status、tracked/untracked file set、ignored pyc/tmp path set、既有 `.tmp` path set 及 G4 disposable-root path set 全部相同。
- 最後 integrity 僅比較 path sets，使用 `git ls-files -z` 避免中文路徑跳脫；沒有 read/hash ignored paths。
- Disposable temp 已清除，既有 G4 disposable directories 為空。
- 先前追加 combined hash wrapper 在測試開始前因 Git quoted Unicode path 解析中止，屬 validation wrapper failure，不是 source/test failure；後續 hash 重試已停止。最終採上述 path-set-only 驗證。
- Checkpoint 的一般 apply_patch 寫入失敗後，改由 Project Workspace create_text_file 建立，未修改 ACL。

## 邊界與停止點

未修改 `launcher_qt.py`、WorkPanelControlServer、startup ownership、tray、second-launch 或 OS notification delivery；未 physical delete Electron legacy；未啟動正式 stack、操作 Central Voice、改 ACL、commit 或 push。

G4 停在 source-ready。**G5 未開始**；正式 runtime adoption、桌面人工驗收及 G7 legacy removal 不在本次成果內。

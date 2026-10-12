# G6 Live2D-only 收斂 checkpoint

> 本檔保留 G6 結束時的測試數與階段狀態；後續 G7/G8 已執行，最新 source／physical deletion／runtime verdict 見 [G8Checkpoint](G8Checkpoint.md)。

日期：2026-10-09。狀態：**G6 source-ready；正式桌面／device／notification 驗收 UNVERIFIED。G7 實體刪除待 inventory。**

## 實際變更與 ownership

- Electron main 僅建一個 Pet BrowserWindow，保留 Live2D/model/audio/lipsync/input/geometry。移除 WorkPanel/Reader/Briefing 視窗建構、IPC、launcher HTTP proxy、history/memory/tool policy/confirmation、Core client、Mail service/Study watcher、Tray 與 Schedule delivery 啟動。任何 KURO_DESKTOP_OWNER 值都不再開啟 standalone legacy application。
- `:23567` 僅 pet-local status/inspector/preview/backend configuration/allowlisted commands。舊 `/briefing/*`、`/mail/*`、`/work-panel/*`、Schedule routes 為 404；send-text、interrupt conversation、business actions 在 dispatch 前拒絕。instance fencing 仍驗證。
- 修復 confirmed defect：5 秒 probe 只讀 renderer，不再 GET `:23568/v1/runtime` 或 presentation。missing/loading/failed/offscreen/ready 由 pet-local evidence 推導，不用 Launcher failure 冒充 Pet failure。
- Launcher bootstrap descriptor + explicit `set-presentation` push 為唯一模型來源；沿用 registered local-model allowlist，profile/既有 shell 也推送，未建新 service/cache/gateway。Qt 持有 lifecycle diagnostics。
- Launcher Core/Mail poller startup 移出 Pet spawn，沿用既有 owner，在 profile startup 呼叫；Pet child 不注入 Core bearer/instance、Mail handoff 或 launcher control token。inherited 值清除。
- 修復 G3/G4 殘留的 capture trigger 缺陷：Pet 只回傳 Qt 明確要求的擷取結果，Qt primary WS 送 mic chunks/end；最多 60 秒 PCM16，bad/oversized/offline/uncertain send fail closed、不重播。Camera/Screen 附件亦由 Qt 發送。Pet 無 sendText/sendInterrupt/history methods；保留實際 audio queue/ack。未實測硬體或讀私人影像／錄音。
- Browser toggle 原本只改 boolean、沒有可用 browser implementation，明確 DELETE。停止對話由 Qt interrupt；Pet context menu 的 stop 僅停止本地播放，hide 只隱藏 Pet。
- Vite production entry 僅 index.html。未重做 Cubism、Live2D renderer 或商業 policy。

## 變更檔案

- `pet-electron/src/main.js`、`main-process/control-server.js`、`main-process/menus.js`、新增 `main-process/pet-status.js`。
- `pet-electron/renderer/src/main.ts`、`env.d.ts`、`backend/backend-client.ts`、`backend/types.ts`、`backend/kuro-backend-events.ts`、`backend/adapters/llm-vtuber-adapter.ts`、`commands/pet-command-router.ts`；`vite.renderer.config.ts`。
- `kuro_launcher/qt_controller.py`、`qt_chat_client.py`、`qt_app.py`。
- 新 `tests/g6_pet_shell.test.cjs`、`tests/test_g6_pet_boundary.py`；更新 G3/G4/G5、pet lifecycle/runtime capability tests。

## 實際驗證

Python：`envs/kuro-llm310/python.exe -B -m unittest discover -s tests -p <pattern> -q`；每個 pattern 獨立 process。

| Pattern | 最終結果 |
| --- | --- |
| test_g6_pet_boundary.py | 9/9，exit 0 |
| test_g3_conversation.py | 27/27，exit 0 |
| test_g4_qt_core.py | 15/15，exit 0 |
| test_g5_desktop.py | 17/17，exit 0 |
| test_pet_lifecycle.py | 17/17，exit 0 |
| test_runtime_capabilities.py | 8/8，exit 0 |
| Python 合計 | 93/93 |
| node --test tests/g6_pet_shell.test.cjs tests/g3_presentation.test.cjs tests/g5_desktop_owner.test.cjs | 20/20，exit 0 |
| npm.cmd --prefix pet-electron run check:renderer | exit 0 |

Node tests 真實啟動 disposable loopback HTTP server（port=0），驗證 status timeout、404、command allowlist、identity mismatch；不啟動 Electron GUI。
初跑 G4 fixture 還要求 Browser、pet lifecycle fixture 缺新 presentation dependency，兩項失敗；依 explicit DELETE 與 descriptor push 更新 fixture 後重跑皆通過，沒有刪掉仍有效的 assertions。
Python 使用 offscreen、no pyc、repo-root disposable TEMP/TMP，結束後驗證 parent 並精確刪除。未操作 Central Voice、OAuth/provider、正式 DB/模型/voice/userData。

## G7 前 inventory 門檻／限制

Main active consumers 已移除，完整 legacy files、Qt dead helpers、config/tests/docs 仍需逐項清查；此處不宣稱 repo-wide consumers=0。
正式 Windows desktop、Live2D rendering/device/audio、profile reload 視覺效果皆 UNVERIFIED；G8 將提供手動步驟。
Rollback 須依本 Gate diff 還原 source 並保留最初 88 WIP；不可 reset/clean、不可回滾私人 DB 或啟動第二 owner。

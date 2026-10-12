# G3 checkpoint — source-ready

日期：2026-10-09

狀態：G3 source-ready；G4/G5 未開始。這是 source 與 synthetic protocol 驗證，不代表正式 runtime 已採用，亦不代表實機聲音／Live2D 人工驗收。

## 已完成

- Runtime 新增 `qt-primary`／`pet-presentation`。Qt 是 canonical controllable session；Pet 不建立 ServiceContext、history 或 ChatGroup，不是 hot-switch target。初始化中的角色也納入 admission，避免並行連線建立兩個 controllable frontend。
- Pet inbound 僅允許 heartbeat、request-init-config、audio-play-start、frontend-playback-complete，其餘 fail closed。禁止透過群組把 Qt/Pet 合併。
- individual conversation 注入 primary output wrapper：原始訊息給 Qt；Pet 僅接收 allowlist 的 audio/display/Live2D actions、full-text、presentation control／synth markers。History、config、admin、error 與未知訊息不鏡射。
- 每個 primary turn 有獨立 playback wait 與 request_id；Pet ack 只完成相符 turn。快速 ack 不遺失、舊 ack 不完成新 turn，全部 Pet 完成才結束等待。Pet absent／斷線／delivery failure 不讓 Qt 等 30 秒。Qt 不回假 ack，也不在 synthesis 完成時提前變 idle。
- Qt text／attachments／interrupt／history create/select/delete/list 直走 runtime WebSocket。空白草稿先 create，收到 new-history-created 後只送一次 pending text；history-list 不偷偷切換 current session。Connected history 使用 WS response，offline cleanup 不走 controller fallback。
- Launcher 注入 Pet role URL；Pet backend client 在 constructor 與 applyConfig 都固定 pet-presentation，連線時只要求 presentation init，不建立 history。保留 media capture、audio queue、lip-sync 與 Live2D 既有實作。

## G3 變更檔案

- `Open-LLM-VTuber/src/open_llm_vtuber/websocket_handler.py`
- `Open-LLM-VTuber/src/open_llm_vtuber/conversations/conversation_handler.py`
- `Open-LLM-VTuber/src/open_llm_vtuber/conversations/conversation_utils.py`：只增加 primary playback waiter 選擇；legacy waiter 保留。
- `kuro_launcher/qt_app.py`
- `kuro_launcher/qt_chat_client.py`
- `kuro_launcher/qt_controller.py`：G3 僅修改 KURO_BACKEND_WS_URL role；保留既有 G2 dirty changes。
- `pet-electron/renderer/src/backend/backend-client.ts`
- `tests/test_g3_conversation.py`
- `tests/g3_presentation.test.cjs`
- 本 checkpoint。

## 驗證

Python 使用 `envs/kuro-llm310/python.exe -B -m unittest discover -s tests -p <pattern> -q`，每個 pattern 在獨立 process 執行。設定 PYTHONDONTWRITEBYTECODE=1，PYTHONPATH 加入 repo 的 Open-LLM-VTuber/src 與 Open-LLM-VTuber；TEMP/TMP 指向 repo 內 disposable directory。

| Pattern | 通過 |
| --- | ---: |
| test_g3_conversation.py | 27/27 |
| test_runtime_capabilities.py | 8/8 |
| test_kuro_core*.py | 137/137 |
| test_schedule*.py | 44/44 |
| test_mail_status_handoff.py | 16/16 |
| test_mail_work_handoff.py | 7/7 |
| test_mail_poller_runtime.py | 9/9 |
| test_launcher_entrypoint.py | 5/5 |
| test_pet_lifecycle.py | 17/17 |
| test_work_panel_activation.py | 6/6 |
| test_work_panel_api.py | 8/8 |
| 合計 | 284/284 |

- `node --test` 跑 tests/*.test.cjs 與 tests/*.test.mjs：80/80 PASS，包含 Core client 4 項及新增 Pet protocol 5 項。
- `npm --prefix pet-electron run check:renderer`：PASS。
- 7 個 G3 Python source/test 檔 UTF-8 讀回與 in-memory compile：PASS。
- `git -c core.safecrlf=false diff --check`：PASS。
- 測試前後 Git status 相同；ignored pyc/tmp 新增 0、移除 0；disposable temp 已清除。

額外合併所有 Python suite 至單一 process 時，既有 CoreHostTests.test_duplicate_auth_and_length_rejected 兩次遇到 Windows ConnectionAbortedError [WinError 10053]。Core host 獨立 20/20、完整 Core pattern 獨立 137/137 均通過；未更動 Core source 或該測試。合併 process 的不穩定性仍保留為限制，不宣稱該執行方式全綠。

Pet renderer 與 finalizer 的 shell 寫入曾受檔案權限限制，已由 Project Workspace SHA-guarded exact patch 完成；未更改 ACL。

## 邊界

- 未修改 Today、DB、Qt feature parity、startup/tray；未 physical delete legacy。
- 未讀取正式 private payload、未啟動正式 stack、未操作 Central Voice、未 commit/push。
- Mic/camera/screen capture 的既有實作保留。Canonical Pet role 不具 conversation trigger 權限；perception ownership／UI parity 留待 G4，不在 G3 恢復 Pet controllable path。
- 下一步僅能在另行授權下做 runtime adoption／實機驗收；本次停在 G3 source-ready。

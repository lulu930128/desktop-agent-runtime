# P1 WS dispatch 修正 checkpoint

Reviewer 指出新方法插入造成 `self._message_handlers = self._init_message_handlers()` 落入 `_handle_fenced_history` 尾端。修正前唯讀搜尋確實定位於該 async 方法內。已將它放回 `WebSocketHandler.__init__`，History 不再重新初始化 handler mapping。

- `R1DispatchFix.json` 保存 AST assignment owner、檔案 SHA-256、測試數與複查狀態。
- `test_r1_ws_dispatch_regression.py.txt`：6/6。覆蓋建構即有 bound handlers、Qt-primary 在第一則 History 前的普通路由、History 後 mapping 不變、frontend 舊 history/other 路由、console restrictions、Pet allowlist。
- `test_r1_history_parity.py.txt`：17/17。
- `test_g3_conversation.py.txt`：27/27，含 Pet 缺席對話、原路由／獨占／ack／interrupt。
- 測試命令：`envs/kuro-llm310/python.exe -B tests/run_work_companion_parity.py test_r1_ws_dispatch_regression.py test_r1_history_parity.py test_g3_conversation.py`。

先前測試 runner 未 capture child output 不能作證；已改為保存 UTF-8 stdout/stderr、檢查實際測試數，並修正父程序 cp950 無法列印原有 emoji log 的問題。G3 有兩次實際失敗：list 缺少 current uid 欄位不應清掉既有選取，已修正；回應順序測試更新為 history.v1 的合法 request/reply fixture，仍驗證 observer 執行前 client uid 已更新，不放寬 stale-response fencing。

Reviewer 靜態複查：**PENDING**。正式 runtime／桌面：**UNVERIFIED**。本 checkpoint 不代表 R1 全部完成，尚未完成正式 drawer 接線。

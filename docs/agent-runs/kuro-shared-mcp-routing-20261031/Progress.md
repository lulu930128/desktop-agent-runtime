# 本輪結果

本頁保留公開驗收摘要。原始探針收據與任務 patch 只留本機。

Source Ready；Tests PASS；isolated native MCP 驗證 PASS；LLM E2E UNVERIFIED；正式 Qt runtime 未換版／未重啟。

## 根因與局部修正

- 正式 `Open-LLM-VTuber/logs/debug_2026-10-31.log:1720-1722`：`2026-10-31 13:09:26.989` 為 `Tool router selected no tools: No tool category matched this turn.`，隨即 `Starting simple chat completion.`。這輪沒有 tool call 或 permission-denied 事件；先前另一輪的 `additionalProperties` 是獨立問題。
- catalog 與 intent helper 補 US 市場語詞，保留 OMI-first 與既有 web enrichment。沒有把「昨天」或「收盤」單獨列成市場意圖。
- 三個舊 Node command 的 `normal-direct-bearer-20261023` 路徑實際不存在。改為已執行驗證的 `C:\Program Files\nodejs\node.exe`，版本 `v24.14.1`，不依賴 Qt PATH。
- Listening 編譯後 `dist/src/config.js:15` 使用 `env.LISTENING_TRAINER_BASE_URL ?? "http://127.0.0.1:8765"`；`index.js` 直接呼叫 `loadConfig()`，TrainerClient 使用其 `trainerBaseUrl`。Kuro 明確傳入 `http://127.0.0.1:18811`，共用正式 Trainer，沒有啟動服務。
- 市場 route 無工具時直接回覆未查詢；候選工具已暴露但模型沒有 call 時，不串流或存入無證據的市場結論／拒絕。真正 executor 狀態保持原樣；已嘗試但缺少 final result 時說明尚無有效市場證據。
- `_add_message` 維持本輪 preimage 的 `display_lane_text(text_content)`，未納入 `strip_control_prefix` 增量。沒有修改 TTS 或 Qt。

## 驗證證據

歷史探針摘要收據為`NativeProbe.json`（僅本機）。它保留 identity/digest、參數欄位與型別、狀態、receipt id；沒有 raw arguments、prompt、完整 schema/reply 或詳細 evidence。舊大份收據已原地改寫；Listening 單獨重查後併入摘要，自己的中間收據已移除。

| 原生工具 | discovery 可見／shared 全量 | readonly 結果 |
| --- | --- | --- |
| Japanese Study | complete=true；10／34 | `study_get_summary` succeeded、ok=true |
| English Study | complete=true；10／17 | `english_get_summary` succeeded、ok=true |
| Listening Audio | complete=true；3／7 | URL 修正後 `listening_health` succeeded、ok=true、listening-trainer-v1 |
| OMI Search | complete=true；15／46 | exact 原句 route 首選 `omi_ask`，canonical schema/policy 允許，cache-only succeeded、ok=true |

- shared 全量含未授權工具；Kuro 只暴露既有 allowlist。未擴大 policy。
- OMI 首次請求 target 的 market 為 `us`，正式 response canonical target 為 `{type: market, market: US}`，核對成功。依 reviewer 修正後，探針一律送正式大寫 `US`；沒有為此重跑已成功的 OMI。摘要缺少獨立 freshness 欄位，保留 UNVERIFIED；不把成功回傳等同完整、最新市場證據。
- 第一批 targeted suite **40/40 PASS**：market routing、no-tool truth、既有 argument diagnostics、conversation MCP、OMI/tool policy。
- 後續只重跑受 agent 修改影響的 truth suite，最終 **8/8 PASS**；包含 OpenAI/Claude 無呼叫、過往假拒絕、候選工具未被呼叫、disabled/unsupported、真實 schema/policy/MCP 失敗，以及缺 final result。合計 44 個不同 test methods；不是 48 個不同測試。
- `tool_schema.py`、`tool_executor.py`、`test_tool_argument_diagnostics.py` 與本輪 preimages SHA256 一致；前一輪補丁未被覆蓋。
- 四個 shared adapter entrypoint hashes 前後一致。既有 local web/mail/history、Memory Core、PAOS、Workspace 接線與 allowlist 均保留。
- 受影響 Python 的 syntax compile、JSON/UTF-8 讀回、task-only whitespace check 與 scoped `git diff --check` 全部 PASS。收據已檢查不含原句 prompt、raw arguments、完整 schema/reply 或 detailed evidence；僅保留一份 JSON 摘要。

重現命令（repo root；`PYTHONPATH` 包含 `Open-LLM-VTuber/src`、`Open-LLM-VTuber` 與 repo root）：

```powershell
.\envs\kuro-llm310\python.exe -B -m unittest discover -s Open-LLM-VTuber/tests -p test_no_tool_query_truth.py -v
.\envs\kuro-llm310\python.exe -B Open-LLM-VTuber/tests/verify_shared_mcp_routing.py --only listening-audio --output <new-receipt-path>
```

本輪 first suite patterns：`test_tool_catalog_market_routing.py`、`test_no_tool_query_truth.py`、`test_tool_argument_diagnostics.py`、`test_conversation_mcp.py`、`test_tool_policy_omi.py`、`test_mcp_m0_policy.py`。`--with-llm` 是明確 opt-in；本輪已失敗的 API 不再重試。

## 尚未通過的 gate

- LLM 探針實際只送 **1** 個 `gpt-5-mini` 請求，SDK `max_retries=0`。首次沿用 AsyncLLM 預設占位 organization/project，wrapper 回傳通用 APIError、未提供 status/code，沒有產生 tool call。這是探針限制，不能據此判定 API 本身不可用；探針參數已修正為 None，但依禁止重試限制未再呼叫。
- 因此真模型參數生成與前一輪 root `additionalProperties` Defect 仍為 **UNVERIFIED**，沒有宣稱已修好。canonical schema、policy、native executor 的固定參數探針成功是獨立證據。
- 正式歷史 loaded identity：`launcher_logs/launcher-qt/2026_10/31/launcher.combined.log` 記錄 13:08:37 使用 `envs/kuro-llm310/python.exe .\run_server.py`；對應 `13-08-36_kuro_01/llm.combined.log:54` 為 PID **70820**。正式 debug log 13:08:59.710 載入 **52** tools。
- `13:35:14 +08:00` 唯讀 live 快照沒有找到 `launcher_qt.py`／`run_server.py` Python process，23456／23567／23569 也未見 listener。原因未判定；不能以磁碟 source pin 或歷史 PID 冒充目前 loaded identity。該 gate 保留 **UNVERIFIED**。本輪沒有中斷、換版或啟停正式桌寵。
- 沒有 commit／push。task-only patch 以本輪 preimages 為基準，與 inherited WIP 分開；見 `TaskOnly.diff`（僅本機）。`mcp_servers.json` 是既有 gitignored 本機設定，patch 仍明確列出它。

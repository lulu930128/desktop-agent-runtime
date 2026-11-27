# Kuro OMI arguments 修正與驗收

本頁公開歷史驗收摘要與 [runtime 觀察摘要](RuntimeReceipt.json)。兩筆原始 live 收據及任務 patch 只留本機。

本輪 Source PASS、定點測試 63/63 PASS、真實 gpt-5-mini → 原生 Kuro Agent／ToolManager／ToolExecutor → 共用正式 OMI MCP 的 isolated E2E PASS。正式 Qt／Conversation Runtime 未執行、未 reload，RUNTIME UNVERIFIED；不是產品封版。

## 修前與修後

| 現場缺陷 | 修前 | 本輪修正與證據 |
| --- | --- | --- |
| 15:28:40 `argument_policy` | 原生 schema 宣告 external fetch budget 0..8、default 3，Kuro Policy 上限 0。 | Adapter 只對 `omi_ask` 投影既有 Policy 的 enum、numeric maximum 與 default；max_external_fetches 明確為 maximum=0、enum=[0]、default=0。Executor 對省略欄位補同一份有效預設。明確傳入超額仍拒絕並提供允許範圍，沒有偷偷放寬 Policy 或改寫超額。成功 live call 生成 0，沒有 blocked。 |
| 15:28:51 `invalid_arguments` | debug log line 5266：`$/market additionalProperties=false`；`market` 不可在 `omi_ask` 根層。 | descriptor 明示 `target.type=market`、`target.market`；僅對無歧義的已知根層 market 搬移到 target，保留其他欄位再驗 canonical schema。衝突 target、非 market target、非字串及未知欄位仍拒絕。成功 live call 一次生成合法 target.market，原始 arguments 已通過 canonical/provider validation。 |

單點落差在 `ToolAdapter.format_tools_for_api`：舊版只投影 provider JSON Schema profile，沒有納入 Kuro 執行 Policy。現在保留 MCP `input_schema` 與 canonical digest，另產生符合 Policy 的 provider schema 與獨立 digest。沒有修改 OMI backend、正式 MCP contract、`tool_policy.json`、ToolManager／Catalog 或其他工具設定。

Canonical schema digest 修前、正式 discovery、成功 E2E 皆為：

`7687a011c6b484df34f5ca4c8b4d6d432ab4bb8530d10ffcd617bf775b26bbc6`

Provider schema digest：`056c7ce9a6dee147c4ca60eb758ec7de2449c3ed5498b27bfa2db9151da16b4d`。MCP transport 仍使用 canonical `expected_schema_digest`；schema validation 與根層 `additionalProperties:false` 保留。

## 真實鏈路收據

- `LiveReceipt1.json`（僅本機）：第一筆 gpt-5-mini 自然選 `omi_read_market_overview`，探針在 MCP 發送前停止。**HARNESS ERROR**：當時錯用 `omi_ask` schema 驗證 helper，收據中的 schema FAIL 不能當作產品缺陷。正式 adapter `server.py:897` 使用 `_shortcut_input_schema` 明確宣告 helper 自己的根層 market；它是通用 shortcut、預設 TW，不能據此判定 TW-only。本輪未修改它。探針已改為檢查實際選中工具的 schema。
- 第一筆不是 API/model error，也沒有被計為成功。其後只強化既有 `omi_ask` descriptor 的首選說明，沒有使用 tool_choice，也沒有移除其他候選工具。
- `LiveReceipt2.json`（僅本機）：同一 exact 問句，UTF-8 code points 已核對，market intent=true。正式 ServiceContext 產生 14,901 字元分層 prompt，使用正式 kuro_01 persona、project/tool/runtime contracts，以及失敗原句之前的 4 則歷史訊息；全文與 arguments 都未保存到收據。
- 原生 AgentFactory／BasicMemoryAgent 工具迴圈，自然選 alias `omi-search__omi_ask_bd15278fafcf622c4a96`，canonical `omi-search::omi_ask`。六個正式 OMI route candidates 保留。
- 模型原始 arguments：provider PASS、canonical PASS；補缺省值後 canonical PASS、Policy allowed=true；cache_only=true、no_refresh=true、zero_external_fetches=true。
- 真正共用入口 `C:\GPT_MCPtool\OMI_search\server.py`，執行 id `call_FjJDdiHxb1zEZiGNK9SMuDv3`；2026-10-31 15:59:02–15:59:05 +08:00。ToolExecutor `completed`、MCP `succeeded`、`is_error:false`、reason_code 空、`ok:true`、`request_status:completed`、target.market=`US`；實際回傳 40,467 bytes，來源日期包含 `2026-10-30`。
- 第二筆 replay 的後續模型 completion 已收到，991 字元，回覆涉及美股與資料缺漏；收據僅保留主題詞與摘要，沒有原始私人內容。
- 合計 **3 次真實 gpt-5-mini API**（第一筆選 helper；第二筆選 ask；第三筆整理實際結果），SDK max_retries=0，沒有自動重試失敗。**1 次 MCP 業務呼叫**，無 provider refresh、OMI restart 或 DB 修改。
- `policy_allowed:true` 旁的 `reason_code:argument_policy` 是既有 ToolPolicyDecision 成功預設字串，不是 blocked/error；實際終態以 allowed、ToolExecutor status 與 MCP reason_code 為準。

## 驗證與 WIP

[Checks.json](Checks.json) 記錄八個 test patterns：新 OMI effective arguments 12、argument diagnostics 12、OMI Policy 4、M0 Policy 5、market routing 9、M0 schema 7、conversation MCP 6、no-tool truth 8，共 **63/63 PASS**。涵蓋合法 US/cache-only、超額預算拒絕及修正回饋、受控預設、known market alias、衝突／未知欄位、刷新／寫入拒絕、canonical digest／transport pin、其他工具 descriptor 不變，以及無市場意圖不誤路由。

修前基線另外跑到 `test_mcp_m0_omi_path.py` 的 1 個既有 fixture error：它傳 `None` 給目前需要 input.metadata 的 agent.chat。該次共 31 tests，30 PASS／1 ERROR，發生在本輪 source edit 前。它未包含在 63 個 PASS 中，本輪未修改該檔或相關 speech WIP。

- 五個任務程式檔 syntax compile PASS；scoped `git diff --check` PASS。
- `TaskOnly.diff`（僅本機） 以本輪三個 dirty source preimages 為基準，僅含下列五檔任務增量；不以 HEAD diff 冒充本輪改動。原始 preimages 位於 ignored `.tmp/omi-arguments-20261031/preimages/`。
- branch 仍是 main；HEAD `c2b3e64c27caaec8c2cba5b213444ddce0d79e03` 與 index bytes 未變。未 stage、commit、push，未混入 history feature branch。未修改無關 WIP。
- 成功 replay 載入的三個 runtime source hashes 與最終檔案完全相同，見 Checks.json 的 `live_loaded_sources_match:true`。

任務程式檔：

1. `Open-LLM-VTuber/src/open_llm_vtuber/mcpp/tool_adapter.py`
2. `Open-LLM-VTuber/src/open_llm_vtuber/mcpp/tool_policy_manager.py`
3. `Open-LLM-VTuber/src/open_llm_vtuber/mcpp/tool_executor.py`
4. `Open-LLM-VTuber/tests/test_omi_effective_arguments.py`
5. `Open-LLM-VTuber/tests/verify_omi_effective_arguments.py`

重現命令（repo root；真實探針會消耗 API，必須使用新的 receipt 路徑並另計授權總額）：

```powershell
$env:PYTHONPATH = "$PWD\Open-LLM-VTuber\src;$PWD\Open-LLM-VTuber;$PWD"
.\envs\kuro-llm310\python.exe -B -m unittest discover -s Open-LLM-VTuber/tests -p test_omi_effective_arguments.py -v
.\envs\kuro-llm310\python.exe -B Open-LLM-VTuber/tests/verify_omi_effective_arguments.py --live --max-requests 2 --output <new-receipt-path>
```

## 未通過的表面與必要下一步

[RuntimeReceipt.json](RuntimeReceipt.json)：16:01:55 +08:00 唯讀快照沒有 launcher_qt.py／run_server.py Python process，也沒有 23456／23567／23569 listener。正式 loaded identity **UNVERIFIED**；沒有可以核對 idle 的 live owner，也沒有執行 reload／restart。收據中的 loaded_probe PID、executable 與 source hashes 只證明 isolated Python replay，不能冒充 Qt 正式載入。

OMI 回傳仍有既有資料限制：`news.events` incompatible／unsupported、部分 trust missing／blocked；本輪收據的指定數值欄位計數為 0，沒有驗證完整美股指數收盤數字。成功只證明真實 US cache-only 工具鏈與實際來源結果已通，不能宣稱行情覆蓋完整或可交易。此處沒有新增 backend 修復。

下一個必要步驟是透過既有正常 Launcher 啟動正式 Kuro，核對新的 loaded identity，再由 Qt 送出相同原句完成桌寵實機驗收；本輪依使用者要求不啟動、不重啟。baseline fixture error 與 OMI 資料覆蓋限制另列，沒有擴張本輪任務。

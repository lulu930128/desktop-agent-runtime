# Memory Core／PAOS 受控 HTTP MCP 接入

## 範圍與所有權

沿用唯一 ServerRegistry → MCPClient → ToolAdapter／ToolManager → ToolExecutor → ToolPolicy／ToolCatalog。
Kuro Conversation Runtime 管工具路由與執行政策；Memory Core 管外部正式記憶；PAOS 管帳本與 read-model；Launcher／Qt 管生命週期與設定呈現。
角色記憶、History、Core Today 維持各自 owner，不與外部 Memory Core 混合、不自動寫入。

只增加 `streamable_http`；既有八個 STDIO server 與 60 項設定保留。固定 endpoint 為
`http://127.0.0.1:18818/mcp` 與 `http://127.0.0.1:18876/mcp/`。
無 proxy、redirect、自訂 headers／auth、任意 URL、第二套 executor、REST 捷徑或新增正式服務。
不安裝依賴、不讀 `.env`／token／DB、不改外部專案、不重啟、不 commit／push。

## 計畫與停止條件

1. 讀規則、產品方向、上一輪收據並保存 WIP hash；確認已安裝 SDK 公開介面。
2. 僅作 live MCP initialization／tools/list metadata discovery；auth／不相容時記錄阻擋，不找 token 或修改來源。
3. 最小 transport 分支、精確白名單與唯讀 guard；同步 registry／角色／policy／catalog／中文 Settings metadata。
4. 以合成 HTTP MCP peer 驗 canonical／alias／schema／output／annotation／timeout／redirect／禁用；跑相關 regression。
5. 既有 signed Qt owner 顯示 10 群／75 開關並在合成 policy 上驗 confirmation／CAS／readback；保全與交付。

有任一 schema／policy／保全失敗，先局部修正，不降低 guard。正式資料與 provider 測試本輪禁止。

## 已確認證據

- 已安裝 Python MCP SDK **1.15.0** 原生支援 `mcp.client.streamable_http.streamablehttp_client`，公開介面提供 `httpx_client_factory`、timeout、SSE read timeout、terminate_on_close。
- [LiveMetadata.json](LiveMetadata.json)：Memory Core MCP 初始化名 `memory-core-mcp`，29 項 metadata；PAOS 初始化名 `Personal Asset OS`，7 項 metadata。
- 發送 method 僅 initialize／notifications/initialized／tools/list／GET SSE。正式業務 `tools/call=0`；未呼叫 health、memory search／fetch 或資產查詢。
- Memory Core 限指定 8 項；其餘 21 項即使 annotation 是 readOnlyHint=true，仍不能進 Kuro 工具集。PAOS 限指定 7 項。
- live metadata 不證明正式 backend token scopes、資料可用性、財務 freshness 或現役 Kuro 採用；本輪不讀取或調整 token scope。
- [Baseline.json](Baseline.json) 保存 1386 個 Kuro 基線檔案、110 個外部 Python source、95 個既有 bundle 檔案 hash。preimages／測試 log 位於既有 devtools `.runtime/kuro-http-mcp-20261024/`。

## 驗證進度

**Program Source／Registry／Policy／Catalog／isolated HTTP／isolated native Qt PASS；live MCP metadata PASS；現役 Kuro adoption PENDING；正式資料查詢 NOT_CALLED。**

| 驗證面 | 結果與收據 |
| --- | --- |
| 正規 Kuro HTTP client live discovery | 兩個固定 endpoint 都通過原 Registry／MCPClient，完整 schema 與 digest 見 [KuroLiveMetadata.json](KuroLiveMetadata.json)。僅 metadata，無正式 tools/call。 |
| 15 個允許工具 | 每項 canonical ID 與 provider alias 各派送一次，共 30 次合成 HTTP tools/call，逐項驗 wire name、參數、原 input/output schema 與 readOnlyHint。 |
| 拒絕路徑 | 135 次 Executor 拒絕，另有 MCPClient 直接拒絕；含 Memory Core 全部 21 項非白名單、兩來源虛構 admin／trade／reconcile／backup／restore／refresh、每項 disabled toggle。 |
| transport／schema | 37 個不合法 URL／設定案例；redirect、401、503、錯誤 server identity、readOnlyHint 移除／改 false、destructiveHint=true、input/output digest 變更、無效 output 均 fail closed。 |
| timeout | 已完成初始化後，合成工具 handler 延遲引發有界 timeout；實際送出恰好 1 次、不 retry，保留 may_have_executed，見 [TimeoutVerification.json](TimeoutVerification.json)。 |
| STDIO 相容性 | 同一 MCPClient 同時管理 8 個真 STDIO 合成 peer 與 2 個 HTTP peer；HTTP 失敗與成功之後，8 個 STDIO 查詢仍成功，aclose 通過。 |
| Python regression | [PythonVerification.json](PythonVerification.json)：110/110 PASS，包含前輪完整 targeted module 清單；最後 metadata 順序與額外拒絕案例調整後，[FinalTargeted.json](FinalTargeted.json) 28/28 PASS；timeout 強化另 1/1 PASS。 |
| Native Qt Settings | [NativeQt.json](NativeQt.json)：186/186 PASS，10 群／75 toggles、122 次真 native dialog（合成自動回答，全部預設 No）、停用／恢復、保存／UI readback；CAS／stale-digest 拒絕亦由既有 Python settings tests 驗證。 |
| Frontend／signed bundle | JS／builder／pin 未改；保留 `1cf2b5951a7a27ee508b185bcfa3d08e353b8e4cae86d76e9b7e6ad3de576ea0`，另程序 VerifiedOwnerBundle.load 驗簽成功。未跑無必要的 Node build。 |
| 保全與靜態 | [FinalVerification.json](FinalVerification.json)：1386 基線中 1373 byte-exact，13 個指定既有接觸點更新；110 個外部 source 與 95 個既有 bundle 檔案全數 hash 相同。10 個 Python 檔 syntax、UTF-8／JSON 讀回與 git diff --check PASS。 |

原 8 servers／60 tools 的設定、policy、catalog category、中文 CATALOG metadata 與順序逐項 hash 比對不變，見 [OriginalInventory.json](OriginalInventory.json)。最終 73 項 read_only、2 項 Mail confirm；confirm 仍封鎖。
完整 native fixture 截圖、log 與 Result 位於 `.tmp/kuro-http-mcp-20261024-qt-final/`；`tools-folded.png` 已目視檢查，新增群組可沿原頁面捲動查看。

初次測試的兩個路由失敗（泛用 memory token 擠掉集合工具、fixture 使用不屬既有 History keywords 的查詢）已以新來源精確關鍵字與既有 History 查詢修正。
初次 Qt 檢查發現新增 CATALOG 插在最前方，改變原第一項並使 fixture 重複切換；已將 15 項追加於原 60 項之後，保留原順序並新增順序回歸。初始失敗 log／Result 保留，沒有降低驗證標準。

正式 Launcher 生成的 `conf.launcher_runtime.yaml` hash 未改；角色合併的正式 build_runtime_conf 已由隔離測試驗證為 10 servers，正常啟動時才會採用。未重啟現役 Kuro／Memory Core／PAOS；未啟動額外正式服務，沒有正式記憶／資產／Broker／FX／secret 讀寫。

## Reviewer 交接與採用限制

本輪既有檔案接觸面：`mcpp/{types,server_registry,mcp_client,tool_adapter,tool_policy_manager,tool_catalog_manager}.py`；
`mcp_servers.json`、`characters/kuro.yaml`、`tool_policy.json`、`tool_catalog.json`；
`kuro_launcher/tool_policy_settings.py`、project `tool_prompt.txt`、`tests/g2_tools_today_surface.py`。
新增 `tests/test_http_mcp.py` 與 `tests/verify_http_mcp_metadata.py`，以及本交接文件與驗證收據。
`mcp_servers.json`／角色 YAML 仍為 ignored 本機設定，未強制加入 Git。ToolExecutor 本輪 byte-exact。

請以本輪 preimages／Baseline 區分先前 WIP 與本次增量，再 review transport pin／白名單／無 credential 路徑。
所有 15 項只有 schema 與合成 handler acceptance；沒有宣稱正式記憶或財務資料已可讀，也沒有查核來源 token scope。
現役採用須待使用者日後正常啟動；本輪不代為執行。若要暫停新來源，既有 Settings 可逐項停用並保留原 mode；不需改外部 owner 或回退 signed bundle。
沒有 commit／push、依賴安裝、installed release 變更或外部專案寫入。

## 重現方式

在 repo root 使用現有 `envs/kuro-llm310/python.exe -B`，`PYTHONDONTWRITEBYTECODE=1`；
`PYTHONPATH` 包含 repo root、tests、Open-LLM-VTuber、Open-LLM-VTuber/src、Open-LLM-VTuber/tests。

```powershell
.\envs\kuro-llm310\python.exe -B -m unittest test_http_mcp -v
.\envs\kuro-llm310\python.exe -B -m unittest test_g2_tool_settings test_tool_catalog_market_routing test_project_workspace_cutover
.\envs\kuro-llm310\python.exe -B Open-LLM-VTuber/tests/verify_http_mcp_metadata.py --through-kuro --output docs/agent-runs/kuro-http-mcp-20261024/LiveMetadataRepeat.json
.\envs\kuro-llm310\python.exe -B tests/g2_tools_today_surface.py --refinement --banner-regression --bundle-receipt devtools/original-git-web-host-20261010/.runtime/kuro-conversation-mcp-20261024-build.json --output C:\project\desktop-agent-runtime\.tmp\kuro-http-mcp-repeat
```

第三個命令為選擇性 metadata-only live probe，要求新收據路徑，絕不發出 tools/call。第四個是隔離 native Qt fixture，要求新的 repo `.tmp` 目錄，僅修改合成 policy。

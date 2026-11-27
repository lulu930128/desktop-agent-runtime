# 執行進度

本頁保留公開摘要及隔離 stdio 收據。原始 discovery 與基線只留本機。

狀態：**Source／Config／Policy／STDIO／Schema／Signed bundle／Isolated Qt PASS；現役 Runtime adoption PENDING；實際桌面操作 UNVERIFIED**。

## 正式接線

- 8 個正式服務：`kuro-web`、`kuro-filesystem`、`project-workspace`、`omi-search`、`japanese-study`、`english-study`、`listening-audio`、`kuro-mail`。
- 60 項政策／Settings CATALOG：原 Web 5、history 1、Project Workspace 7、Mail 9，加 OMI 15、日文 10、英文 10、聽力 3。Mail 原 confirm 權限不變。
- `mcp_servers.json` 與 `characters/kuro.yaml` 是既有 ignored 本機設定，已實體更新；policy／catalog／中文 metadata 已同步。未強制加入 Git。
- 保留唯一 ServerRegistry／MCPClient／ToolAdapter／ToolExecutor／ToolPolicy／ToolCatalog。Study／Listening 同時要求明確 allowlist 與 discovery 的 readOnlyHint=true，annotation 消失或變成寫入時 fail closed。
- `omi-market` 從正式 registry、角色、policy、catalog／candidates 移除；Registry 硬拒絕舊 server，Policy 硬拒絕舊 canonical owner。LEGACY_OWNERS 只保留歷史歸屬，沒有 silent remap。
- 移除 BasicMemoryAgent 自動 preflight／stream／fallback；market_preflight 僅保留歷史 evidence 呈現，沒有 HTTP、credential、request builder 或 autorun。新 `omi-search::omi_ask` 的 evidence 經原 Executor／history consumer，沒有第二套分析管線。
- OMI caller 使用正規 question／target／mode=data_only；僅接受 refresh_if_missing=false 或缺省，不接受舊 trust flags，即使傳 false 也拒絕。max_external_fetches 上限為 0，其他原 bounded budget 保留。
- Catalog 新增各學習子集與查詢意圖排序；完整 OMI 工具數增加後仍保留明確新聞需求的 Web enrichment 名額，不自動執行或繞過政策。

## 驗證

| 項目 | 結果 |
| --- | --- |
| 真 STDIO 完整 discovery | OMI 20、日文 34、英文 17、聽力 7；新 allowlist 38 項 input/output schema 全部可投影 |
| 真 STDIO + 合成 backend dispatch | 31 次成功查詢：OMI 8 次／7 種工具，學習／聽力 23 種工具全覆蓋 |
| 負向檢查 | 484 次 Executor 拒絕，另有全部未 allowlist 工具的 MCPClient 拒絕；含 canonical/provider alias、舊 OMI、寫入/UI、refresh=true、舊參數、所有新增工具 disabled |
| v4 payload | 原始 question／target 保留；adapter 固定 caller_profile=omi_search，allow_llm=false、allow_write=false、allow_external_fetch=false；唯一 POST path 為合成 `/api/ai/ask` |
| Source offline | 日文／英文／聽力 3 個合成 503 保持錯誤，不冒充空資料 |
| Python targeted regression | 99/99 PASS；最後擴充完整 inventory 路由後，相關 12/12 PASS |
| Frontend／Settings／banner／refinement | Node 30/30 PASS；既有 TypeScript `tsc --noEmit` PASS |
| 隔離 Qt + 新 signed bundle | 156/156 PASS；92 次 native confirmation，預設 No；新增 38 工具與原 Workspace 7 工具各自停用／恢復，CAS／保存／GET/UI readback 通過 |
| 原本地來源 inventory | Web 5、history 1、Mail 9 schema PASS，3 次 fake dispatch；移除舊 OMI Python module import |
| 外部成品保全 | 37 個 adapter／dist／snapshot 檔案前後 hash 一致；無正式 provider／LLM／私人資料查詢 |

收據：`Discovery.json`（僅本機）、[StdioAcceptanceFinal.json](StdioAcceptanceFinal.json)、`Baseline.json`（僅本機）、[Inventory.md](Inventory.md)。初次 fixture outputSchema 與 discovery GET 計數假設失敗已修正；中文 category keywords 經 PowerShell 管線變成問號，已用明確 UTF-8／Unicode 修正並通過中文路由與 native 畫面驗證。失敗日志保留，沒有降低 schema／policy guard。

最後保全結果見 [FinalVerification.json](FinalVerification.json)：1374 個基線檔案中 1345 個 byte-exact，29 個指定接觸點更新；先前 36 個 WIP 檔中 23 個未動，13 個本輪必要接觸點保留原成果並更新契約。原非 OMI policy／registry／catalog 內容逐項比對不變，原 bundle 88 檔全數不變。25 個 Python 檔案 syntax compile、UTF-8 讀回與 `git diff --check` 通過。

## Signed UI 與保全

- 新 fingerprint：`1cf2b5951a7a27ee508b185bcfa3d08e353b8e4cae86d76e9b7e6ad3de576ea0`。
- Manifest SHA-256：`6181906155af08f61c3a7d3ad80c764772245200129462d92855e039dba9f7c1`。
- 現有 builder 驗證六份 immutable ORIGINALS 後建立獨立 bundle／Ed25519 簽章；更新 RELEASE_PIN，另一個 Python 程序直接執行 VerifiedOwnerBundle.load 驗證成功。
- 前版 `7e1c96580ce2584e197733b093c3cc172174ea9d2efb2e1c6ac6b1799ed7feaf` 與全部先前 88 個 bundle 檔案不變。未修改 builder、canonical-model、owner-bootstrap、CSS、tray／Qt app。
- Settings schema 從可信 native Catalog 取得 toolNames／groups，檢驗 inventory 一致性；不再固定舊數量／群組形狀。目視 tools-folded.png 確認 8 群中文與數量正確、無 banner 回歸。
- 基線、preimages、build 與測試 logs 位於 `devtools/original-git-web-host-20261010/.runtime/kuro-conversation-mcp-20261024/`；build receipt 為相鄰 `kuro-conversation-mcp-20261024-build.json`。
- Qt 收據／截圖位於 `.tmp/kuro-conversation-mcp-20261024-qt/Result.json` 與 `tools-folded.png`。

## 採用與回退

未重啟任何現役 Kuro／Core／OMI／Trainer／TTS。生成檔 `conf.launcher_runtime.yaml` 原有舊清單保持不動；下次正常 `QtLauncherController.start_profile → build_runtime_conf` 由角色導出新 8 servers。已測試正式 builder 的來源合併。新 source 的 Registry 會拒絕生成檔中過期的 omi-market；已在記憶體中的舊 runtime 仍屬 **PENDING**，不宣稱熱採用。

安全回退優先透過既有 Settings 停用四個新增服務的各工具，保持舊 OMI 退役，下一次正常啟動採用。若要回退 UI，需成對還原本輪 preimage 的 owner-presentation.ts 與 qt_web_release.py，驗證保留的前版 signed bundle；新 60 項 native Catalog 可被前版動態 UI 呈現。不以刪除 bundle 或重新啟用舊 OMI 作回退。本輪未執行回退。

Memory Core／PAOS 等精確 deferred 原因見 Inventory.md；不要求 token、不建 proxy、不掃私人 DB。沒有 commit／push／deploy／依賴安裝或外部專案修改。

## 重現命令

在 repo root 設定測試程序 `PYTHONPATH` 包含 repo、tests、Open-LLM-VTuber、Open-LLM-VTuber/src、Open-LLM-VTuber/tests，PATH 包含 `C:\work\Git\cmd`。使用現有 `envs/kuro-llm310/python.exe -B`。所有 output 必須使用新檔名／新目錄。

```powershell
.\envs\kuro-llm310\python.exe -B -m unittest test_conversation_mcp test_tool_policy_omi test_tool_catalog_market_routing test_project_workspace_cutover test_g2_tool_settings test_market_preflight test_mcp_m0_omi_path test_mcp_m0_consumers test_mcp_m0_policy test_mcp_m0_schema test_mcp_m0_identity test_mcp_m0_discovery test_mcp_m0_integration test_qt_web_w10 test_qt_web_w8.W8IconTrayTests test_qt_web_window_chrome.ChromeWindowTests test_qt_web_window_chrome.GestureProtocolTests
node --test tests/g2_tools_today_frontend.test.cjs tests/qt_web_frontend.test.cjs tests/kuro_ui_refinement.test.cjs
node pet-electron/node_modules/typescript/bin/tsc --project devtools/original-git-web-host-20261010/frontend/tsconfig.json --noEmit
.\envs\kuro-llm310\python.exe -B Open-LLM-VTuber/tests/verify_conversation_mcp.py --output docs/agent-runs/kuro-conversation-mcp-20261024/DiscoveryRepeat.json
.\envs\kuro-llm310\python.exe -B Open-LLM-VTuber/tests/verify_conversation_mcp_acceptance.py --output docs/agent-runs/kuro-conversation-mcp-20261024/StdioRepeat.json
.\envs\kuro-llm310\python.exe -B tests/g2_tools_today_surface.py --refinement --banner-regression --bundle-receipt devtools/original-git-web-host-20261010/.runtime/kuro-conversation-mcp-20261024-build.json --output C:\project\desktop-agent-runtime\.tmp\kuro-conversation-mcp-repeat
```

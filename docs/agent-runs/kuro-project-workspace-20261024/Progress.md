# Kuro Project Workspace 接線交付

公開證據包括獨立複查與隔離驗收收據。原始工作樹基線只留本機。

狀態：**Source／Config／Policy／Schema／Bundle／Isolated Qt PASS；現役 Runtime Pending；Native user session UNVERIFIED**。

## 正式接線

- `Open-LLM-VTuber/mcp_servers.json` 直接啟動 `node C:\GPT_MCPtool\project_reading\dist\src\index.js`，server id 為 `project-workspace`。沿用既有 ServerRegistry、MCPClient、ToolAdapter、ToolExecutor。
- 只允許 `workspace_info`、`list_dir`、`find_files`、`search_text`、`read_file`、`read_files`、`project_context`。此次採最小 7 項，不加入選配 `git_status_summary`。
- roots 明確為 `projects=C:\project;mcp_tools=C:\GPT_MCPtool;work=C:\work`。未加入 data、desktop、codex 或 home roots。
- 未傳 `WORKSPACE_MCP_WRITE_POLICY`；已在父程序放入合成 write-policy 設定驗證 SDK 不繼承。正式 STDIO `workspace_info` 證明 `mode=read-only`、`writeCapabilities.enabled=false`、`reason=not_configured`，原 path guard／deny／limits 生效。
- `kuro-filesystem` 的 allowlist 僅有 `search_past_conversations`。舊四工具移除 FastMCP decorator；原 history 函式與本輪前 preimage 位元一致，原 canonical identity、conf_uid、exclude_history_uid、include_current_history=false 及上限保留。
- 舊檔案 identity 保留在 LEGACY_OWNERS 作歷史 owner pin，不重定向；已從 policy、catalog、Settings CATALOG、專案 tool prompt 及路由 scoring 移除。新工具使用正式 root／relative path／project／files[].path schema；批次路徑逐項套用 Kuro 原 deny 規則。
- Settings 共 24 項、5 個服務群組。保留 enabled-only 寫入、native confirmation、CAS、原 mode／constraint 與 GET readback。

## Launcher ownership 與採用界線

角色 `Open-LLM-VTuber/characters/kuro.yaml` 與 registry 順序皆為：
`kuro-web → kuro-filesystem → project-workspace → omi-market → kuro-mail`。

`kuro_launcher.settings.yaml` 指向 `conf.launcher_runtime.yaml`；`qt_controller.py` 的正式啟動流程呼叫 `build_runtime_conf()`，由角色設定合併後交給 `write_runtime_conf()`。targeted test 已驗證新順序可由正式 builder 導出。

本輪未直接重寫生成的 `conf.launcher_runtime.yaml`，目前仍是舊 4 servers；未重啟現役。因此現役已建立的 MCP session／tool snapshot 不屬本輪採用證據，需下次正常啟動後驗證。

`mcp_servers.json`、`characters/kuro.yaml` 與 bundle 是既有 ignored 本機配置／資產；本輪實體修改並驗證，沒有強制加入 Git。

## Signed bundle

- 新 fingerprint：`7e1c96580ce2584e197733b093c3cc172174ea9d2efb2e1c6ac6b1799ed7feaf`。
- Manifest SHA-256：`69b788d0b84d850fa47ba108f1bfee4153b62b5c931fd16b4d9659ac7c825c3f`。
- 實體路徑：`assets/qt-owner/7e1c96580ce2584e197733b093c3cc172174ea9d2efb2e1c6ac6b1799ed7feaf/`。
- 沿用原 `build_owner_bundle.py`、六項 immutable ORIGINALS、Ed25519 新簽章；更新 `qt_web_release.py RELEASE_PIN` 後，主 agent 與獨立 Reviewer 均成功執行 `VerifiedOwnerBundle.load()`。
- 原 `535e20b1…` 及其他舊 bundle 均未改。既有 refinement、banner removal、builder、bootstrap、canonical model 不變。

## 驗證收據

總表：[Validation.json](Validation.json)。正式 STDIO：[StdioFormalReceipt.json](StdioFormalReceipt.json)。
基線：`Baseline.json`（僅本機）。獨立複查：[Review.md](Review.md)。

| 驗證 | 結果 |
| --- | --- |
| 相鄰 Python Config／Policy／Catalog／Schema／identity／discovery／integration／Settings | 52/52 PASS |
| Node frontend／Settings／refinement | 30/30 PASS |
| Qt W10／tray／window chrome／gesture targeted | 30/30 PASS |
| Frontend `tsc --noEmit` | PASS |
| 新 server 真 STDIO discovery／7 種工具讀取 | PASS |
| backend escape／絕對路徑／secret／.git／unknown root／batch／project escape | 7/7 拒絕，未返回 sentinel |
| write／patch／create／delete／command／commit／push／restart | 8/8 不可執行 |
| 舊四工具 canonical／legacy + client 呼叫 | 全部拒絕 |
| history 真 STDIO 空 query + 精確 scope 合成 fixture | PASS；不開啟正式 history／SQLite |
| 正式 roots metadata／write disabled／外部 build hash | PASS；54 build 檔不變 |
| Source inventory | 26 declarations schema + 4 fake dispatch PASS；其中 OMI 現有 11 declarations，與政策可執行的 24 項不同 |
| Isolated Qt 新 pin／工具列表／native cancel／保存讀回／banner／zoom／refinement | 80/80 PASS；16 次確認皆預設 No |
| 7 個新工具各自停用及還原 | 14 次 native 確認／CAS／持久化／UI readback PASS |
| 原 history 函式／六份 ORIGINALS／既有 WIP | PASS；102 基線檔僅 3 個指定接觸點變更，其餘 99 byte-exact |
| 10 個 Python 檔 syntax compile／UTF-8／git diff --check | PASS |

日志與 preimages：`devtools/original-git-web-host-20261010/.runtime/kuro-project-workspace-20261024/`。
Build receipt：`devtools/original-git-web-host-20261010/.runtime/kuro-project-workspace-20261024-build.json`。
Qt receipt／截圖：`.tmp/kuro-project-workspace-20261024-pass/Result.json`、`tools-folded.png`、`tools.png`。
已目視工具群組截圖：5 群、專案工作區 7/7、過往對話 1/1，中文與 runtime 未驗證提示正常。

保留的首輪失敗記錄：STDIO negative fixture 對「絕對路徑須為相對路徑」錯誤誤期待 outside，已修正測試而非 backend；Node 在新 source 尚未打包前正確拒絕舊 lineage；Qt 原測試固定 2 次確認未計新增 14 次，已改為 derived count；source inventory 原腳本缺少 local_mcp import path，已補足。首輪 PowerShell pipe 編碼造成新增中文問號，已改用 UTF-8／patch 並由 source、中文 UI tests 與實際截圖驗證修正。未以略過安全檢查處理這些失敗。

## 重現命令

在 repo root，使用現有 `envs/kuro-llm310/python.exe`。設定本次程序 `PYTHONPATH` 包含 repo、`tests`、`Open-LLM-VTuber/src`、`Open-LLM-VTuber/tests`，PATH 包含 `C:\work\Git\cmd`。收據輸出需使用新檔名／新目錄。

```powershell
.\envs\kuro-llm310\python.exe -B -m unittest test_project_workspace_cutover test_g2_tool_settings test_mcp_m0_policy test_mcp_m0_schema test_mcp_m0_identity test_mcp_m0_discovery test_mcp_m0_integration test_tool_catalog_market_routing test_tool_policy_omi
node --test tests/g2_tools_today_frontend.test.cjs tests/qt_web_frontend.test.cjs tests/kuro_ui_refinement.test.cjs
node pet-electron/node_modules/typescript/bin/tsc --project devtools/original-git-web-host-20261010/frontend/tsconfig.json --noEmit
.\envs\kuro-llm310\python.exe -B -m unittest test_qt_web_w10 test_qt_web_w8.W8IconTrayTests test_qt_web_window_chrome.ChromeWindowTests test_qt_web_window_chrome.GestureProtocolTests
.\envs\kuro-llm310\python.exe -B Open-LLM-VTuber/tests/verify_project_workspace_cutover.py --output docs/agent-runs/kuro-project-workspace-20261024/StdioRepeat.json
.\envs\kuro-llm310\python.exe -B tests/g2_tools_today_surface.py --refinement --banner-regression --bundle-receipt devtools/original-git-web-host-20261010/.runtime/kuro-project-workspace-20261024-build.json --output C:\project\desktop-agent-runtime\.tmp\kuro-project-workspace-repeat
```

沒有 commit／push、現役 kill／restart、ACL／sandbox 改動，沒有修改 Project Workspace source／installed release，也沒有真實 LLM／provider 呼叫。下一步僅是在使用者下次正常啟動後核對正式 runtime 的 5 servers／24 tools／new bundle；本輪不宣稱此 live gate 已完成。

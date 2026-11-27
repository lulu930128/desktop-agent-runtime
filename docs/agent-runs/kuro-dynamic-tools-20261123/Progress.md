# Kuro 工具系統交付與驗收

本頁公開工具與權限摘要、隔離工作流結果、DOM 摘要和驗證清單。原始 discovery、Workspace 權限回傳、工作流事件、預覽 HTML、截圖與任務 patch 只留本機。

2026-11-23，工作目錄為 `C:\project\desktop-agent-runtime`。此版已完成程式、隔離驗收與 Qt 工具頁預覽。正式桌寵載入及實際雲端模型操作尚未驗證。

## 檢視成果

- 本機工具頁預覽可展開五個服務、操作權限、不可用原因及 42 筆隔離執行事件。預覽使用 Qt 工具頁的正式元件與本次驗收資料，設定控制項停用。歷史 DOM 檢查結果見 [PreviewEvidence.json](PreviewEvidence.json)。
- 本機 task-only patch 與 [逐檔 SHA-256](changed-files.json) 以修改前的工作檔內容為基線，包含既有未追蹤設定的局部修改。已在暫存目錄套用 patch，逐檔比對內容。基線分支為 main，HEAD 為 `c2b3e64c27caaec8c2cba5b213444ddce0d79e03`。
- 回歸結果與歷史收據雜湊見 [驗證清單](validation.json)。

## 工具與權限

| Kuro 使用的來源 | tools/list | 通過 schema、模型可見性與 Kuro 政策 | 其餘項目 |
|---|---:|---:|---|
| Project Workspace，stdio | 53 | 51 | 2 項輸出 schema 無效 |
| Japanese Study，HTTP | 37 | 35 | 2 項僅限 App |
| English Study，HTTP | 17 | 17 | 0 |
| Listening Audio，HTTP | 7 | 7 | 0 |
| OMI Search，HTTP | 63 | 49 | 14 項僅限 App |
| 合計 | 177 | 159 | 18 |

清點時間約為台北時間 15:58。每一列都有工具名稱、來源宣告的操作類型、輸入 schema 雜湊與 Kuro 的判定。可呼叫數量表示通過 discovery 與註冊檢查，實際呼叫仍由服務依當次身分與參數判定。來源未宣告操作類型時保留 `owner_defined`。

Project Workspace 的 `workspace_info` 回報契約 `2026-11-20.1`、`mode=read-only`、`writeCapabilities.enabled=false` 與 `reason=not_configured`。另一個已授權 Codex 連線發現 59 項，其中多出的 6 項為 `create_text_file`、`append_text_file`、`patch_text_file`、`update_json_value`、`make_directory`、`get_write_operation`。Kuro 已支援原 owner 的操作政策環境設定，也已用隔離 grant 驗證編輯。正式 Kuro 程序仍需由操作者提供原 owner 授權給該程序的寫入政策。

`workspace_runtime_status` 與 `mcp_component_diagnostics` 的正式輸出 schema 含重複的 JSON Schema 型別 `["null","null"]`。另外 16 項工具由 owner 標為 `_meta.ui.visibility=["app"]`。逐工具契約片段及錯誤位置留在本機 `inventory.json` 的 `contract_evidence`。

## 執行路徑

OpenAI 與 Claude 的工具回合從 `kuro_discover` 開始，空查詢可列索引，也可按名稱、描述與服務搜尋。模型能在同一輪對話中更新 inventory、載入新選取的 schema，再繼續呼叫。執行沿用原 MCP Client 與 ToolExecutor，在送出前重新核對來源 schema、註冊及權限。已保存的停用設定仍會生效。

Qt 工具頁以該工作階段的 ToolExecutor 回報連線狀態、來源工具數、可呼叫數、權限與結果。權限檔的 revision 與執行中 revision 可分別核對。呼叫事件提供 call ID、工具名、參數數量、結果與原因。可能改變狀態的操作若結果未知，模型會收到使用原識別碼讀回的指示，同一工具回合會攔下參數相同的盲目重送。這項保護未提供跨程序的去重保證，操作的永久收據由原服務管理。

## 隔離工作流

| 服務 | 已執行的操作與讀回 |
|---|---|
| Project Workspace | 在暫存 root 找到 note.txt、讀取原 SHA、帶 operation_id 套用 patch，再經 MCP 與檔案位元組確認 updated。工具結果含前後 SHA 與 diff。 |
| Japanese Study | 讀摘要、預覽、寫入隔離練習，再透過 session ID 自暫存 Hub DB 讀回。 |
| English Study | 讀摘要、預覽，帶預覽的 fingerprint 寫入，再讀回同一 session。 |
| Listening Audio | 建題組、取題、準備音訊、檢查落地 WAV 有影格、提交答案並讀回 completed。使用可重現的 PCM 夾具代替外部發聲引擎。 |
| OMI Search | 由真正的 MCP adapter 讀到 stale，呼叫 omi_ask 並驗證上游收到 allow_external_fetch，再讀到 current。市場 HTTP 回應由隔離夾具提供。 |

兩個模型 provider 的多回合測試使用確定性的模型回應驅動正式迴圈。另一次隔離流程一次載入 9 個工具，下一回合可見 9 個 schema 與搜尋入口。正式金融資料、委託與學習紀錄均未用於寫入測試。

## 前端與正式執行狀態

Qt 原始碼已通過 TypeScript、Vite 隔離 build、前端測試及 Qt WebEngine DOM／截圖檢查。原 owner bundle 流程回傳 `Immutable Git source mismatch: src/work-panel/main.ts`。這個檔案在起始 git status 已有修改，本次保留原狀。15:54 台北時間，23456、23567、23569 均無 listener。尚無正式 release 身分、已載入 Qt 元件或真實模型對話收據。

## 重跑驗證

從 repo 根目錄執行，使用原有環境及已授權的服務。先產生本機 inventory 和工作流收據，再建置預覽。[驗證清單](validation.json) 中的 artifact hashes 是歷史收據的摘要。工作流在新的暫存目錄建立資料，市場來源及語音發聲端由測試提供。

```powershell
$env:PYTHONUTF8 = '1'
$runDir = 'docs/agent-runs/kuro-dynamic-tools-20261123'
$env:KURO_TOOL_POLICY_PATH = (Resolve-Path Open-LLM-VTuber/tool_policy.json).Path
& .\envs\kuro-llm310\python.exe -B "$runDir/verify_workflows.py" --owners C:/GPT_MCPtool --projects C:/project --receipt "$runDir/workflows.json"
& .\envs\kuro-llm310\python.exe -B "$runDir/inspect_inventory.py" | Set-Content -Encoding utf8NoBOM "$runDir/inventory.json"
# 以下兩步會在本機產生預覽、截圖及 preview-check.json。
node "$runDir/build_preview.mjs"
& .\envs\kuro-llm310\python.exe -B "$runDir/verify_preview.py"
```

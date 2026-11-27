# MCP 接入與驗證邊界

所有外部來源只讀程式／建置入口；未讀取 `.env`、credential、私人 DB、正式學習資料或資產資料。測試只啟動短暫 STDIO 子程序與 repo 內合成 loopback fixture；未啟動正式 Hub／Trainer／OMI／TTS。Conversation 查詢與既有 Core Today integration 分開，不新增 poller 或 domain truth。

| 成品 | 結果 | 已驗證 | 尚未驗證／排除 |
| --- | --- | --- | --- |
| OMI Search | `SOURCE_CONFIG_STDIO_PASS` | `.venv/Scripts/python.exe` Python 3.12.3、MCP 2.1.1；原 `server.py` 真 STDIO 完整 20 tools；15 allowlist 全部 schema 可投影；7 種工具、8 次合成查詢，v4 精確 POST payload | 8 個 dashboard／progressive 工具完成 discovery/schema，未執行其業務結果 fixture；正式 backend/auth、provider 與現役 adoption 未驗證 |
| Japanese Study | `SOURCE_CONFIG_STDIO_PASS` | `dist/src/index.js` 存在，完整 34 tools；10 個 readOnlyHint=true 子集全部經 Executor 真 STDIO → mock Hub 執行 | 不查正式 Hub／個人進度；不開放其他 preview、create、set、record、apply、revision 或 lifecycle tools |
| English Study | `SOURCE_CONFIG_STDIO_PASS` | `dist/src/index.js` 存在，完整 17 tools；10 個 readOnlyHint=true 子集全部經 Executor 真 STDIO → mock Hub 執行 | `english_preview_practice_record`、`english_record_practice` 的完整 inputSchema 在既有 projector 回報 `schema_invalid`，均未加入 allowlist；正式 Hub/auth 未驗證 |
| Listening Audio | `SOURCE_CONFIG_STDIO_PASS` | `dist/src/index.js` 存在，完整 7 tools；health、question、attempt result 3 項全部經 Executor 真 STDIO → mock Trainer 執行 | create exam、submit answer、prepare audio、render widget 不開放；不讀取音檔 resource、不合成、不啟停 TTS；正式 Trainer 未驗證 |
| Memory Core | `DEFERRED_TRANSPORT_OR_AUTH` | `src/memory_core/mcp/main.py` 使用 uvicorn／HTTP app；README 宣告 stateless Streamable HTTP，尚無 Kuro adapter；`mcp/settings.py:30` 要求 `client_token`，另有獨立 reviewer token | Kuro MCPClient 僅支援 STDIO，未配置最小權限 API credential。不能用 STDIO 啟動 HTTP main 冒充 MCP；不建立 proxy、不讀 token、不掃 DB |
| Personal Asset OS | `DEFERRED_TRANSPORT_OR_AUTH` | `src/personal_asset_os/app.py:53` 建立 `streamable_http_app`，`:134` mount `/mcp`；資料由 PAOS database/API owner 持有 | 無已驗證原生 STDIO entrypoint；Kuro 缺 HTTP transport／授權邊界。不可 import app（會初始化 DB/migration）或新增 proxy；未驗證或要求任何 token |
| Codex Bridge | `DEFERRED_CONFIRMATION_AND_TRANSPORT` | `package.json` bin/start 指向 `dist/src/http-main.js`；`src/server.ts` 註冊 direct job dispatch 等，另有 PowerShell execution tools | HTTP/MCP Apps 與 task/執行能力；Kuro generic Conversation confirmation queue 尚不存在，`confirm` fail closed。連只讀盤點工具也未混入本輪模型 surface |
| MCP Control Center | `DEFERRED_CONFIRMATION_AND_LIFECYCLE` | README component exact-path lifecycle；`src/WorkspaceLocal.Native.cs:24` 列 `ensure_running`、`repair_connectivity`、`restart_core`、`reload_runtime`、`shutdown_runtime` | 沒有已驗證可直接供 Kuro 使用的唯讀 STDIO entrypoint；權限與 process lifecycle 屬原 owner，不能在 Conversation queue 未完成時對模型開放 |

OMI 明確排除 `omi_restart_backend`、`omi_open_tw_market_dashboard`、`omi_open_tw_workspace`。`omi_read_runtime_status` 與 `omi_read_runtime_operation` 雖是 readOnlyHint=true，但需要專用 `OMI_SEARCH_RUNTIME_CONTROL_TOKEN`；本輪未傳入任何 admin scope，列為 `DEFERRED_AUTH`。

三個 Node adapters 使用當前已存在的 Node v24.14.1 絕對路徑；未安裝／重建外部專案。Kuro Python MCP SDK 1.15.0 與 OMI 的 2.1.1 經真 STDIO handshake/list-tools/call-tools 驗證相容。SDK 子程序預設環境只有 OS 基本路徑等 allowlist；新增 config 不含 token，也不繼承父程序 OMI／Study／OpenAI credentials、NODE_OPTIONS 或 PYTHONPATH。合成 sentinel 與 fixture header 檢查通過。

來源未啟動、401/403、offline 或無資料不得宣稱安裝失敗或零筆進度；已驗證三個學習來源 503 都維持工具錯誤。正式 endpoint/auth 的可用性仍待下次正常啟動後另驗。

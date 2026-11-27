# 共用 MCP 接線與市場查詢事實修正

- 目標：精確原句「可以幫我看看昨天美股的大致狀況嗎」經 ToolManager 選出 `omi-search::omi_ask`；無關的昨天／收盤問題不誤路由。
- 接線：直接使用 `C:\GPT_MCPtool` 既有 Japanese Study、English Study、Listening Audio、OMI entrypoint 與 discovery schema。各 backend 保留 domain ownership。
- 回覆：無 tool call 時不得宣稱已查詢、取得資料或遭權限拒絕；真正 schema、policy、MCP failure 保留原始狀態。
- 驗證：原生 discovery、三個指定 readonly 工具、US cache-only `omi_ask`；最多兩次已授權 `gpt-5-mini` 請求，不重試。
- 限制：只改 Kuro config、light routing、tool/no-tool 回覆與定點測試；不複製 shared business implementation，不新增 server/provider/policy。
- 不進行：Qt 換版／重啟、TTS／GUI 修改、provider refresh、寫入 Study／Memory／PAOS、密鑰變更、commit／push。
- 證據邊界：Source、Tests、isolated native probe、正式 runtime adoption 分別回報；收據只保留必要 metadata。

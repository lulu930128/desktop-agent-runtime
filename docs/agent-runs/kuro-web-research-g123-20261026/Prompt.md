# kuro-web Web Research Enhancement G1～G3

在唯一 `Open-LLM-VTuber/local_mcp/web_tools_server.py` 實作 bounded public-web evidence research。G4 PDF／Playwright 延後。

- 保留五工具 identity、input/output schema、CLI／STDIO、ToolCatalog／ToolPolicy／ToolExecutor 與 Settings enabled/hard read-only policy。
- G1：HTTP 每跳驗證、DNS/connect IP pinning、peer/TLS 驗證、無代理、byte/type/timeout/concurrency/quota 限制，以及 HTML 正文／metadata。
- G2：DDG HTML 為主；失敗或零結果才按 opt-in 使用固定 Brave 官方 API；無 key 不呼叫；固定額度、去重與來源標示。
- G3：引用 URL、provider、來源觀察、正文、original/validated publication time、fetched time、缺漏與衝突；confidence/official 僅 heuristic，recency 僅 query hint；不產生 LLM 結論。
- Domain Owner 仍為 OMI／新聞等系統；本工具提供一次性證據，不建立 polling、service、manager、第二個 server 或 UI 業務邏輯。
- 不讀取實際 secrets、`.env`、私人 DB；不啟動、重啟、停止正式 Kuro 或其他 MCP；不 install/deploy/commit/push，不呼叫 Brave 真實 API。
- 保全開始時 74 個 dirty/untracked WIP。目標 server 原本乾淨；修改前保存 bytes/hash、Git status、index hash 與五工具完整 discovery 快照。

完成標準：在 `envs/kuro-llm310/python.exe` 跑離線負向安全 fixtures、五工具 discovery/mock call、MCP/Router/Policy/Settings regression、syntax/diff 檢查；明確區分 Source 與 Live/Product acceptance。

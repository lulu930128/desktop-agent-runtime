# Kuro 真實 API 驗收

2026-11-23 台北時間。本次沿用原專案與 Kuro 的 OpenAI Responses 實作。真實模型成功自行發現並執行跨服務工具。正式後端已讀回新版 inventory；正式 Qt 工具頁、桌寵對話及五項正式服務的完整業務驗收仍未通過封版條件。

## 真實模型與實際查詢

同一份公開測試檔含隨機收據碼和待查詞，使用者提示只提供檔案路徑。模型先搜尋、載入 Workspace 工具讀檔，再搜尋、載入 English Study 公開詞目工具，依前一步結果查詢。兩次都回報檔案中的收據碼、`study`、命中總數 7，以及第一筆來源 CMU Pronouncing Dictionary。每個 HTTP 回合都保留 request ID、response ID、API 回報模型、effort、時間、工具參數與 schema 雜湊。回傳的工作階段識別碼以雜湊保存。

| Kuro 設定依據 | API 回報模型 | Effort | HTTP 200 且 completed | 時間 | API 回報總 tokens |
|---|---|---|---:|---|---:|
| 正式程序啟動前，最後一次產生的 Kuro 設定 | gpt-6-astra | low | 7 | 16:18:08–16:18:46 | 15,089 |
| 正式 Launcher 啟動後，設定與啟動紀錄相符 | gpt-6-luna | none | 14 | 16:23:35–16:24:17 | 73,445 |

執行使用原 BasicMemoryAgent 的 OpenAI 迴圈、原 SDK、ToolManager、ToolExecutor 與真實 MCP。專用無歷史會話設有只允許指定測試檔與公開詞目查詢的測試條件。觀測程式轉送 SDK 的實際請求與串流，未合成回答。本次未使用 Qt 對話框發送測試。Luna 在取得正確 schema 前多次搜尋，是本次實際消耗的一部分。

[原設定 Responses 收據](responses-081808.json) · [現行設定 Responses 收據](responses-082335.json) · [比對過的工具 schema](responses-schemas.json)

## 正式來源

| Kuro 連線 | 發現／可載入 | 實際結果 |
|---|---:|---|
| Project Workspace | 53／51 | 真實 MCP 讀回驗收檔與收據碼。當前 Kuro 工作階段回報 read-only、write_enabled=false、not_configured。 |
| Japanese Study | 37／35 | 正式 study_get_summary 回傳 ok=true 與 summary。收據保留形狀、雜湊及時間，省略個人學習內容。 |
| English Study | 17／17 | 正式 english_search_reference_entries 回傳 count=1、total=7。 |
| Listening Audio | 7／7 | 正式 Trainer 健康及契約讀取成功。舊題庫公開列出的四個題組以及 owner 的兩個範例，都未在正式 Listening MCP 取得有效題目，來源回 EXAM_NOT_FOUND。正式 MCP 沒有列舉已建題組的工具，音訊資源模板也未提供 list。 |
| OMI Search | 63／49 | 正式代號查詢回傳 2330、台積電、TWSE。freshness 一般讀取與明確 cache_only 讀取均在 Kuro 約 30 秒期限到時。診斷程式僅放寬本次接收等待時間，再用相同 cache_only 參數取得服務於 90.313 秒回傳的 tool_error，未取得 freshness。 |

[正式 MCP 清點及呼叫](live-mcp.json) · [業務讀回](business-readback.json) · [Listening 原服務範例](listening-owner-examples.json) · [OMI 快取限定](omi-cache-readback.json) · [OMI 來源終態](omi-owner-wait.json)

## 寫入與身分

原 Project Workspace 的同一版契約在 Codex connector 回報 operate 且有 6 項寫入相關工具。在 Kuro 正式後端回傳 read-only。Process、User、Machine 三個環境均未發現 Kuro 可沿用的 Workspace 寫入政策或 Workspace HTTP 憑證設定。正式開通需要原 owner 給 Kuro 程序的有效授權。驗收未將其他 client 的身分移植到 Kuro。

四組獨立資料使用真正的 Workspace owner、日英 Hub、Listening Trainer 與 MCP adapter。執行完成 16 次業務操作，並重讀修改後的檔案、日英 session 與 Listening 的已完成作答。資料放在新建暫存目錄，結束後已清除。本輪未產音，未寫入正式學習或金融資料。

[隔離真實寫入收據](isolated-writes.json) · [Codex connector 身分](workspace-connector.json)

## 正式桌寵

初查三個埠無 listener。16:22 重查時正式 LLM、pet 與 Core 已啟動。16:26 對現有工作階段呼叫 /launcher/tool-inventory 成功，五項連線與呼叫數均可讀回，載入的政策 digest 與磁碟相同。正式 Launcher 指定的 Qt bundle 簽章已核驗；其 owner-presentation.ts 與 CSS 的來源雜湊都與新版不同，編譯後的 JavaScript 也缺少新版呼叫紀錄欄位 call_summary。本輪未更換發行版或重啟正式桌寵。

[程序與連線埠](runtime-status.json) · [正式後端與 Qt bundle 讀回](production-readback.json) · [驗收檔案 SHA-256](verification.json)

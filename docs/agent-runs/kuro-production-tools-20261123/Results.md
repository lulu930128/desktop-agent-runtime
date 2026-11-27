# Kuro 日文教師驗收

下文保留歷史驗收摘要及逐檔雜湊。學習原始收據、正式清單、程序快照和任務 patch 只留本機。

2026-11-23，正式桌寵教師閉環尚待驗收。實作與真 API 測試在原 checkout 完成，執行模型取自 Kuro 當時的設定 `gpt-6-luna`，Responses reasoning effort 為 `none`。工程 Job 指定的模型與 Kuro 對話設定是兩個不同欄位。

## 真實學習流程

- **本人正式 Japanese Study Hub，唯讀。** 以獨立 Kuro Agent 程序、正式角色的完整分層提示、原 ToolExecutor 及正式 HTTP MCP 送出「今天做一輪日文」。模型先呼叫 `kuro_discover`，實際讀取 policy 與未加篩選的 context，取得 20 個推薦目標，以及搭配詞、拼寫、が／を、自他動詞等診斷。回覆有五題 N3、固定 session ID 與原題號，沒有附解答。沒有對本人的學習庫提交答案。出題原文、HTTP request ID 與工具事件（本機收據）
- **五題持久測試學習者。** 真實模型先出題，收到第一題後保留其餘四題。第二批作答包含明確跳過。模型批改後自行預覽、提交、讀回同一 session。Hub 記錄三題正確、一題錯誤、一題跳過，得 3/5。原有測試詞庫中沒有相符項目，五個目標保留為 unresolved。三輪完整收據（本機收據）
- **兩題持久測試學習者。** 在獨立原版 Hub 中預置一筆「が／を」診斷，要求第一題練近期助詞弱項。模型讀回 `particle_ga_wo_confusion`，生成對應題目，等候第二題，批改為 1/2。Hub 將第一題的 `particle_ga_wo_confusion` 保存於 target assessment，正式定義版本為 `diagnosis-definitions-v1`。第一題有兩個空格，這次模型以整題錯誤計分。session 為 `jp-20261123t093345z-9519fdee0e2a`，submission 為同 ID 加 `-submission`，source 為 `kuro`。兩個目標仍未對應詞庫。逐輪 Call、Result、題目、批改與原始 Hub 讀回（本機收據）
- 共四個完成的測試 session。逐一關閉後以原 Hub 重開各自的持久資料目錄，依 session ID 用正式 HTTP API 全量讀回並比較。四份內容皆相同，最後一次成功 preview 與 record 的工具參數逐欄相同。測試資料存於本機 task preimage 區，各資料庫相互獨立。跨程序持久化、原答與診斷（僅本機）

診斷過程累計 116 個 HTTP 200 Responses 請求，保留 116 個不同的 request ID。早期樣本包含配置錯誤、原題與測試答案不相干、MCP 的 schema 拒絕，以及預覽成功後模型停住。HTTP 狀態只描述模型端的請求。修正包括讓教師先讀整體學習脈絡、提供 Hub 的 v2 契約與正式診斷目錄，並在遇到 unresolved 目標時依 Hub 的預覽結果保存。[驗證摘要](validation.json)

## 正式桌寵

正式端 `/launcher/tool-inventory` 的可呼叫／發現數為 Workspace 51/53、Japanese 35/37、English 17/17、Listening 7/7、OMI 49/63。五項教師工具都有可執行的 schema。Workspace 仍回 `read-only / write_enabled=false / not_configured`。磁碟新增的是專案內本輪驗收子目錄的授權，三個 roots 的普遍寫入與正式程序的測試檔讀回均未驗證。其他服務沿用前輪業務端讀回，App-only 與 OMI freshness 的 tool_error 仍列為限制。正式 inventory（僅本機） · [前輪業務查核](../kuro-real-api-20261123/Results.md)

Qt 原發行 builder 已產生並驗證簽章，五個資產的新版 fingerprint 是 `1fa9b1646a024b573fabe019e4fd940f0e34962f87db6b46cba52408290f3e2a`，manifest SHA-256 是 `fc759d5a95cfa53b0997e3d57ca68dc1c9d40675be9419d10de7a38b0a38ae9d`。前端仍使用原 work-panel，既有 history WIP 被保存在可重建原位元組的 patch，原 immutable Git source 校驗保持生效。

目前觀察到的 Launcher PID 119856、LLM PID 73172 都早於本輪修改。會話由 qt-primary 獨占，GUI 工具只列出 Kuro Pet Renderer，不能操作其下方的 Qt Tool 視窗。實際新版 Qt 工具頁截圖、正式會話出題到存檔、新 PID 對新版 pin 的功能讀回均待完成。先前的工具頁預覽只供查看版面。程序啟動身分（僅本機） · 既有工具頁預覽（僅本機）

## 變更與回歸

本輪 24 個產品、測試及簽章資產的 task-only patch（僅本機） 已成功套回逐檔 preimage，並與結果作位元組比較。[變更清單與雜湊](change-manifest.json) · 原始基線（僅本機）

原 Agent 透過同一份對話歷史保留開放練習的 snapshot，支援分批作答與歷史切換。課程中的自然日文例句及修正是桌寵 persona 的限定例外。原 ToolExecutor 傳回成功的 Hub session 與 submission 身分，供課程結束與跨輪辨識使用。

教師歷史／工具／Workspace 回歸 12 項通過，Qt W10 共 17 項通過，前端 Node 測試 37 項通過，TypeScript check 與正式 owner build/verify 通過。歷史 W6 套件有兩項仍讀取已移除的舊 Widget 檔，一項仍要求舊建構子字串。保留歷史測試與失敗資訊。[測試與簽章收據](validation.json)

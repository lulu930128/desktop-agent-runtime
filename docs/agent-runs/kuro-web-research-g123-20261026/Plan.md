# 實作與驗證

1. 基線與 owner：讀取 repo 規則、產品 OperatingModel/QualityBar/Vision/Roadmap、server、依賴與相關測試；保存 WIP／工具 schema 基線。
2. G1：新增 server 內部 `web_fetch.py`，以 httpcore 公開 network backend 介面 pin numeric IP；每跳新 pool，TLS 保留原 hostname；負向 fixtures 必須通過才能接受。
3. G2：沿用 `_search_once` 與 `_merge_results`，只在主來源失敗/零結果時 bounded fallback；Brave 設定預設 disabled，fixture 注入假 key。
4. G3：內部 `web_evidence.py` 定義 typed evidence；沿用原文字輸出附加版本化 JSON，不改 MCP response schema；缺漏、日期與字面衝突可追溯，不宣稱語意查證。
5. 精準驗證、讀回文件、比對 WIP/index/schema 雜湊並記錄實際結果。

安全失敗一律 fail-closed，不使用第二個 hostname HTTP client、代理或不同工具重試繞過。遇到權限拒絕則保存阻擋證據並停止該寫入。未取得 live 授權就停在 source/fixture gate；不因測試通過宣稱正式 runtime 已採用。

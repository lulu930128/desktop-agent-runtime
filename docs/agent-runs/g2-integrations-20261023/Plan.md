# G2 四個獨立唯讀 Integration

起始 HEAD 為 `c53f2f0d59c44c63e2120785beb989231de3e558`，保留 G1 dirty；證據 `.tmp/g2-integrations-20261023/`。G1 僅驗雜湊繼承，不重跑已通過 gate。

1. 核對 Japanese／English Hub canonical summary、due reviews、plan 與 Mail handoff、OMI cache-only contract。
2. 在既有 Core IntegrationRegistry 與 Core 背景生命週期接入獨立來源。GET 不發 Hub/provider 請求、不寫 DB。來源時間、unknown/stale/offline/auth 與 stable identity 不可省略；aggregate counts 不產生工作項目。
3. 僅做受影響 synthetic/contract/negative tests，證明實際 Today 投影與停止／關閉零請求；沒有 canonical OMI cache consumer 或 quota ledger 就回報 unavailable。
4. 保存相對 G1 preimage 的 G2 diff、來源對照、Code／Runtime 狀態與 Debt。

不修改其他 repo、正式設定／secrets／DB，不啟動正式 Kuro、不停止中央 Voice、不呼叫外部 provider 或 LLM、不改 sandbox/ACL/GPU、不 commit/push。遇權限拒絕立即停止。Study SRS／plan 邏輯留在 Hub；不做 G3 task persistence、G6 語音。

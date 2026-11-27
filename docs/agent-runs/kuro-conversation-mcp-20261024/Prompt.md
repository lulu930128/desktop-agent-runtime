# Kuro Conversation MCP 正式整合

以唯一 OMI Search STDIO adapter 取代舊 omi-market；接入已建置的 Japanese Study、English Study、Listening Audio 的明確唯讀子集。沿用既有 Registry／Client／Adapter／Executor／Policy／Catalog，不新增服務或 domain 管線。

驗收：真 STDIO discovery、schema 投影、canonical allowlist、v4 cache-only payload、舊路徑失效、離線 fixture dispatch、Settings 與簽章 bundle 同步、native confirm/CAS/readback、WIP 與舊 bundle 保全。

限制：不改外部專案、不安裝依賴、不啟停現役服務、不查私人資料、不呼叫正式 provider／LLM、不讀寫憑證、不 commit/push。HTTP-only 或需要獨立認證／確認佇列的成品明確 deferred。Source 與隔離驗證不代表現役採用。

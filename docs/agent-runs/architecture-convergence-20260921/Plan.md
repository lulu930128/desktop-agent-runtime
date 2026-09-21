# 整合計畫

1. 盤點：核對附件、既有 TTS diff、產品方向、source 接線、schema 與證據。完成條件為每個核心能力有明確現行 owner。
2. TTS checkpoint：保留既有 bounded fix，執行 21 個 central voice 與 8 個 capability tests、Python compile、renderer typecheck/build；獨立提交。
3. 架構收斂：更新 RuntimeArchitecture、README／索引／開發指南／AGENTS；補 OwnershipMap、DataLineage、RuntimeServices、CorePersistence、ResearchBoundary；Core source 只修正註解。UTF-8、連結、diff 與 AST 行為等價檢查後提交。
4. 研究 baseline：保存已提交來源的 hashes／policy 與 isolation 限制；記錄本次驗證與 commit 分組，再獨立提交。

## 決策與停止條件

- 2026-09-21：選擇單 DB、明確 migration/table ownership，避免在研究需求未定時引入正式資料搬移。
- 使用者選擇外部研究工作區延後；本輪只記錄規範，不宣稱已建立隔離環境。
- 文件／註解變更採 Tier 0，不執行 Core／MCP 全套測試或 runtime smoke；TTS 採對應 targeted regression 與 renderer checks。
- 發現測試 failure 或 staged 私有／無關檔案時先修正，不能用刪除 assertion、reset 或廣泛 staging 通過。

# Kuro 文件

先從 [README](../README.md)認識 Kuro，再依需求閱讀。

| 需求 | 文件 |
| --- | --- |
| 環境準備、啟動 | [開始使用](guides/getting-started.md) |
| 介面用途與限制 | [功能導覽](guides/feature-tour.md) |
| 故障與資料位置 | [故障排查](guides/troubleshooting.md) |
| 開發與驗證 | [開發指南](guides/development.md) |
| 元件與權限邊界 | [架構索引](architecture/index.md) |
| 中央語音 | [語音服務](central-voice-runtime.md) |
| 產品目標 | [願景](product/ProductVision.md)／[Roadmap](product/Roadmap.md) |
| MCP 可信度與安全修復計畫 | [M0 規格與施工入口](agent-runs/mcp-trust-security-m0/Prompt.md) |

## 與 OMI 文件的對照

2026-09-12 對照本機 OMI README、guides 目錄與 architecture index，採用相同讀者分層，不搬用其市場 contract、安裝包承諾或授權。

| 層次 | 原有狀況 | 本次整理 |
| --- | --- | --- |
| 產品入口 | README 混合功能與大量 source 細節 | 保留產品、圖片、入口與限制 |
| 使用指南 | 集中在 README | 獨立入門、功能、排查與開發文件 |
| 架構 | 缺乏統一索引 | 建立索引，保留原責任地圖 |
| 產品方向 | 四份文件已有內容 | 保留既有決策 |
| Electron | README 停留在第一版 | 對齊工作面板與 Launcher 協作 |
| 發布資訊 | 當時缺少頂層政策與授權 | 已補公開政策與授權範圍；整體 CI、完整新機流程與資產分發稽核仍待完成 |

本次核對的是本機 Git 追蹤文件與 source，未讀取遠端 GitHub 或驗證 live runtime。新增文件在另行 commit／push 前不會出現在 GitHub。

## 維護

功能異動同步更新指南與 owner 文件，只有已驗證能力寫成現況。版本以 `VERSION` 為準，截圖保留日期；一次性測試數字、agent 過程與 private payload 不放進使用指南。

## 公開協作文件

[貢獻指南](../CONTRIBUTING.md)、[行為準則](../CODE_OF_CONDUCT.md)、[安全政策](../SECURITY.md)、[Apache-2.0](../LICENSE) 與 [第三方聲明](../THIRD_PARTY_NOTICES.md)。政策文件不代表 GitHub 私人回報功能已啟用；可用管道以安全政策及實際 Security 頁面為準。

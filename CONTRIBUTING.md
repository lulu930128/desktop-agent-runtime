# 貢獻指南

Kuro 是 Windows local-first 個人工作助理 runtime。貢獻應改善工作資訊、互動品質、穩定性與可維護性，並尊重 [行為準則](CODE_OF_CONDUCT.md)。

## 開始之前

先閱讀 [README](README.md)、[入門指南](docs/guides/getting-started.md)、[開發指南](docs/guides/development.md) 與 [現況架構](docs/architecture/RuntimeArchitecture.md)。非平凡功能先在 [Issues](https://github.com/lulu930128/desktop-agent-runtime/issues) 說明需求、owner、相容性與驗證方式；安全問題不要公開細節，請看 [SECURITY.md](SECURITY.md)。

本機環境、模型、中央語音與憑證需要另行準備，clone 不等於完成安裝。不要為了測試擅自呼叫付費 API、發送訊息、刷新大量資料或停止共用語音服務。

## 修改邊界

- Launcher 管 lifecycle，conversation runtime 管對話與工具，Electron 管呈現；OMI 等外部專案擁有 domain truth。
- 不把 freshness、tool policy、記憶政策或市場判斷藏進角色 prompt／renderer。
- 保留 stale、partial、missing 與錯誤資訊；不能把失敗當成空資料。
- 保持局部 diff，不夾帶無關升級、格式化、使用者 state 或 generated output。
- 不提交 `.env`、token、對話、記憶、logs、資料庫、模型、私人 voice reference、Electron userData 或 dependency/build 產物。

## 驗證與 PR

文件修改做 UTF-8 讀回、相對連結檢查與 `git diff --check`。程式修改依開發指南跑 targeted tests／syntax checks；UI 修改按風險加 build 與實際畫面驗證，不因只改文件而啟動 runtime。

PR 請提供：問題與修改後行為、主要檔案、真正執行的驗證及結果、相容性／資料風險、未完成項目。分開描述 source checks、runtime adoption、provider 實證與桌面體驗，不將其中一項當成全部通過。可使用 Conventional Commits，例如 `fix:`、`feat:`、`docs:`。

## 貢獻授權

提交者須有權提供內容。對 Kuro 自有 Apache-2.0 範圍的有意貢獻，除另有明確書面安排，依 [LICENSE](LICENSE) 納入；修改既有第三方元件則維持該元件適用授權及歸屬聲明。詳見 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。來源或再授權權利不明的字型、角色、音訊與模型不應提交。

# 專案改名與中央語音切換

2026-09-11 使用者授權實作並先執行自動化驗證，桌面操作與人工聽感由使用者接續驗收。

- 目標：repo 改名 desktop-agent-runtime；中央 GPT-SoVITS 擁有模型與推論；Kuro/JLPT 使用 voice API。
- listening_audio 保留透過 JLPT 的既有 API 邊界。
- 不更名角色、namespace、IPC 或記憶；不 commit/push，不刪除舊 TTS。
- 模型、reference、音訊、環境、log 只留本機。未經人工聽感驗收不標記 production。
- 完成標準：相關 regression、兩角色中央推論、consumer smoke、新路徑入口檢查通過；人工驗收另列。

2026-09-12 更新：舊 TTS 已保存比對並移除；使用者授權整理、升級 1.1.0、commit 與 push，取代原先不發布與保留舊目錄的限制。人工驗收仍另列。

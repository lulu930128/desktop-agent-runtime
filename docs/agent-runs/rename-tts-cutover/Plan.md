# 實作與驗證計畫

1. 中央 gateway：registry/hash、loopback API、單一推論鎖、明確 busy/invalid/offline 回應。
2. Kuro：central/legacy 模式、voice ID 映射、runtime projection、adapter、啟停 ownership。
3. JLPT：中央 client、package identity 納入 audio cache，保留 MCP API。
4. Targeted regression、Kuro/Yuki/再 Kuro 真實推論與 consumer smoke。
5. 確認 exact processes，改名 repo，更新捷徑、active 文件，檢查新路徑入口。
6. 保留 legacy，交付人工桌面與聽感待驗清單。

若驗證失敗先修正；不終止未知 port owner。18790 已由 japanese-study-mcp 使用，中央服務改用已確認空閒的 18890。

2026-09-12 更新：舊 TTS 已保存比對並移除；使用者授權整理、升級 1.1.0、commit 與 push，取代原先不發布與保留舊目錄的限制。人工驗收仍另列。

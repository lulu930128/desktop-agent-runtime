# 修復計畫

1. Consumer：中央 POST read timeout 180 秒；busy 和 synthesis timeout 不啟動失敗冷卻、不重送原句；離線及錯誤有 5 秒冷卻。以 targeted tests 驗證下一句恢復、錯誤隔離與診斷隱私。
2. Readiness：讀取目標 voice、active model、last inference；區分 cold、busy、available、unavailable。健康輪詢不合成、不暖機，避免搶佔共用模型。
3. 驗證：相關 Python regression、syntax、renderer typecheck/build；使用正式 client 進行有限短句及切換語音驗證，保留端到端播放與人工聽感的獨立證據。

## 決策與失敗處理

- 2026-09-13：全部中央 POST 使用同一個 180 秒上限。health 只是快照；另一個 consumer 可能在 health 和 POST 之間切換模型，不能據此把 warm request 限回 30 秒。
- 不新增自動 warm-up。首次發聲按需載入，Launcher 顯示 cold；中央仍為唯一載入 owner。
- 有關聯的測試失敗先修正；中央 busy 或結果未知時不重送、重啟或啟動第二個模型服務。

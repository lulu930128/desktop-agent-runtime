# 中央語音 lifecycle 修復

## 目標與驗收

修復對話 TTS 在 30 秒後逾時及後續語音被冷卻期略過的問題。中央合成允許有界的模型載入時間；busy 與未知結果不得重送原句；服務恢復後可由下一句恢復。Launcher 僅在目標模型已載入且當次中央程序最近合成成功時顯示語音可用。

## 邊界

- 中央 Voice Runtime 保持唯一模型與程序 owner，沿用單模型及單推論鎖。
- Kuro 只傳 voice、text、language、speed_factor；`kuro -> kuro`、`yumi -> yuki`。
- 本次限定 consumer、readiness、狀態文字、回歸測試與文件；不改 MCP、記憶、角色 persona 或 legacy 資源。
- 真實 WAV、payload、runtime 採用、Electron 播放與人工聽感分別記錄；單元測試不能替代真實發聲驗收。

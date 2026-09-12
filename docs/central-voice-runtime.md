# 中央語音服務

Desktop Agent 與 JLPT 使用 loopback Voice Runtime v1，預設 `http://127.0.0.1:18890`。
18790 已由 japanese-study-mcp 使用。Consumer 不啟動引擎、不讀模型或 reference，不停止共用服務。

## 啟動與使用

中央服務的標準啟動入口位於本機 Voice Package 工作區。開機後先執行：

```powershell
& 'C:\project\voice package\GPT-SoVITS\scripts\start-service.ps1' -Background
Invoke-RestMethod http://127.0.0.1:18890/health
```

再開啟桌寵啟動器或 JLPT。此服務不隨 consumer 關閉；不安裝 Windows 開機自啟。
API `available` 表示可接收請求，模型按需載入；`last_inference` 才是當次程序的推論證據。
模型包維持 `staged`，人工聽感待驗。`busy` 回 HTTP 429，稍後由使用者重試，不偷偷切模型或啟動第二個引擎。

## 設定與邊界

- Desktop Agent：`kuro_launcher.settings.yaml` 的 `network.tts.mode: central`、host/port 與角色映射。
- `kuro` 對應 `kuro`；persona `yumi` 對應聲音 `yuki`。未配置角色映射會明確阻擋。
- JLPT：`JLPT_TTS_MODE=central`、`JLPT_VOICE_RUNTIME_URL=http://127.0.0.1:18890`。
- listening_audio 保留呼叫 JLPT；不另實作模型管理。JLPT audio cache 包含中央 package digest。
- 中央 service 只接 JSON 的 voice、text、language、speed_factor；不接受模型或檔案路徑。
- 單一推論鎖涵蓋模型切換與完整音訊生成；重建模型時清除上個角色的 reference cache。

## 舊資料清理與人工驗收

2026-09-12 依使用者要求清理舊 `gpt_sovits/`：10,347 個檔案在中央工作區找到 SHA-256 相同副本，約 16.25 GiB；唯一不同的 Python 快取也另存，沒有覆蓋中央引擎或模型。

本機保存清單：`C:\project\voice package\GPT-SoVITS\inventory\legacy-gpt-sovits-20260912\manifest.json`。每筆包含來源、保存位置、大小與 SHA-256；`result.json` 和 `removed.jsonl` 記錄完成結果與刪除項目。

舊目錄已移除，不能只把 mode 改成 legacy 就回退。`envs/kuro-tts310`、repo 其他音檔與資料夾不在本次清理範圍。舊 `00_kuro_bootstrap.ps1` 與 `compose.yaml` 不適用目前中央模式，請使用上方中央服務啟動入口，不要用它們重建舊引擎。歷史訓練設定與 manifest 的 source 路徑保留作追溯，並非目前執行路徑。

Kuro/Yuki 中央資源與 hash 檢查、桌寵中央語音 5 項測試通過。本次未執行模型推論、未啟停服務；模型包仍為 staged，人工聽感與桌面互動仍待驗收。

# 故障排查與本機資料

先確認 checkout、settings、啟動入口與 listener 身分，再決定是否重啟。不要預設清空資料、停止所有 Python／Electron 或切換舊 port。

| 現象 | 檢查與處理 |
| --- | --- |
| Work panel build missing | 檢查 `pet-electron/renderer-dist/work-panel.html`，於該專案執行 `npm run build:renderer`。 |
| 找不到 Python | 確認 `envs/kuro-llm310`；clone 不包含環境，勿改指向未知 interpreter。 |
| 面板可見但不能對話 | 檢查 settings、Launcher log 與 LLM readiness；Shell 可見不代表 backend ready。 |
| 有文字但無聲音 | 檢查 Bridge、中央服務與 voice mapping；health 不代表推論或播放成功。 |
| 關閉後程序仍在 | 面板隱藏到 tray 是正常行為；結束時使用既有 tray／控制台操作。 |
| Port 被占用 | 核對 PID、process 路徑與 service identity，不停止未知或共用服務。 |
| Today 空白或過期 | 看 source status、最後成功時間與錯誤；無資料不等於零事項。 |
| 工具 confirmation 被拒絕 | 一般工具尚無完整確認流程；不得用 allow 繞過 policy。 |

## 唯讀診斷

以下為預設 port，實際以 settings 為準：

```powershell
Invoke-RestMethod http://127.0.0.1:23567/status
netstat -ano | Select-String ':1188|:18890|:23456|:23567|:23568'
```

用 PID 再確認 process；HTTP 200 不能證明 source identity。Launcher `23568` 的 session token 不得貼到 renderer、issue 或截圖。`GET /briefing` 可能包含私人內容，勿公開完整回應。

## 資料與回復

| 資料 | Owner／位置 |
| --- | --- |
| Launcher 診斷 | `launcher_logs/` |
| 對話／記憶 | Conversation runtime 的 history／memory 設定，核對實際載入路徑 |
| 視窗／Briefing | Electron `userData` 的 `pet-shell-state.json`、`briefing-store.json` 等 |
| 生成設定 | `Open-LLM-VTuber/conf.launcher_runtime.yaml`，由 Launcher 生成 |
| 模型與私人 reference | 獨立中央語音工作區 |

目前沒有經本文件驗證的跨元件一鍵備份／restore。搬機或清理前盤點 owner 與路徑，停止相關 writer 後保留副本；SQLite 要使用一致性備份方式，不能承諾複製單一檔案已涵蓋全部 state。公開診斷先遮蔽私人內容。

詳見[現況架構](../architecture/RuntimeArchitecture.md)與[中央語音服務](../central-voice-runtime.md)。

# Study Hub 明確啟用路徑

正式設定 owner 仍是 Launcher 讀取的 `kuro_launcher.settings.yaml`，不增加第二個設定檔 loader、manager 或服務。此目錄的 [YAML 範例](StudyHubOptIn.yaml) **不會自動載入**，兩個來源預設皆關閉。

1. 操作者確認要開啟哪個來源，將範例的對應 keys 合併到既有 `core.integrations`；保留其他 Core、Mail 設定，不能整檔覆蓋。只將選定來源 `enabled` 改為 `true`。
2. `core.enabled` 與既有 Core port 必須已正確配置。不可同時啟用 legacy `study` snapshot 與這兩個獨立 Hub；Core 會拒絕重複 owner。每個 interval／TTL 為 60–86400 秒整數，enabled 必須是 boolean。
3. 日文固定只讀 Hub 18791，英文固定只讀 Hub 18887；每次 cycle 最多 health／summary／due20／plan20 四個 GET，不查 MCP、不回寫 Hub。啟用後，**下次另外核准的正式啟動**才由 Core 的唯一 integration reader 採用。這份文件不授權本輪啟動或重啟。
4. 若 Hub 要求認證，僅沿用 Launcher 所繼承的既有 `JSTUDY_API_TOKEN`／`ESTUDY_API_TOKEN` 環境，不將 token 寫入此範例或輸出 log。缺認證會顯示 auth_required，不繞過。
5. 關閉：把相應 enabled 設回 false，於下次核准的 owner 啟動採用；此配置不是 hot toggle。disabled worker 不發 Hub HTTP，Today 不把它計為 missing；observations 仍顯示 disabled。記憶體 snapshot 隨 Core 結束清除，不寫新 DB／私人 cache。

驗收以 `/v1/integrations/{japanese_study|english_study}` 與 `/v1/today` 的 source ID、時間、限制為準，不能只看 HTTP 200。English 缺來源 timestamp 時維持 unknown，bounded pages／輸出預算截斷維持 partial。此 opt-in 不啟用 OMI 或主動語音，也不增加 Conversation tools。

本輪只用此範例的 synthetic 副本驗證，不讀寫正式配置、認證或學習 DB，不重建已簽 Qt bundle。

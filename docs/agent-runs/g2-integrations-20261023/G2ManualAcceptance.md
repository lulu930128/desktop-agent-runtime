# G2 使用者啟動前驗收／實機檢查

本輪狀態：Source／Synthetic 驗證與正式 Runtime Loaded 分開記錄。工程端沒有啟動正式 Kuro、Hub、Mail、OMI，也沒有讀取私人 DB、郵件或憑證。請先由 Reviewer 核對本輪收據，再由使用者實際啟動。G1／G2 舊驗收數字是繼承證據，不是本輪 Native PASS。

## 已配置的第一波來源

唯一設定 owner：repo root `kuro_launcher.settings.yaml`。這是啟動時載入的設定，沒有 hot reload；不是另外載入 `docs/config/StudyHubOptIn.yaml`。

| 設定 | 本輪值 | 啟動後行為 |
| --- | --- | --- |
| `core.integrations.japanese_study.enabled` | `true` | Core 唯一 integration worker 對既有日文 Hub :18791 作 bounded read-only GET |
| `core.integrations.english_study.enabled` | `true` | 同一 worker、獨立英文 sourceId，使用英文契約；Hub :18887 |
| 兩個 Hub 的 `interval_seconds` / `ttl_seconds` | `300` / `600` | 一輪最多 health、summary、due(limit=20)、plan(limit=20)；每個 worker tick 最多一個 GET |
| `core.integrations.study.enabled` | `false` | 保持 legacy handoff 關閉，避免雙重 Study owner |
| `core.integrations.mail.enabled` | `true` | Launcher 唯一 MailPollerRuntime；Core 只讀其 status/work metadata handoff |
| Tools > OMI | 保留原使用者偏好；未讀取或改動私人 settings sidecar | `executionAvailable=false`，沒有背景 OMI poll、quota 消耗或第二市場服務 |

Mail 使用既有 `gmail.readonly`，Gmail 呼叫為 GET，沒有 send／modify 路徑。Poller 預設每 900 秒、最短 300 秒，預設最多 12 封；既有保存偏好可調整上限至 500 封。開始後可能立即讀取；既有規則可能 GET 符合條件的完整本文。這不是「永遠只讀 metadata」的 producer；**Core Today 才是 metadata-only consumer**。OAuth 到期可能更新 token，原 producer 也會寫本機 handoff；本輪沒有執行以上動作。缺認證須降級，不能自動跳過驗證或強行建立登入流程。既有 `autoRefresh=false`／`KURO_MAIL_BRIEFING_AUTO=0` 仍能抑制 poller 查詢。

## 使用者實機檢查

1. 先確認沒有另一個 Kuro owner；若 1188／23456／23567／23569 被未知程序佔用，停止本次驗收，不 kill PID 或另開一套服務。**中央 Voice :18890 是共享服務，不可停止。**
2. 在 canonical repo 使用正式入口（由使用者執行）：

   ```powershell
   cd C:\project\desktop-agent-runtime
   .\envs\kuro-llm310\python.exe -B .\launcher_qt.py
   ```

   依現有 Qt 啟動流程啟動 profile，不改 sandbox／GPU flags。黑畫面、權限拒絕或需 OS 手勢時記錄 Unknown／UNVERIFIED，不繞過。勿另起 `kuro_core_service.py`、Mail poller 或 Electron launcher。
3. 記錄 Qt／Tray／Controller／WS／Pet 的實際狀態與 owner PID；listener 或 HTTP 200 本身不等於 Runtime Loaded。Live2D、Native 桌面與 tray 若未目視驗證，一律 **Unknown／Native Pending**。
4. 在 Qt Today 檢查 `japanese_study`、`english_study`、`mail` 的來源狀態與項目。Gmail 的 canonical ID 是 `mail`，不是第二個 Gmail source。日英項目不可混用 ID/schema；Hub 回傳沒有工作就應為空，不得從 summary count 生造 Task。英文缺 source timestamp 時顯示 unknown 是有效限制，不應硬改成 current。
5. 使用既有 Controller／Diagnostics 的 Core 讀取表面核對 `/status`、`/v1/today`、`/v1/observations` 與 `/v1/integrations/{sourceId}`。這些路由需要現有 owner session token；不要從私有檔擷取 token，也不要貼 token、信件標題、學習內容或完整 payload 到驗收 log。若目前 UI 沒有足夠診斷表面，該細項標 UNVERIFIED，交回 Reviewer，不新增旁路。只記錄 sourceId、availability、freshness、時間、受限 count 與 limitations。
6. 若 Hub 原本離線／無認證，確認來源顯示 missing／auth／stale 等實際狀態、Schedule 仍運作；不要為測試刻意停止共享 Hub。Mail 認證失敗應保留可辨識失敗與 last-good 時間，不能偽裝為零封新信。Qt Mail detail／refresh 仍 fail-closed，不以此觸發 provider refresh。
7. Settings 的「主動語音通知」與 Tools > OMI：先記下原值；只做偏好變更，native confirmation **取消**應不保存，**同意**後離開並重進頁面，確認由 Core 再次讀回。間隔、預算非法值應被拒絕；保留原值或測試後恢復。保存成功與背景執行分開：畫面既有文案應顯示「偏好已儲存並由 Core 讀回；自動觀測與主動播報仍未啟用」。不可用聊天 TTS 發聲來代替此驗收。
8. OMI interactive 的正式路徑仍為 Conversation `omi.ask` / `omi.decision.v4`；它可能刷新 provider／呼叫 LLM，**不屬於本輪自動安全驗收，不送真實市場問題測試**。只核對工具可見性與 unavailable 狀態。Auto OMI 為 **BLOCKED_UNAVAILABLE**：尚無安全 scoped cache-only/no-DB-write handoff，沒有 restart-safe quota／claim，不會暗中排程；也不掃描私人 history。
9. 使用正式 Quit 結束此次啟動的 Kuro-owned children，核對 owner 退出、中央 Voice 持續存在。不要用 taskkill 清未知 listener。僅關閉視窗可能是縮到 tray，不能當作 Quit 成功。

## Source Ready 與 Runtime Loaded

| 證據 | 可宣稱 | 不可宣稱 |
| --- | --- | --- |
| synthetic config→Core worker→Today→Qt adapter、簽章與 SHA 驗證 | Source Ready／Source PASS | 正式來源已載入、Native PASS |
| 正式 owner identity 正確、Qt Today 有對應來源與真實取得時間，與來源限制相符 | 該來源 Runtime Loaded | 其餘來源也正常、OMI auto 可用 |
| Qt／Tray／Live2D 操作、Quit 與共享 TTS 保留均由使用者確認 | 對應 Native 細項 PASS | 未執行的 OS／語音／外部工具項目 PASS |

## 最小 rollback

先由使用者正常 Quit Kuro，再只改原 YAML：移除本輪新增的 `japanese_study`、`english_study` 兩個完整 entries（恢復原本 absent → 預設 disabled）；將 `mail.enabled` 改回 `false`，`study.enabled` 保持 `false`。若只是暫停採集，也可將兩個新 entries 的 `enabled` 都設 `false`。下次由使用者啟動後，disabled 來源不採集、不污染 Today complete；Mail 不 spawn。**不要改 DB、token、private handoff、Hub／OMI 配置或 Qt bundle pin。**

保留原 G1 signed bundle 與 rollback 資產；本輪沒有 UI／immutable originals／pin 變更，不需重建 bundle。設定頁若測了偏好，另由同一 Settings owner 恢復測試前值，不直接修改 sidecar。

## 留給 Reviewer 的記錄

本輪收據：`.tmp/g2-manual-ready-20261023/Status.json`、`Targeted.log`、`BundleVerification.json`、`TaskDiff.patch`。請填各來源 Source／Runtime／Native 結果與原因，避免分享私人內容。承接的傳輸限制：Hub body idle 200ms fail-closed（單請求總 deadline 1.5 秒）；慢來源可能降級，不能以放寬 timeout 或重試掩蓋。詳細 observations 仍受輸出預算，分頁尚未實作；`hasMore` 不表示完整資料已載入。

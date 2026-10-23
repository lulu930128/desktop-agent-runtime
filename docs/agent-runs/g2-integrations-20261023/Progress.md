# G2 來源切片與 reviewer 修正紀錄

狀態：**G2 受檢 Source Gate PASS（20 targeted + 1 配置 smoke + 8 bounded live GET）；正式 Runtime Pending；OMI BLOCKED_UNAVAILABLE，G2 整體 partial。**

本輪依 reviewer 要求收斂為生命週期隔離、收取時間、disabled 品質語意及 Mail failure 的定點驗證，追加一次使用者授權的 8 GET 真實 Hub 契約探針。沒有重跑 G1 gate，也沒有啟動正式 Kuro／Hub、直接讀取私人 DB 或查詢外部 provider。

## 已完成與證據

- Japanese／English 各自使用固定 Hub identity、loopback port 與 bounded GET summary／due reviews／plan；不共用日文 vocab schema，不自行計算 SRS 或 plan。完整 bounded cycle 通過驗證才發布記憶體 snapshot。
- CoreApplication 持有一條 integration read thread，明確 start、close、join；Schedule 的 G2 callback 注入已移除，既有 Schedule 程式保持原樣。Hub 權限失敗永久封鎖該來源；不設定 Schedule stop event、不重試該來源或切換路徑。
- Core GET 僅投影已取得 snapshot；synthetic producer → 真正 Core HTTP routes → Today 證明兩個 source ID 各產生自己的工作證據。summary aggregate 不產生 task。
- snapshot `receivedAt`、`details.fetchedAt` 保留真正取得時間；`projectedAt` 另列。重讀不刷新 receipt；freshness 隨投影時間變 stale。English 缺少來源時間時保持 unknown，不假造來源更新時間。
- Today expected sources 僅包含已啟用來源。全部 disabled 時 complete=true、無 sourceMissing／stale、無 task、零 Hub request；disabled 仍在 observations 顯示 missing + disabled。OMI enabled 但不可執行時仍如實成為 unavailable quality state。

定點測試：`python -B -m unittest test_g2_integration_boundaries -v`，**10/10 PASS**。測試中的 Schedule 使用真實 loop、synthetic store／notifications；Hub blocking timeout 與 PermissionError 不阻塞通知／materialization。停止後 Core integration、Schedule、API thread 均退出。測試只使用 ephemeral loopback Core API 和 synthetic client，沒有連接正式 Hub。

Mail 定點驗證另 **5/5 PASS**：先以既有兩個 regression 重現 WIP 將 cached availability 錯改 offline、auth connection 不相容；修正為保留 last-good availability 與既有 disconnected 語意，另驗證 auth／stale／missing-work 經唯一 handoff 進 Today、無 DB／network／handoff mutation。只有驗證過的 schema／attempt 能提供 auth 狀態。

有界 live probe：**8/8 HTTP 200**，透過目前 HubClient.get 各取日英文 health／summary／due／plan 一次，兩源都被 project_hub 接受。日本來源兩頁各 20 筆，維持 bounded_page_may_be_partial；英文兩頁為空，沒有假造 task。英文非空投影仍由 synthetic 證據支持。沒有保存 response body、學習標題／ID／憑證，只記錄 allowlisted schema keys、受限 count、HTTP status 及 acceptance。未啟動 worker／服務、未重試。

後續 reviewer 修正另 **4/4 日本 summary regression PASS**：日本明確解析 canonical `items.total`，英文保留 scalar `items`；錯型別／負值／缺少 total 不偽造 0。有效且無其他限制的日本 summary 可為 AVAILABLE。先前 live probe 僅證明 schema 可接受，不是無品質限制證明；本修正沒有重跑 live GET。

正式 transport 負載 **1/1 PASS**：兩 Hub 各 due20 + plan20，長中文 title／summary；Today 保留原 TodayView contract、不重複嵌入完整 Evidence。每來源先用輸出預算，超出時標示 output_budget_exceeded／partial；完整 bounded snapshot 不被刪除。Today 實測 21,510 bytes，observations 15,914 bytes，日英詳細端點各 7,593／7,518 bytes，均小於原 65,536 cap。透過真正 Core HTTP、CoreRuntime.request 與 QtLauncherController.read_today 讀取成功，沒有調大 cap 或放寬 UI。初次負載 fixture 的舊 as_of 與新的 receipt 不一致，既有時間防護拒絕；改成同次 snapshot 時間後 PASS。

配置 smoke **1/1 PASS**：synthetic load_config → Launcher argv → Core entrypoint constructor；Popen 與 CoreApplication 為 mock，零真實 child／HTTP／DB。初次 fixture 漏填必要 port／env python，補齊 synthetic port 與 mock executable 後通過，不更改正式配置。

證據：`.tmp/g2-integrations-20261023/ReviewTests.json`、`MailFailureBefore.json`、`MailFailureAfter.json`、`LiveHubProbe.json`、`G2Status.json`、`G2Diff.patch`。首次 9 項測試有 1 項 fixture 的 as_of 早於 snapshot receipt，觸發既有防護；修正 fixture 後同組測試及新增 enabled Mail 共存案例全數通過。這些數量不包含 G1 106 targeted + 12 DOM + signed bundle 歷史 gate。

## 各來源交付狀態

| 來源 | Source／Today 證據 | 正式狀態與缺口 |
| --- | --- | --- |
| Japanese Study | synthetic canonical Hub cycle → Core HTTP Today PASS；live 4 GET + project_hub PASS | Runtime Pending；正式設定未啟用、未重啟。bounded pages 保持 partial。 |
| English Study | synthetic canonical Hub cycle → Core HTTP Today PASS；live 4 GET + project_hub PASS；CEFR metadata、獨立 identity | Runtime Pending；現有契約缺少來源 timestamp，freshness 保持 unknown；live 空集合。 |
| Mail | 沿用原 status/work handoff；5 項 failure／cache／auth regression PASS；synthetic metadata 真正進 Today；未新增 poller | 未讀取正式 Mail handoff／信箱，Runtime Pending。detail／refresh 保持 fail-closed。 |
| OMI | persisted settings policy 投影；disabled 不污染 Today；enabled 仍 executionAvailable=false | BLOCKED_UNAVAILABLE：缺 verified no-refresh consumer、quota ledger、idempotency。沒有使用 chat preflight 或新增 provider。 |

## Debt 與下一步

1. Mail 正式 owner adoption／資料可用性尚未驗收；沒有讀取個人信件。既有 status/work producer 與 poller 程式保持不變。
2. Hub transport 的惡意慢流／payload bounds 尚未作完整負測；本輪 timeout 是 synthetic 阻塞故障隔離測試。8 GET 成功僅證明當下 canonical readonly contract，不代表正式背景週期或 Native 驗收。
3. Launcher options 的 synthetic 接線已驗證，正式啟動採用仍 Pending；未修改正式設定、DB、secrets。G1 Native 維持 UNVERIFIED。
4. Conversation 未新增 Japanese／English MCP tool 註冊；本次 Core Hub GET 不擴大聊天工具 side-effect surface。若需要聊天工具，另作明確只讀 allowlist 契約。
5. OMI 排程不開放；interval/budget 保留 Core 驗證及 persisted intent，沒有 canonical safe consumer 與 ledger 前不可啟用 execution。聊天分析路徑語意未修改。
6. 詳細 observations 目前是有界前綴投影，超過預算會給 hasMore／evidenceTotal／evidenceReturned；後續完整翻頁 UX 尚未實作，不把省略項當成完整來源。

G1 dirty、六份 immutable originals、signed bundle pin 維持繼承；相對 G1 的允許交疊只有 CoreApplication 組裝。沒有 commit／push。後續只補剩餘受影響契約缺口，不能把本輪 isolated PASS 當成正式桌面或完整 G2 驗收。

封存核對：G1 receipt SHA 不變，17 份 G1 source 中 16 份 byte SHA 不變，CoreApplication 僅有 G2 組裝差異。Schedule 的混合行尾經原 Git 內容及 G1 baseline SHA 驗證還原，SHA=`e96f854b7fee940ca2f846f39cba091fc82d0dec7ae0640dcf8f5faca2b581a9`；未改封存 G1 receipts。所有受影響 Python 以 compile(source) 驗證，git diff --check PASS。Repo 保留 G1 + G2 dirty，完整清單見 task-local GitStatus.txt／G2Diff.patch。

最終 OS 唯讀核對：正式 1188／23456／23567／23569 無 listener；Voice 18890 仍由 PID 50520 持有，建立時間 2026-10-21T14:23:54.6085870Z 與原身份一致。記錄的測試／probe PIDs 均已退出，沒有 kill 任何程序，見 FinalRuntime.json。

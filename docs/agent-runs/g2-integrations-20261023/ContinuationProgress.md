# G2 continuation：明確 opt-in 與 transport 邊界

狀態：**Source continuation CONFIRMED；G2 仍 partial，待獨立審查。正式 Runtime／Native 未驗收。**

基線：HEAD `c53f2f0d59c44c63e2120785beb989231de3e558`。沿用 [前次 Progress](Progress.md) 的 G1 106 targeted + 12 DOM + signed bundle，以及 G2 20 targeted + 1 config smoke + 8 Hub GET。沒有重跑 G0／G1，沒有追加真實 Hub／OMI／Mail 查詢。前次 G1/G2 receipts 不修改，續作 preimage／SHA／diff 存於 `.tmp/g2-continuation-20261023/`。

## 本次實作

1. 新增 [StudyHubOptIn.yaml](../../config/StudyHubOptIn.yaml) 與[操作說明](../../config/StudyHubOptIn.md)，沿用唯一 `kuro_launcher.settings.yaml` owner。範例預設 false、不自動載入；操作者只合併所選來源 keys，明確改 true，於下次另行核准啟動採用。沒有新 loader、manager、服務、UI 或正式配置變更。
2. HubClient 的 1.5 秒 deadline 現在涵蓋 connect／headers／body，不再收到 headers 後重新計時。每次 read1 同時受剩餘總時間及 **200ms body idle** 限制；header/connect 仍有原一秒 socket bound。逾時拒絕本次 snapshot，不 retry、不刷新 provider。
3. close／timer 保留並 shutdown 真正建立時的 socket reference；finally 關閉 response／socket、取消並 join Timer。Windows 的 in-flight select 不保證立即被 shutdown 喚醒，因此明確縮短 body idle wait，固定 0.5 秒 cancel gate 已通過。這不是放寬測試等待或忽略 alive。
4. source as_of 已 stale、plan item 缺 timestamp 時，原程式把 source TTL 套到 retrieval timestamp，產生 valid_until < observed_at。修正為各 evidence 以自己來源時間或明示 retrieval basis 計算 TTL；source 仍 stale，缺時間的 item 仍 unknown，不捏造來源更新時間。

### 失敗與修正證據

- `TransportBefore`：5 項中 2 PASS、2 FAIL、1 ERROR；重現總時間 2.359 秒超過預期、0.5 秒取消失敗、timestamp 順序錯誤。
- 一次 `CancelDiagnosis` worker stack 定位 `HTTPResponse.read1 → socket.recv_into`，沒有 Timer join／response.close deadlock。
- `socket.dup()` 候選亦未喚醒 Windows read1；沒有保留 duplicate handle 實作，也沒有反覆重試該候選。
- 曾放寬等待到 1.2 秒的 `TransportAccepted` **不作為取消驗收證據**；原測試門檻已恢復為 0.5 秒。
- 最終 `CancelFinal`：只重跑該固定 0.5 秒 case，**1/1 PASS**。其餘四項採 `TransportAfter` 中已通過案例，不把整份 failed receipt 冒稱全綠。
- `StudyOptIn`：**2/2 PASS**。synthetic YAML → 真正 load_config → CoreApplication 原有 integration worker → 兩個 ephemeral Hub（各四個 HTTP GET）→ 真正 Core HTTP Today；預設 off 零 HubClient.get，on 後不同 sourceId 各有工作項目，GET 不增加 Hub requests，stop 後 worker／Schedule 退出。沒有真實子服務或私人 DB。

本次新接受證據合計 **7 個獨立 cases**（transport 四項繼承 + 固定 cancel 一項 + opt-in 兩項），不重計歷史 G1/G2 gate。Today／observations 64KiB 與 Schedule PermissionError 隔離繼承有效 G2 證據，相關 owner 與輸出預算程式未修改。

依使用者最後收斂指示，對最終程式另作一次最小收尾 regression：**FinalRegression 6/6 PASS**（Hub transport 5 項，固定 cancel 0.5 秒；受影響 Today／observations 64KiB 1 項）。實際 Today 21,510 bytes、observations 15,914 bytes，CoreRuntime 與 Qt Controller 可讀。加上先前 Study opt-in 2/2，收尾採用 **8 個 cases**，其中 Today 1 項為受影響重驗而非新功能。無 G0/G1 重跑。

封存：Python syntax／git diff --check PASS；當前 36 個 dirty files，HEAD 未變。前次 G1/G2 receipts／pin 與其他 baseline source SHA 不變，現存 source 只有 hub_integration.py 續改，另新增兩個測試與三份文件。最後唯讀 OS 證據確認所有記錄測試／runner PID 已退出；1188／23456／23567／23569 無 listener，Voice 18890 維持 PID 50520、建立時間 2026-10-21T14:23:54.6085870Z。沒有 kill 程序。詳見 FinalRuntime.json／Status.json／GitStatus.txt。

## 各來源與邊界

| 來源 | Production path | Source Gate | Runtime／下一步 |
| --- | --- | --- | --- |
| Japanese Study | 原 Launcher YAML → core_hubs → CoreRuntime argv → CoreApplication reader → bounded Hub snapshot → Today | CONFIRMED；新增 opt-in 端到端，舊 live/schema 證據繼承 | 正式 disabled、Runtime Pending；獨立 review 後由操作者選擇 opt-in 與另行核准啟動。 |
| English Study | 同一 owner、獨立 english_study、英文 scalar summary／CEFR schema | CONFIRMED；off 零 HTTP，on 真正進 Today；未知時間不偽裝 current | 正式 disabled、Runtime Pending；缺來源 timestamp 的 unknown 是來源限制。 |
| Mail | MailPollerRuntime 唯一 child → canonical status/work env → 原 handoff → Core metadata projection | CONFIRMED source/provenance；繼承正常／auth／last-good regression；本輪無 Mail source 修改 | 正式 adoption UNVERIFIED；不讀私人手交檔／信件，不開第二 poller，不 detail／refresh／send。 |
| OMI | Conversation `omi.ask`／`omi.decision.v4` → scoped history evidence；Core 目前僅 OmiIntegration policy status | BLOCKED：沒有經證明可供 Core 消費的 bounded scoped handoff，也未證明無 OMI DB mutation 的全程 cache-only read | executionAvailable=false。無 scheduler／quota ledger／新 cache。等待正式 owner 提供可審查契約；不是啟動背景權限。 |

### OMI 有界追查結論

已定點讀取 Kuro `mcpp/market_preflight.py`、`tool_executor.py`、`single_conversation.py` 與 `basic_memory_agent.py`：`build_omi_evidence_snapshot` 是 conversation presentation projection，completed event 由 `_store_tool_status_event` 依 conf_uid/history_uid 寫入 history；`_last_omi_resolution` 是當前 agent 的 follow-up state。兩者都不是 Core global authoritative market snapshot。未讀任何 history 檔案，也未新增跨角色／持倉 consumer。

OMI backend 僅定點讀取 `ai/ask*.py` 的 policy／execution 邊界：可看到 cache_only、allow flags 與 refresh_policy mode=off，但這不等於全程 no-DB-write 或 runtime attestation。依 reviewer 收斂要求停止擴查，不作市場詢價測試。未證明安全契約前，不接 scheduler，也不新增無 consumer 的 ledger 空殼。

未來若 owner 提供正式 consumer，仍必須明確強制 cache_only、allow_llm=false、allow_external_fetch=false、allow_write=false、refresh_policy.mode=off，驗證 scoped provenance／source time／no-refresh／no-DB-write，再實作 restart-safe quota 與 at-most-once claim。不能使用 chat preflight 的 prefer_live 預設。

### Mail provenance／權限核對

`kuro_launcher/mail_poller_runtime.py` 以 Launcher 為唯一 child owner；`mail_environment.py` 要求 status/work 為不同 absolute resolved paths，清除再注入 canonical env；`local_mcp/mail_work_handoff.py` 的 producer 將路徑限制於 private_root、atomic replace，失敗保留 last-good。Core `mail_adapter.py`／`mail_work_adapter.py` 驗 schemaVersion、gmail_briefing source、kuro.mail.work.v1、時間與 generation mismatch，只消費 bounded metadata。現有 source-level read/write 邊界符合本批範圍；不將此靜態核對當作正式 OS ACL 或私人資料可用性驗收。

## Debt／審查重點

- **200ms body idle 是刻意更嚴格的 transport policy**：慢速 body 會 fail-closed／保留 last-good，而非使用完整 1.5 秒等待下一段。須由獨立 reviewer 接受此 latency tradeoff，不能把 synthetic PASS 當成正式網路採用。
- cancellation 的 Windows stack／候選失敗／最終固定門檻結果全數保留；沒有 kill PID 或調整 sandbox／ACL／GPU。
- config 為啟動時採用，沒有 hot toggle。正式設定未變，OMI auto 與 G6 語音仍不可用。
- observations 翻頁、正式 Mail adoption、Native 桌面驗收沿用前次 Debt；本輪不擴功能。
- 所有舊 receipts／Qt pin／immutable originals 保留，Repo 持續 dirty，不 commit／push；以本輪 Status.json 與 ContinuationDiff.patch 為續作範圍。

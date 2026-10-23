# G2 使用者實機測試準備收據

2026-10-23；main `c53f2f0d59c44c63e2120785beb989231de3e558`。狀態：**Source PASS／Runtime Pending／Native UNVERIFIED／OMI auto BLOCKED_UNAVAILABLE**，等待獨立 Reviewer 確認，不能宣稱 G2 fully complete。

## 本輪範圍

- 按使用者明確授權，只在唯一正式 YAML owner 加入 `japanese_study.enabled=true`、`english_study.enabled=true`（各 interval 300 秒、TTL 600 秒），並將 `mail.enabled` false→true；legacy `study.enabled=false` 保留。沒有 code 常數強制 enabled。
- 增加 `G2ManualAcceptance.md`，說明官方入口、使用者觀察項目、設定 readback、fail-closed、正式 Quit 與最小 YAML rollback。
- 增加 `tests/test_g2_manual_readiness.py`，使用實際 Core worker／HTTP API／Qt adapter，但全部來源內容、Hub ports、Mail handoff、Schedule store 都是合成隔離 fixture。
- 未改產品 Python／Qt／original renderer source、signed pin、正式 DB／private settings。前次 36 dirty 檔逐一 SHA 保留；加上本輪 YAML、測試與兩份文件，共 40 dirty files。不 commit／push。

## 本輪證據

`.tmp/g2-manual-ready-20261023/` 保存 Baseline、Targeted、BundleVerification、FinalRuntime、TaskDiff、DiffCheck、GitStatus、Status。TaskDiff 只包含本輪四個檔案；既有 G1/G2 diff 不覆寫。

定點 **4/4 PASS**（2 新 cases、2 既有 Mail owner cases），命令記於 `Targeted.json`：

- 正式 Core 配置片段→隔離 Launcher config→實際 Core worker→日／英各四次 ephemeral GET→Today 三個 sourceId→Qt getData；合成 Mail handoff 無改寫、沒有 DB；Settings readback 的 `ok=true` 與 `executionAvailable=false` 保留。
- rollback/off→Hub 零 HTTP、Mail 零 child、Today 沒有 disabled missing debt；Core／Schedule／API worker 全部正常退出。
- Mail enabled 仍只 spawn 一個 mocked owned child，status/work env 是同一組 canonical paths；disabled 不 spawn，Electron owner 仍被抑制。沒有真實 Mail provider 呼叫。
- 新測試 Python syntax、UTF-8 文件讀回、`git diff --check` PASS。Today／observations 64KiB 的既有大 payload gate 繼承；本輪合成三來源 observations 也通過正式 CoreRuntime 64KiB cap。沒有放大 cap、重跑 G0/G1 或重建 Web。

簽章驗證透過正式 `VerifiedOwnerBundle.load`，六份 originals 對照原 Git `995c23c7c8d1be62000229d58610d2214f3bb745`，所有 bundle source hashes 符合 lineage；pin 未變：fingerprint `c45c572dd566dafb4cd7f7e3aeb05d3d9edf5588e97e502554e5f7bd2fdd7cca`，manifest `7327d4b085a29581f39fbccda9e9f4a5893aef82bfe3a2544ff8a1eea291a0c5`。

繼承 G1 106 targeted＋12 DOM、G2 20 targeted＋1 config＋8 Hub GET、continuation transport 5＋Today 1＋opt-in 2；原收據 hash 未變，不重計成本輪新驗收。

## 各來源採用與 Debt

| 來源 | 設定／正式路徑 | 本輪界線／下一步 |
| --- | --- | --- |
| Japanese Study | enabled；Launcher→Core 唯一 integration reader→:18791→Today | Source PASS；使用者啟動後才可確認 Runtime Loaded／Native |
| English Study | enabled；獨立 english_study→:18887→Today | Source PASS；缺來源 timestamp 保持 unknown，不套日文 schema |
| Mail | enabled；Launcher 原唯一 poller→status/work→Core metadata | Source PASS；正式認證、偏好、手交資料未讀，Runtime UNVERIFIED；唯讀 producer 可能按原規則讀本文與更新 OAuth／本機 handoff，詳見手冊 |
| OMI | 保留 Settings intent／Conversation interactive owner | auto BLOCKED；缺安全 scoped cache-only/no-DB-write handoff、readiness attestation、restart-safe quota/claim；未新增 market cache／manager，未掃 private history |

既有 Debt：200ms body idle fail-closed 的慢來源限制；observations 詳細分頁未實作；Mail detail／refresh、Pet／附件沒有安全契約者保持 fail-closed；主動語音只保存偏好（G6 不在此輪）。GUI 文案已明示保存與執行不可用，未作會需要重新簽章的文案修改。

最後只讀 OS 觀察：測試 PID 58252、runner PID 72400 均已退出；1188／23456／23567／23569 無 listener；中央 Voice :18890 維持 PID 50520、建立時間 `2026-10-21T14:23:54.6085870Z`。沒有正式服務啟停或 kill。下一步為獨立 review，之後依 `G2ManualAcceptance.md` 由使用者本人啟動驗收。

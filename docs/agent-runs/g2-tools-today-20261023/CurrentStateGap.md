# G2 工具設定／Today 來源概覽：現況與缺口

2026-10-23；main `c53f2f0d59c44c63e2120785beb989231de3e558`。承接 40 dirty WIP，沒有 reset／commit／push。使用者已啟動正式 Kuro；本輪未啟停、重載或對其發送操作。

## 根因與修復

- 原 Settings > 工具與權限直接使用 immutable renderer 的唯讀 tool list，因此出現內部 ID／mode，沒有保存控制。改由既有 owner-presentation overlay 取代該區，21 項按網路搜尋／檔案與對話查找／郵件／市場情報四服務分組，以原生 details/summary 收合；繁中名稱、用途、政策與開關分開呈現，raw ID 留在診斷展開區。重繪保留同一 panel 和收合狀態。
- 採 Reviewer 的最小方案：原 policy JSON 每工具增加可選 `enabled` boolean（預設 true）；false 封鎖，true 繼續經原 ToolPolicy.mode／argument／path／URL 檢查。沒有第二份 ceiling；CATALOG 僅供名稱與顯示，不能提供執行權限。未知工具及任意 mode/constraint 更新不被此 editor 接受。
- 保存路徑為 Qt protocol → native confirmation → Controller → canonical `tool_policy.json`。只允許 name／enabled／expectedDigest；跨程序排他 writer lock、digest CAS、同目錄 tempfile＋fsync＋atomic replace、再次 GET readback。不是 localStorage；拒絕 noncanonical owner override、壞檔、未知 registry、redirected path；不重試或自動移除殘留 lock。
- ToolExecutor 初始化載入 policy，沒有熱採用證據。UI 明示保存與 runtime adoption 分離；原 confirm 授權工具即使 enabled=true 仍封鎖，因為工具執行確認佇列尚未提供。設定變更的 native confirmation 不等於工具執行授權。
- Today 工作只由 evidence materialize。英文先前真實 probe 的 due／plan 都空，不能從 summary count 造 Task；缺來源時間仍標 partial／unknown。日文可能因 bounded page 而 partial。Mail 本次正式來源狀態未經已授權 owner token 讀取，**不能判定其缺項是未授權、空信箱、快照缺失或未採用**；只在 synthetic 證明 auth／missing／last-good 呈現。
- `/v1/today` 新增 lean `sourceOverview`，與 items/sourceStates 分離，不重複 Evidence；顯示來源 availability／connection／freshness／時間／limitations。disabled、缺快照與 OMI 不捏造新 receipt；disabled 不污染 complete。原本 Source filters 不認識獨立日英 ID，現在透過 canonical-model 與原 presentation preference allowlist 加入，不修改 immutable main/model。
- OMI auto 仍 executionAvailable=false；卡片明示背景尚未可用。既有 proactive voice／OMI settings 保留獨立區塊，已將其 execution unavailable 文案改為中文。沒有新 scheduler/cache/provider，也不讀 per-history private evidence。

## 證據與未完成事項

Source／isolated PASS；正式 Runtime Adoption Pending，使用者原生手勢／正式資料驗收仍 UNVERIFIED。OMI auto BLOCKED_UNAVAILABLE。完整數字、hash 與命令見 Progress.md、task-local Status.json。

原生 details/summary 與具 aria-label 的 checkbox 保留瀏覽器鍵盤語意；isolated Qt 驗證程式控制收合／點擊及真實 modal，未冒稱使用者的實機鍵盤、螢幕閱讀器或服務重啟驗收。正式 Mail 根因仍待使用者在新版來源卡片確認，不讀取私人 token／DB／信件來補證據。

此工具開關只控制 Conversation ToolExecutor，不關閉獨立 Mail poller 或 Study integration；UI 已明示範圍。若要停背景來源，仍由既有 YAML／來源 owner 管理。原 read_only 的 OMI interactive 工具可能使用外部資料／LLM，開關保存不執行它；本輪沒有市場詢價。

## Reviewer／使用者下一步

先核對 task diff、policy boolean 邊界與兩版 signed bundle。由使用者自行決定何時正常 Quit／啟動以採用新 Python 與 bundle，工程端沒有重啟現役服務。採用後測工具關閉／重新開啟、取消／保存、讀回與重新載入；確認原 auth 工具仍不可執行。Today 依來源卡片確認英文 empty＋時間限制、Mail 真實原因與 OMI blocked，勿以沒有 Task 推斷離線。

## Rollback

舊 G1 bundle `c45c572d…` 完整保留並重新驗簽。`.tmp/g2-tools-today-20261023/preimage/` 保留本輪開始的既有 dirty source；`TaskDiff.patch` 僅包含本輪增量。不要 git reset 或套用 HEAD 覆蓋 G1/G2。

需要回退時，先由使用者正常退出，再由 Reviewer 依 TaskDiff 反向套用本輪交集、恢復對應 old pin／owner overlay，保持六份 originals 不變。若使用者已保存 enabled=false，不可僅回退舊 ToolPolicy consumer：它不認得 enabled，且移除 false 會重新啟用工具。應保留 consumer 的 boolean gate，或在另行確認下把停用意圖轉成原有 blocked mode，再回退其餘部分。**不要複製 synthetic policy 到正式路徑，也不要刪除真實 policy／私人 DB／token／handoff。**

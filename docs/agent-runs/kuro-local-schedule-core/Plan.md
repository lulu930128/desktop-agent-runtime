# 本機時間表實作計畫

狀態：使用者先授權 M0–M3，後續授權完成 M4–M6 與桌寵重啟測試。各階段已完成本機實作與驗證，見 [Contract.md](Contract.md) 與 [Progress.md](Progress.md)。以下保留原規劃背景與驗收準則；當時的「未來／未實作」描述不代表目前狀態。

## 現況與路線

已對照產品文件、Core service/storage、Mail snapshot、Work Panel model：Core 仍為 shadow Observation/context，Calendar 是 placeholder，沒有本機 schedule owner。

OperatingModel 支持 Core 擁有工作狀態。Roadmap 原先優先既有來源 shadow；本計畫建議本機 schedule 局部採用 Core，不代表整體 R2／R5 完成。批准後隨實作更新階段對應，現在不改寫產品事實。

## 資料 contract

沿用 Core SQLite 及 transaction pattern，不另建 Calendar DB。正式 runtime DB 路徑由設定提供，與 shadow 實驗資料區分；不直接採用研究 DB。

建議新增下列邏輯資料，具體表名在 M0 對照既有 schema 後定案：

- Schedule item：stable ID、owner、類型、標題、有限備註、時間／期限、時區、完成追蹤選項、revision、取消狀態。
- Revision：追加保存 scoped mutation、idempotency key 與時間；current row 和 revision 同交易更新。
- Series exception：series ID + 原定 occurrence identity；單次改期保留 identity。
- Occurrence state：單次完成／略過狀態，不能把一次完成當整個系列完成。
- Notification preferences/deliveries：系列預設與單次覆寫、到期時間、dedup、配送與回報紀錄。

Observation 留給外部觀察，不把可編輯的本機資料硬塞進 details。更新帶 expectedRevision；舊版回 conflict，不 last-write-wins。同 idempotency key 不同 payload 拒絕。

取消保留 tombstone；第一版不提供不可復原硬刪除。先限制欄位大小與查詢頁數，提供 DB 大小診斷；歷史清除另行設計。

## 時間、完成與固定系列

- Timed event 有 start/end，end 晚於 start；datetime 必須 aware。
- 全天用日期 `[startDate, endDateExclusive)`，不假裝成午夜 timed event。
- Deadline 可只有截止時間／日期，不捏造開始時間或占用時段。
- 時間狀態（未開始／進行中／已結束）與工作狀態（待完成／完成／略過）分開。
- 今日行程：`start < tomorrowStart && end > todayStart`。今日午夜剛結束不算今日。
- 日期型 deadline 在當地日期結束後才逾期。跨日安排在期間內列今日，結束但未完成則列「未完成／逾期」，不假装還在進行。
- 已完成可收合查看，不再通知。跨日顯示完整開始／結束日期。
- 系列時區決定 recurrence／提醒，view timezone 決定今日邊界；API 回傳兩者及 view date。
- DST 不存在時間：手動輸入拒絕；系列 occurrence 標記 skipped reason。重疊時間採固定 fold 規則並測試，不讓 renderer 猜。
- 只展開 bounded range／notification lookahead，不無限 materialize。
- 「只改這次」建立 exception；「這次及以後」在原定 occurrence 邊界拆分系列，保存 lineage。
- 「整個系列」更新模板，不重寫已完成歷史。例外無法映射時回 conflict，不能靜默丟棄。
- 未完成 occurrence 以持久化游標分批 catch-up，保留多年逾期查詢；不靠任意 lookback 漏掉舊未完成，也不每次 GET 展開多年系列。
- catch-up 未完成回 coverage incomplete，不宣稱完整空清單。

## API、UI 與 runtime

M0 固定 versioned routes、欄位與 error schema，提供 status/readiness、today/range、CRUD／complete／skip、series edit scope、notification preferences/snooze/dismiss/ack。

GET 為 local read：不 migration、不 provider refresh、不寫入 occurrence、不配送通知。materialization 由 command／scheduler 執行。

Core unavailable 顯示無法取得；只有成功完整的 local view 為零才顯示沒有安排。外部尚未接入不影響本機可用，也不把本機 current 說成外部同步成功。

UI 流程：

1. 今日：全天、進行中／稍後、未完成／逾期、可收合已完成。
2. 七日／日期選擇，使用 Core 範圍投影。
3. 新增：類型、名稱、時間／期限、重複、完成追蹤、通知。
4. 系列編輯先選範圍，呈現影響摘要後提交。
5. 取消明確確認；完成／略過明確按鈕。儲存中防重送，失敗保留草稿。
6. revision conflict 可重新讀取且保留草稿；offline 不假成功。
7. filter/count/today/priority 全部使用同一 schedule identity，不混入 legacy Calendar。

沿用現有設計系統，不重做整個 UI；實作前再讀取適用 frontend skill。

Runtime：

- Launcher 管理 Core，settings 擁有 path/port；M0 查 listener，不預猜 port。
- Core loopback + session authentication；Electron main 提供受限 IPC、輸入驗證。token 不進 renderer／URL／Git。
- readiness 核對 schema、instance、owner，不只 HTTP 200。
- Core 停止不影響 Chat／Mail／Study。
- 使用者 UI 明確提交構成本機該次 payload 的操作確認，不加第二個泛用授權視窗。AI／背景流程不因此取得任意寫入權限。
- 第一版不新增聊天寫入工具、OAuth 或付費生成。

## 通知生命週期

Core 判斷 eligibility，Electron 配送並回報；candidate 不等於已送達。

- 狀態：pending、suppressed、ready、dispatching、delivered、dismissed、snoozed、cancelled、failed、unknown。
- dedup 綁 occurrence、提醒規則版本、channel；改期／停用原子撤銷舊 pending。
- snooze 保留 lineage；完成／取消優先，配送前重查 revision。
- 重啟／睡眠喚醒 catch-up 建議限最近 30 分鐘；更舊項目面板標 missed，不一次全部補發。
- 勿擾期間面板可見；結束後只補仍可行動且在 catch-up window 的提醒。
- delivery claim 使用租約與 fencing，避免多個 shell 或過期 worker 重送。
- OS 通知與 SQLite 不能原子提交，不承諾 exactly-once；送出後 ack 遺失標 unknown，不盲目重送。
- Electron 關閉保留 candidate，不能標 delivered。

## 外部同步後續 contract

此處只保留設計，不在第一版接入。

- Identity 包含 provider/account/calendar/event/instance，local/source ownership 分離。
- 每次 sync 保存 scope/range/generation/page completion/latest attempt/last success/freshness。
- 完整成功的 scope 才能做 absence reconciliation；partial/timeout 不清 last-good。
- 取消 tombstone、移出查詢範圍有明確處理；revision/generation 防舊請求晚到倒退，不只比較 received_at。
- 成功零事件有完整性證據；auth_required/offline 不等於零。
- 不共用 Gmail token、不讓各 producer POST 整份 Briefing。
- 接入時再查官方 API 文件、完成帳號與 scope 設計並獨立驗收。本輪沒有 provider live 證據。

## 里程碑

| 階段 | 工作與驗收 | 驗證表面 |
| --- | --- | --- |
| M0 baseline／contract | 批准後重查 worktree、AGENTS、config、Python、API/schema/error、UI wireframe、正式 DB、備份與 port owner | 可撰寫 deterministic tests 的 contract；建議預設定案 |
| M1 persistence | schema migration、CRUD、revision、exceptions、完成、偏好；冪等、衝突、交易失敗不半寫 | temp/copied DB，旧 schema upgrade、不丟 Observation、unknown schema fail closed、backup/restore |
| M2 projection | today/range/overdue、bounded expansion、catch-up cursor | 全天、跨日、午夜、月末、DST、改期、系列拆分、多年未完成；GET 不寫 |
| M3 service／bridge | Core service、Launcher lifecycle、IPC/auth、timeouts、單實例 | isolated DB/port；拒絕錯 token/未知 action/malformed input/舊 revision；故障隔離 |
| M4 Work Panel | 清單／CRUD／系列範圍／完成／通知設定，退出 legacy Calendar | DOM/screenshots；Mail refresh 不清排程，所有 Today/filter/count 入口無混入，offline 真實呈現 |
| M5 scheduler | due/dedup/quiet/snooze/invalidation/delivery audit | fake clock + 實際桌面通知；重啟、喚醒、ack 遺失、取消與改期競態 |
| M6 adoption | 正式 Launcher identity/DB/loaded source、重啟/crash、文件更新與 rollback | 真實新增至通知完整流程；Chat/Mail/Study regression；source/runtime/product 分開驗收 |

M1–M3 是資料與服務基礎，M4 是第一個可操作版本，M5–M6 完成通知與正式採用；M4 完成不能宣稱全部交付。

## 驗證命令

以下為未來使用；新測試名稱於 M0 定案，不代表已執行。

```powershell
# repo root
.\envs\kuro-llm310\python.exe -m unittest discover -s tests -p "test_kuro_core_*.py"
.\envs\kuro-llm310\python.exe -m unittest discover -s tests -p "test_schedule_*.py"
.\envs\kuro-llm310\python.exe -m unittest discover -s tests -p "test_work_panel_api.py"
# pet-electron
npm run check:renderer
npm run build:renderer
```

依階段選最相關檢查；py_compile/node --check 只列實際變更檔案。新測試必須存在且執行數非零，不能把零測試成功當通過。runtime port/routes 定案後補精確 smoke 指令。

UI 證據包含窄視窗、長標題、鍵盤操作、空／失敗／衝突、跨日與防重複提交；通知需真實桌面配送證據。任何 not_run/pending 不記 PASS。

本輪僅文件 UTF-8 讀回、links、diff check，不跑程式測試/build/runtime。

## 停止修正與回退

- 發現雙 owner、history 被覆寫、unknown 變零、取消後發舊通知，先修復再進下一階段。
- 超出批准範圍（外部授權/寫入、語音、AI 自動操作）另行確認。
- 保留平行變更，不廣泛 reset/kill。
- 關閉 Core schedule integration 後顯示 unavailable、保留 DB，其他 legacy 功能繼續；不 fallback legacy Calendar。
- migration 前備份；舊 binary 不強開新 schema。restore 若會遺失新資料，先說明差異再確認，不自動覆蓋。

## 預計修改面

- `kuro_core/`：schedule、migration、projection、notification。
- Core service entrypoint：檔名 M0 定案。
- `kuro_launcher/`、settings：lifecycle/config/diagnostics。
- Electron main/preload/renderer work-panel：transport、UI、配送。
- `mail_tools_server.py`：局部移除 Calendar ownership。
- tests 與相關文件：實作後更新現況，保留其他工作修改。

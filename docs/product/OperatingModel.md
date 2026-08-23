# Operating Model

本文件定義 Kuro 的目標產品架構、責任邊界與運作模型。它描述要收斂到的系統，不代表目前 repo 已經完整實作。

若本文件和 `ProductVision.md` 衝突，先以產品願景確認方向；若和目前程式不同，應採漸進遷移，不用文件假裝現況已完成。

## 1. 核心架構原則

Kuro 的本體是後方的工作系統，不是 Live2D 桌寵，也不是單次呼叫的 LLM。

- 系統擁有待辦、工作狀態、事件、提醒規則、權限設定與 audit。
- AI Agent 讀取系統提供的資料，負責理解、排序建議、說明與互動。
- 桌寵、角色、語音、Reader 與工作面板是呈現與操作介面。
- 外部專案擁有各自的 domain truth，透過 contract 向 Kuro 提供觀察、狀態與可執行能力。
- AI 的回答不是資料庫，也不能因為說了一句話就改變系統真相。

目標關係：

```text
External Domain Systems
OMI / Learning / News / Mail / Calendar / Future Projects
                ↓ typed observations, states, actions
Integration / Adapter Plane
                ↓ normalized events and capabilities
Kuro Core
Task Store / Attention Queue / Rules / Scheduler / Policy / Audit
                ↓ system-owned work context
AI Manager Layer
understand / explain / recommend / request allowed actions
                ↓
Experience Layer
Work Panel / Pet / Reader / Briefing / Settings
```

角色是套在同一套 Kuro Core 與 AI Manager 上的不同人物表現。切換角色不等於切換工作系統。

## 2. 現況與目標的差異

目前責任仍分散在 Qt Launcher、Open-LLM-VTuber、Electron Briefing store、tool policy 與各種 local state 中。

目標不是立即新增一個巨型 service，而是逐步建立清楚的 Kuro Core contract，讓現有元件改成它的 producer 或 consumer。

| 現況 | 目標 |
| --- | --- |
| Qt controller 同時管理 process、chat、memory、Briefing 與 pet commands。 | Launcher 只負責 runtime orchestration 與診斷；產品工作狀態由 Kuro Core 管理。 |
| Electron Briefing store 同時處理 snapshot、mail、study 與 memory candidates。 | Electron 只呈現與收集操作；task、attention、policy 與 audit 移到 backend-owned contract。 |
| Tool policy 主要是靜態 allow/deny，confirmation mode 尚無完整流程。 | 使用者可依 integration 與 action 設定授權等級，執行前由統一 policy engine 判斷。 |
| AI、Briefing 與各專案各自帶部分狀態。 | Kuro Core 提供統一的工作視圖；AI 不靠 prompt 猜測目前狀態。 |

## 3. Domain / Integration Plane

外部專案負責自己的資料、規則與專業判斷。

它們可以向 Kuro 提供：

- observations：目前狀態與可追蹤事實。
- events：值得重新評估或提醒的變化。
- task candidates：建議建立的工作項目。
- actions：在明確參數與 policy 下可以執行的操作。
- health：來源是否 current、stale、partial、missing、offline 或需要重新授權。

Integration / adapter 負責：

- transport、authentication 與 schema translation。
- 把 provider-specific payload 轉成 Kuro 可理解的 bounded contract。
- 保留 source、observed time、fetched time、status、limitations 與 error。
- 宣告能力是 read、write、send、delete、refresh 或其他 side effect。

Integration / adapter 不得：

- 直接控制桌寵或自行播放提醒。
- 繞過 Kuro policy engine 執行 side effect。
- 把 provider failure 包裝成沒有事件。
- 將自己的 raw payload 變成 Kuro 長期記憶。

## 4. Kuro Core / Work Management Plane

Kuro Core 是產品的工作本體。這是一個邏輯邊界，不要求第一版必須是單一 process 或特定資料庫。

核心責任：

- 統一 Task Store。
- Attention / Event Queue。
- reminder rules、schedule、quiet hours、dedup 與 cooldown。
- 使用者偏好與 per-capability automation policy。
- Briefing snapshot generation。
- action request、confirmation 與 execution status。
- audit trail。
- 對 AI 與 UI 提供穩定的 read/write contract。

Kuro Core 不負責：

- OMI 的市場分析與 freshness。
- 學習專案的課程進度算法。
- 新聞來源抓取與新聞事實判斷。
- 角色 persona、語音 rendering 或 Live2D 動畫。
- 讓 LLM 文字輸出直接成為 authoritative state。

## 5. 統一待辦模型

Kuro 顯示的正式待辦由系統持有。AI 只能透過 Task Service 讀取、提出候選或請求修改。

每個 task 至少要能回答：

- `task_id`：穩定識別。
- `title` 與可選的短說明。
- `status`：待處理、進行中、等待中、完成、忽略等明確狀態。
- `priority`、`due_at`、`review_at` 或下一次應處理時間。
- `source`、`source_ref` 與來源 ownership。
- 建立原因與為什麼值得處理。
- `observed_at`、`updated_at` 與來源 freshness。
- 可採取的下一步與對應 action capability。
- 使用者手動覆寫、規則結果與 AI 建議之間的差異。

Task 可以來自：

- 使用者手動建立。
- 學習、市場、新聞或其他 domain system 提供的 task candidate。
- Kuro rule / scheduler 依明確條件建立。
- AI 根據現有資料提出候選。

AI 建議建立 task 時，預設先形成 candidate。是否直接轉成正式 task，由該來源與 action 的設定決定。

對外部系統已有自身 task lifecycle 的情況，record 必須標示是 Kuro-owned task 還是 source-owned projection；不能在兩邊各自修改後假裝沒有同步衝突。

## 6. Attention 與主動提醒流程

Task 與 notification 是不同概念。發生新聞、市場異動或進度落後時，先形成 attention event，不必立刻建立長期待辦。

標準流程：

```text
Observation / Event
    ↓ normalize + source status
Attention Candidate
    ↓ dedup + importance rule + user settings
Notification Decision
    ↓
Short Headline / Overview
    ↓ user requests details
Reader / Briefing / Conversation Detail
    ↓ optional
Task Candidate / Action Request
```

每個通知至少保留：

- category 與來源。
- severity / importance。
- 為什麼現在提醒。
- observed time 與 freshness。
- dedup key 與 cooldown 狀態。
- 一到兩句短概要。
- 詳細內容入口。
- 可採取行動，以及行動需要的授權等級。

使用者可以在設定中控制：

- 哪些 integration 或 category 可以提醒。
- 最低重要度。
- 工作面板、桌面 notification、角色語音等通知 channel。
- quiet hours、暫停提醒與勿擾模式。
- 相同事件的 cooldown 與每日上限。
- 是否只顯示標題、允許簡短語音，或可直接展開詳細內容。
- 哪些事件可以自動建立 task。

來源不完整或狀態不確定時，Kuro 可以提醒「有狀況需要確認」，但不能自行補成確定結論。

## 7. AI Manager Layer

AI Agent 是 Kuro 的理解與互動層，不是系統真相的 owner。

AI 可以：

- 查詢 Task Store、Attention Queue、Briefing 與授權後的 external tools。
- 把分散狀態整理成今天的優先順序與理由。
- 以目前角色的人格說明概要、回答追問與產生 spoken summary。
- 提出 task candidate、action request 或設定調整建議。
- 在 policy 允許時請求執行 scoped action。

AI 不得：

- 僅靠對話內容宣稱 task 已完成或資料已更新。
- 直接修改 Task Store、Policy Store 或 audit record。
- 自己推斷 domain freshness、補齊 missing 或重算 OMI 結論。
- 把 prompt 當成 action authorization。
- 因角色人格不同改變工具權限或工作事實。

AI 產生的 priority 可以是 advisory signal；使用者明確排序、domain severity 與 system rule 必須保留來源，不能被模型建議靜默覆蓋。

## 8. Automation / Permission Control Plane

產品不採單一全域「完全自動」開關。授權必須依 integration、capability 與 action 分開設定。

每個 action 使用以下等級之一：

| 等級 | 行為 |
| --- | --- |
| `disabled` | 不讀取、不提醒、不可執行。 |
| `observe` | 可以讀取與更新 system view，不主動打擾。 |
| `notify` | 可以依提醒設定主動給出短概要，但不執行 side effect。 |
| `confirm` | 可以準備 action，逐次由使用者確認後執行。 |
| `scoped_auto` | 只在使用者明確設定的條件、範圍與額度內自動執行。 |

Policy 判斷優先順序：

```text
Hard deny / security boundary
        ↓
User capability setting
        ↓
Action-specific rule and budget
        ↓
Runtime health / source readiness
        ↓
AI or scheduler action request
```

高層設定不能覆蓋 hard deny。角色 prompt、UI 參數或單次模型輸出也不能提升授權等級。

每個 `scoped_auto` 設定至少包含：

- integration 與 action type。
- 允許的 target、account、recipient、resource 或 domain scope。
- 觸發條件與允許時段。
- 每次與每日 call / quota / amount 上限。
- 內容、附件、資料範圍或模板限制。
- 設定生效日、到期日與立即停用開關。
- 成功、partial、failure 與 retry policy。
- audit detail 與使用者可查看的執行紀錄。

目前 runtime 尚未完成統一 confirmation 與 audit flow，因此現階段寫入、刪除、發送、發布及大量 quota 仍預設 `confirm` 或 blocked。只有產品能力、UI、policy test 與 audit 都完成後，才能逐項開放 `scoped_auto`。

### OMI 範例

Kuro 可以被設定為定期或事件驅動地呼叫 OMI read-only capability，取得市場摘要與重大狀況，並自動產生 attention 或 task candidate。

- OMI 仍擁有市場 evidence、freshness、decision 與 limitations。
- Kuro 可以控制查詢時間、範圍、budget 與提醒門檻。
- Kuro 不以 `scoped_auto` 名義取得交易權限。
- OMI 回傳 stale、partial、missing 或 provider failure 時必須保留。

### Mail 範例

寄信可以在未來成為 `scoped_auto` action，但不能只設定「允許自動寄信」。至少應限制：

- 使用哪個 account。
- recipient allowlist 或允許的 recipient group。
- 可使用的 template / purpose。
- 是否允許附件。
- 每日寄送上限與允許時段。
- 寄送前是否保留 preview。
- 未知收件人、敏感內容或超出規則時降級為 `confirm`。
- 每封信的內容摘要、recipient、時間、result 與 failure audit。

## 9. Character / Persona Plane

角色只改變：

- 人格與說話方式。
- 聲音、語言、emotion、Live2D 模型與動作。
- 角色專屬的互動偏好與可選角色記憶。

角色不改變：

- Task Store 與 Attention Queue。
- 外部專案連線與 domain truth。
- automation policy、hard deny 與 audit。
- shared work memory、Briefing 與使用者確認結果。

角色切換時，Kuro Core 先提供相同的 current work context，新角色再以自己的方式承接。不得要求 LLM 從 chat history 猜測交接狀態。

## 10. Experience Plane

### Work Panel

產品主入口。讀取 Kuro Core 的今日優先順序、tasks、attention、source health 與待確認 actions。

### Pet

角色常駐、短概要、提醒與自然互動。桌寵是 Kuro 的人物介面，不保存 authoritative task 或 policy state。

### Reader

承載長回答、詳細證據、新聞內容、OMI 分析與附件。

### Briefing

呈現每日與分領域 snapshot。Briefing 是 system view，不是另一份資料庫真相。

### Settings

管理 reminder、quiet hours、channel、integration、capability、automation scope、quota 與角色偏好。設定 UI 只寫入 Policy / Preference Service，不直接修改 tool adapter。

### Launcher / Diagnostics

負責啟動、停止、profile、port、runtime health、logs 與 recovery。長期不作為主要工作面板，也不持有產品 task truth。

## 11. 真相來源

| 資料或決策 | 長期 owner |
| --- | --- |
| 統一待辦與其 lifecycle | Kuro Core Task Store |
| Attention、通知狀態、dedup、cooldown | Kuro Core Attention Service |
| Reminder 與 automation 設定 | Kuro Core Policy / Preference Store |
| Action confirmation、execution status、audit | Kuro Core Action / Audit Service |
| 今日工作視圖與 Briefing composition | Kuro Core，由 tasks、events 與 source health 組成 |
| AI 的解釋、排序建議與 spoken summary | AI Manager；屬衍生輸出，不是 authoritative state |
| 市場資料、freshness、evidence、decision | OMI |
| 學習內容與學習進度 | 對應學習系統 |
| 新聞內容、來源、發布時間與去重證據 | 新聞系統 |
| Mail message 與 delivery result | Mail provider / mail integration |
| 角色 persona、voice、Live2D 與角色表達偏好 | Character config / character memory |
| Shared work memory | Kuro memory service，不隨角色切換 |
| Runtime paths、ports、process profile | Launcher settings / runtime owner |

UI、prompt 與 chat history 都不能成為上述資料的替代真相來源。

## 12. Memory 與工作狀態

至少分成：

- System work state：tasks、attention、action requests、execution results。
- Briefing snapshot：特定日期與時間的短期工作視圖。
- Tool result：來源查詢的 evidence 與一次性結果。
- Shared work memory：穩定的工作習慣、專案偏好與長期決策。
- Character memory：角色表達與互動偏好。
- Conversation / thread context：當次對話延續。

Task 不等於 memory，Briefing 不等於 memory，tool result 也不等於 memory。

任何自動升級成長期記憶的流程，都必須有來源、類型、時間、理由、status 與可刪改方式。角色切換不能複製或分叉 shared work memory。

## 13. 外部整合 contract

新的 integration 至少要宣告：

- identity 與 version。
- capabilities 與 action types。
- read/write/send/delete/refresh side-effect classification。
- schema 與 bounded payload。
- source time、freshness、partial、missing 與 failure semantics。
- health / authentication state。
- rate limit、quota 與 timeout。
- idempotency 或 duplicate handling。
- task / event / action mapping。
- 支援哪些 automation levels。

Frontend 與角色 prompt 不直接呼叫 provider。AI 透過 Kuro action contract 提出要求，由 policy engine 決定是否執行。

## 14. 資料保存與可回復性

Kuro Core 的實體儲存技術可以後續決定，但產品 contract 必須要求：

- Local-first，預設不依賴 cloud 才能讀取自己的工作狀態。
- Schema version 與 migration。
- 寫入 idempotency 與 concurrency protection。
- 可辨識 task、event、notification、action、policy 與 audit 的 ownership。
- 備份、匯出與還原流程。
- 依資料類型清除，而不是只能整庫刪除。
- 發生 partial write 或 crash 時可以恢復到一致狀態。
- Secrets、tokens 與 provider credentials 和一般 state 分離。
- Private state、chat、memory、logs、mail、market/account data、voice assets 不進 git。

自動 action 的 audit 不應記錄 secret 或不必要的完整私人內容，但要足以回答誰、何時、依哪個 policy、對什麼 target 做了什麼，以及結果如何。

## 15. Failure 與降級模型

Kuro 不應把 system healthy 簡化成單一紅綠燈。

至少區分：

- runtime unavailable。
- integration offline / authentication required。
- source stale / partial / missing。
- policy denied / confirmation required。
- action queued / running / partial / failed / completed。
- notification suppressed by quiet hours / cooldown / user setting。
- AI unavailable，但 system tasks 與 work panel 仍可讀。
- TTS / Live2D unavailable，但文字工作流程仍可使用。

AI、角色、TTS 或桌寵失效時，Kuro Core 的 tasks、settings、audit 與工作面板不能跟著失去真相。

## 16. 變更與遷移原則

非平凡修改先判斷 owner：

- Domain integration。
- Kuro Core task / attention / policy / action / audit。
- AI Manager。
- Memory。
- Experience surface。
- Character / voice。
- Runtime / launcher。
- Persistence。

遷移順序應優先：

1. 定義 task、event、action、policy 與 audit contract。
2. 建立 backend-owned Kuro Core 最小實作。
3. 讓現有 Launcher、Electron 與 Open-LLM-VTuber 透過 contract 讀寫。
4. 將 mail、study、Briefing 等散落責任逐步搬離展示層。
5. 加入 per-capability settings、confirmation flow 與 scoped automation。
6. 在相同行為與資料驗證完成後再移除 legacy path。

不要 Big Bang rewrite。新 core path 應先 shadow、比對、保留 rollback，再逐步成為唯一真相來源。

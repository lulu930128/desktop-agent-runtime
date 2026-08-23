# Quality Bar

本文件定義 Kuro 要達到什麼程度，才可以被視為能長期使用的個人工作產品，而不只是可以展示或勉強運作的桌寵 demo。

這些標準同時適用於新版 Kuro 的架構、工作面板、角色互動、主動提醒、工具操作、資料保存與 runtime。它描述的是目標品質門檻，不代表目前 repo 已經全部達成。

若功能無法同時滿足產品價值、資料可信度、安全邊界與可恢復性，應先縮小範圍，不得以隱藏限制或繞過 policy 的方式宣稱完成。

## 1. 產品品質標準

Kuro 達到可長期使用，至少必須同時成立以下條件：

1. **每天打開就有用**：第一屏能直接說明今天最重要的事項、值得注意的變化、待確認操作與下一步，而不是要求使用者先聊天或逐一打開其他專案。
2. **工作狀態由系統持有**：待辦、attention、提醒設定、確認結果與執行紀錄不依賴單次 LLM 回答、chat history 或某個角色才能存在。
3. **角色可以交接工作**：切換人物、聲音或 Live2D 模型後，共享待辦、Briefing、工作記憶、工具權限與今日狀態保持一致。
4. **主動但不打擾**：重大狀況可以主動提醒；一般資訊遵守重要度、quiet hours、cooldown、去重與使用者選擇的 channel。
5. **先概要，再展開**：主動提醒預設只提供短標題、發生原因與重要性，讓使用者決定是否查看詳細內容或執行下一步。
6. **自動化由使用者控制**：每個 integration 與 action 有獨立的授權範圍；寫入、發送、刪除、發布或高成本操作不能因 AI 認為合理就自動執行。
7. **資料不足時保持誠實**：來源 stale、partial、missing、offline、未授權或結果不確定時，畫面、對話與語音都必須保留限制。
8. **局部故障不拖垮整體**：AI、TTS、Live2D、單一 integration 或外部服務失效時，既有待辦、設定、工作面板與診斷資訊仍可讀取。
9. **重新啟動後可以承接**：正常關閉、異常終止或 Windows 重啟後，應恢復可持久化的工作狀態，不重複提醒、重複寄送或遺失確認結果。
10. **問題可以被理解與修復**：失敗要有清楚狀態、時間、來源、可採取的恢復動作與足夠的本機診斷線索。

「可長期使用」不要求所有規劃功能一次完成，但已標示為可用的功能必須達到上述相應門檻。尚未完成的能力應明確標為未提供、實驗中或受限，不得用靜態假資料偽裝完成。

## 2. 核心體驗驗收

### 2.1 工作面板

工作面板是產品主入口。預設視圖應在不需要捲動大量內容或先發問的情況下，回答：

- 今天最重要的三到五件事是什麼。
- 每件事為什麼現在重要。
- 建議的下一個最小行動是什麼。
- 哪些項目需要使用者查看、決定或確認。
- 學習、市場、新聞與其他已啟用來源目前是否有重要狀況。
- 哪些來源尚未更新、資料不完整、離線或需要重新授權。

每個正式 task 或 attention item 至少要顯示或可展開取得：

- 明確標題與目前狀態。
- 來源與最後觀察時間。
- 重要性或排序理由。
- 下一步或詳細內容入口。
- 是否為系統事實、來源建議、規則結果或 AI 建議。
- 若有 side effect，所需授權等級與目前執行狀態。

面板不能把工程診斷、原始 log、完整 JSON 或大量低重要度事件放在主要資訊層。詳細證據與診斷應在 Reader、展開區或 Diagnostics 中查看。

### 2.2 資訊層級與操作節奏

介面資訊層級固定為：

1. 現在需要注意什麼。
2. 為什麼重要。
3. 建議做什麼。
4. 來源、限制與詳細證據。

主要操作應在一到兩個明確步驟內完成。高風險操作可以多一步確認，但確認畫面必須說清楚 target、內容摘要、影響、policy 依據與是否可撤回。

Loading、empty、offline、stale、partial、error、permission required、confirmation required 與 completed 必須有不同且穩定的視覺狀態，不能全部退化成空白、紅字或同一個 spinner。

### 2.3 角色、桌寵與語音

- 角色是工作系統的人物介面，不得遮擋主要工作內容或搶走主要操作焦點。
- 使用者即使關閉桌寵、語音或 Live2D，仍可完成核心工作流程。
- 角色切換只改變 persona、聲音、表情、動作與表達方式，不改變共享工作事實與權限。
- 重要提醒的語音先說短概要；長報告、來源、表格、URL、程式碼與診斷內容交給畫面或 Reader。
- 語音內容不得比畫面更確定，也不得漏掉會改變判斷的 stale、partial、missing 或失敗警告。
- TTS、翻譯或 spoken rendering 失敗時，文字結果仍須完整可用，且不能阻塞 turn completion。

### 2.4 主動提醒

一則可接受的主動提醒必須：

- 能說明觸發來源、發生時間與現在提醒的理由。
- 先給一到兩句短概要，不直接朗讀完整內容。
- 提供查看詳細內容、稍後處理、忽略或調整提醒設定的入口。
- 遵守 category、severity、channel、quiet hours、cooldown、每日上限與去重設定。
- 同一事件更新時能合併或標示變化，不以多則近似通知轟炸使用者。
- 資訊不足時用「需要確認」表達，不自行補成確定結論。

被 quiet hours 或 cooldown 抑制的提醒仍應留下可查看的狀態，但不應事後一次大量補播。Windows 關機期間無法即時執行的提醒，啟動後只能依明確的 catch-up 規則補做，不能假裝曾即時送達。

### 2.5 設定與個人化

- 使用者可以依 integration、category、capability 與 action 分別設定 `disabled`、`observe`、`notify`、`confirm` 或 `scoped_auto`。
- quiet hours、提醒 channel、重要度門檻、cooldown、每日上限與角色偏好必須可查看並可修改。
- 設定畫面要顯示目前生效值、來源與影響，不能只提供無法理解的技術 key。
- 關閉一項 integration 後，Kuro 不再主動查詢或提醒；既有資料是否保留或清除要明確說明。
- 高度個人化可以使用本機設定，但 secrets、私人路徑與憑證不得硬編碼進 source 或角色 prompt。

### 2.6 桌面 UI 基準

- 以 Windows 桌面長時間使用為基準，支援常見縮放比例與合理的視窗尺寸。
- 窄視窗不能只靠縮小字體塞入內容；必要時改為分欄收合、分段或詳細頁。
- 文字不得被截斷到無法理解，按鈕、badge、tooltip 與時間狀態不得互相遮擋。
- 鍵盤焦點、對話框、確認操作與主要導覽要可辨識；不能只靠顏色傳達嚴重度或成功失敗。
- 動畫與角色效果應協助理解狀態，不應造成持續閃動、頻繁位移或阻礙閱讀。
- Work Panel、Reader、Briefing、Pet 與 Settings 應使用一致的狀態名稱、時間語意與操作文案。

## 3. 技術品質標準

### 3.1 架構與 ownership

- Task、attention、notification、policy、action 與 audit 必須有明確 owner 與穩定 contract。
- AI Manager 只能透過 contract 查詢、建議與請求操作，不能直接修改 authoritative storage。
- Electron、Qt、Live2D、Reader 與角色 prompt 是 consumer／interaction layer，不得成為 domain truth 或安全政策的唯一實作位置。
- 外部 integration 保留自己的 domain ownership；Kuro 只正規化狀態、排入工作視圖並受控地呼叫能力。
- 同一份正式狀態只能有一個 authoritative owner。若遷移期間存在 legacy 與 new path，必須標示 primary、shadow、同步方向與 rollback 條件。
- 跨程序 contract 要有版本、輸入驗證、bounded payload、可預測錯誤與向後相容策略。

### 3.2 持久化與一致性

- 正式 task、policy、confirmation、execution status 與 audit 不得只存在記憶體、UI state 或 chat history。
- 儲存格式需要 schema version；migration 必須可測試，失敗時不得靜默丟棄資料。
- 建立 task、接收 event、排入通知與執行 action 要有 idempotency 或等價的重複保護。
- concurrent update、重複啟動與 crash recovery 不得造成 task 回退、重複通知或重複 side effect。
- 使用者手動修改與來源更新衝突時，要保留 ownership 與衝突狀態，不能由最後寫入者靜默覆蓋。
- 必須有可操作的備份、匯出、還原與依資料類型清除流程；不能只能整庫刪除。

### 3.3 Runtime 與服務生命週期

- Launcher 以實際設定檔與啟動 profile 啟動正確 executable、working directory、environment 與 port。
- Ready 不能只代表 process 存在；至少要驗證 listener、protocol／health contract 與必要的代表性功能。
- 已存在的 listener 必須確認 ownership 與 runtime identity，不能只因 port 可連線就沿用未知 process。
- Start、Stop、Restart、profile switch 與應用程式退出應是 bounded、可重複且可診斷的操作。
- 任一子服務失敗時，要指出失敗層級與可恢復方式，不做廣泛 process kill 或無限 restart loop。
- canonical port 與 runtime path 由設定 owner 決定；程式、捷徑、文件與產生設定不得各自維護不一致 fallback。

### 3.4 外部整合

- 每個 integration 必須宣告 identity、version、capabilities、side-effect class、timeout、quota、health 與 authentication state。
- 所有外部呼叫都要有 timeout；retry 必須 bounded，且只用於可安全重試或具 idempotency 的操作。
- partial failure 要保留已成功與未成功的範圍，不得只回傳模糊的成功或失敗。
- Integration offline 或 provider unavailable 時，既有 snapshot 可繼續顯示，但必須標示時間與 stale 狀態。
- 新 integration 先從 read-only／observe 開始，完成 contract、policy、audit 與 UI 後才逐級開放通知或 side effect。

### 3.5 錯誤處理與 observability

- 使用者可見錯誤要說明「哪個功能、目前影響、是否保留既有資料、可以做什麼」，不能只顯示 exception。
- 開發與診斷資訊至少包含 component、operation、timestamp、result、duration 與可串接同一次流程的 correlation identifier。
- Log 不得包含 token、password、完整 private message、未遮蔽的敏感附件或不必要的完整 provider payload。
- 跳過、降級、重試、去重、cooldown、policy deny 與 confirmation required 都應留下可追蹤原因。
- 產品畫面不可用單一「系統正常」掩蓋個別 integration、資料 freshness 或功能降級。

### 3.6 相容性與可維護性

- 優先保留現有 public route、WebSocket event、設定 key 與 local state；breaking change 需有 migration 與明確切換計畫。
- 新 abstraction 必須對應清楚 ownership 或降低重複，不能只為包裝單一呼叫增加層次。
- 設定應有安全預設、範例與啟動時驗證；未知 key、缺少必要值與錯誤型別要給出明確訊息。
- Fork、vendor code 與 Kuro-owned source 的邊界要可辨識，避免後續升級時無法判斷自有改動。
- 重要 contract、policy 與 persistence 行為需要 targeted tests；不能只靠人工操作或 prompt 約束。

## 4. 資料與可信度標準

### 4.1 狀態語意

Kuro 至少要能區分：

- `current`：資料在來源定義的有效時間內。
- `stale`：有舊資料，但已超過可接受時間。
- `partial`：只有部分範圍或部分欄位成功。
- `missing`：預期資料不存在或尚未取得。
- `offline`：來源或 runtime 目前無法連線。
- `auth_required`：需要重新授權或憑證不可用。
- `unknown`：資訊不足，無法判斷狀態。

`unknown`、`missing` 與 `0` 不得互換；沒有事件、尚未檢查與檢查失敗也不得呈現成相同結果。

### 4.2 來源與時間

會影響優先順序、提醒或行動的資訊至少保留：

- source / integration identity。
- source reference 或可追溯 identifier。
- source-observed time。
- fetched / received time。
- status、limitations 與 error reason。
- schema / contract version。

畫面可以先顯示人類可理解的相對時間，但詳細資訊必須能查看準確時間與 timezone。跨日提醒、due date、學習日界線與排程要使用明確 timezone，不依賴模糊的「今天」。

### 4.3 優先順序與 AI 建議

- 使用者設定、正式 task 狀態、domain severity、system rule 與 AI 建議要保留各自來源。
- AI 可以解釋與提出排序，但不能靜默改寫使用者明確設定或來源事實。
- Kuro 要能回答「為什麼這件事排在前面」，並指出是規則、期限、重大事件、使用者偏好或 AI 建議。
- 缺少足夠資料時，AI 應提出需要補查的項目，而不是產生看似完整的優先順序。

### 4.4 Task、Briefing、tool result 與 memory

- 正式 task 是 system work state，不是對話記憶。
- Briefing 是有時間點的衍生 snapshot，不是永久真相。
- Tool result 是帶來源的一次性 evidence，不因出現在回答中就成為長期記憶。
- Shared work memory 與 character memory 必須分開，角色切換不能複製或分叉共享工作事實。
- 長期記憶寫入需保留來源、類型、理由、建立時間、狀態與刪改方式。
- 刪除或停用記憶後，後續 prompt、檢索結果與角色回應都不得繼續使用舊副本。

## 5. 權限、隱私與自動化標準

### 5.1 基本安全邊界

- 預設 local-first；本機控制 API 維持 loopback，除非另有經過驗證的 authentication、transport 與暴露範圍設計。
- Secrets、tokens、cookies、provider credentials、私人信件、chat history、memory、logs、模型、聲音素材與 runtime state 不得進 git。
- Prompt、角色設定、UI event 與外部 payload 都不能提升 action permission。
- 未註冊能力、未知 action、超出 scope、超出 quota 或 policy 無法判斷時，預設拒絕或降級為需要確認。
- Audit 要足以追蹤操作，但只保存必要資料，避免複製完整私人內容。

### 5.2 Confirmation 品質

需要確認的 action，在執行前至少顯示：

- 要做什麼與使用哪個 integration／account。
- target、recipient、resource 或影響範圍。
- 內容摘要與重要參數。
- 是否可撤回、是否會消耗 quota 或產生外部影響。
- 目前觸發原因與套用的 policy。

確認必須綁定當次 action payload。使用者確認 A 不能被重用來執行內容已變更的 B，也不能因對話中的一般肯定句而視為授權。

### 5.3 `scoped_auto` 開放條件

任何能力只有在以下項目全部完成後，才可從 `confirm` 升級為 `scoped_auto`：

- action contract、target scope 與 idempotency 已定義。
- 設定 UI 能查看、修改、停用與設定到期日。
- 單次／每日 quota、時段與內容限制可被 policy engine 強制執行。
- 有 dry-run 或 preview 能力，或已說明為何該 action 不適用。
- 成功、partial、failure、timeout 與 retry 都有測試。
- Audit 可以回答觸發者、policy、target、時間、結果與失敗原因。
- 使用者可以立即停用，且停用後不再排入新 action。
- 已完成實際 runtime acceptance，不只測試 mock 或 UI 開關。

不符合其中任一條件時，維持 `confirm` 或 disabled。

## 6. 降級與恢復標準

| 故障 | 最低可接受降級 |
| --- | --- |
| LLM unavailable | 工作面板、既有 tasks、attention、設定與來源狀態仍可讀；不能產生新的 AI 排序或解釋。 |
| TTS / spoken rendering unavailable | 完整文字照常顯示，標示語音不可用，不阻塞對話完成。 |
| Live2D / Pet unavailable | Work Panel、Reader、Briefing 與 Settings 仍可操作。 |
| 單一 integration offline | 其他來源照常工作；保留最後成功時間並標示 stale / offline。 |
| Kuro Core 暫時不可寫 | 不得假裝 task 或設定已儲存；保留輸入或提供可重試方式。 |
| Action 執行結果未知 | 不得自動重送可能造成重複 side effect 的操作；先查詢 provider／audit 狀態或交由使用者確認。 |
| Persistence migration 失敗 | 停止寫入新 schema，保留舊資料與可理解的 recovery 指引。 |

恢復後要重新取得各 component 與 integration 的真實狀態，不能直接把故障前的 UI 狀態改回 healthy。若資料可能已部分寫入或 action 結果不明，必須進入 reconciliation 流程。

## 7. 驗證分級

驗證要對應改動風險與真正的使用者表面。低層測試通過不代表桌面產品已完成；runtime health 通過也不代表畫面、角色或工作流程可用。

### Q0：文件與純規格

適用：Markdown、prompt、註解與不影響 runtime 的模板。

- UTF-8 讀回。
- Markdown 結構、相對連結與 Mermaid 語法人工檢查。
- `git diff --check`。
- 不啟動 GUI、LLM、TTS 或 Electron。

### Q1：局部實作

適用：單一 helper、局部 Python／JavaScript／TypeScript 邏輯、低風險 config。

- 對應 syntax／compile／typecheck。
- 最接近的 targeted unit test。
- 空輸入、缺檔、malformed data 與主要 error path。

### Q2：Contract、資料與 policy

適用：task、attention、persistence、memory、tool policy、settings、API／WebSocket schema 或 integration adapter。

- Q1 全部項目。
- Contract 與 regression tests。
- schema version、migration、idempotency、duplicate 與 concurrency 測試。
- allow、deny、confirm、quota、unknown capability 與 nested parameter policy 測試。
- partial、stale、missing、offline、timeout 與 retry 測試。
- 確認 private state、secret 與 raw sensitive payload 未進入 repo 或 log。

### Q3：Runtime integration

適用：Launcher、service lifecycle、port、process、Electron main、conversation runtime 或跨程序整合。

- Q2 中與改動相關的項目。
- 驗證 exact executable、working directory、environment、listener owner 與 effective config。
- Probe 真實 health／protocol，不只檢查 process 是否存在。
- 驗證 start、stop、restart、重複執行、異常子程序與 shutdown。
- 檢查代表性 API／WebSocket／control endpoint 與錯誤回應。
- 若使用既有 runtime，確認它實際載入本次 source 與 contract version。

### Q4：使用者可見體驗

適用：Work Panel、Reader、Briefing、Settings、Pet、Live2D、語音、通知與互動流程。

- Q3 中與該流程相關的項目。
- 實際開啟使用者會看到的畫面，檢查 loading、empty、正常、partial、offline、error 與 confirmation 狀態。
- 檢查常見視窗尺寸、文字溢出、焦點、overlay、角色遮擋與主要操作。
- 實際完成代表性流程，例如查看今日重點、展開詳情、忽略提醒、切換角色與恢復狀態。
- 語音相關改動需驗證可見文字、spoken summary、emotion、音訊播放與 failure fallback。
- 以 screenshot、DOM／UI state 或可重現操作紀錄保存必要證據。

### Q5：外部 side effect 與自動化

適用：發送、發布、刪除、外部寫入、付費 quota 或 `scoped_auto`。

- 先取得使用者明確授權，再進行真實 side effect 驗證。
- 先通過 Q2 至 Q4 的相關項目與 dry-run／preview。
- 使用受控 target、最小範圍與最低必要 quota。
- 驗證 confirmation payload binding、idempotency、取消、timeout、unknown result 與 reconciliation。
- 驗證 audit、立即停用、quota cap 與 failure notification。
- 不得在 production／真實帳號上用大量測試資料做破壞性驗證。

## 8. 功能完成條件

一項非平凡功能只有在以下條件成立時才可標記完成：

- 對應到 `ProductVision.md` 的明確使用者價值。
- owner、真相來源、輸入輸出 contract 與 non-goal 已說明。
- 正常、空白、缺資料、離線、錯誤、權限與恢復流程都有定義。
- persistence、migration、idempotency、privacy 與 side-effect 風險已依範圍處理。
- 使用者可見狀態不會掩蓋 stale、partial、missing 或失敗。
- 依本文件完成相應 Q-level 驗證，且驗證的是實際變更採用的 runtime。
- 文件、設定範例與診斷方式已同步。
- 已知限制有清楚 owner、影響與後續處理方式，不以「之後再補」代替必要安全門檻。
- 沒有把 private state、generated output、dependency folder 或 secret 納入 Git 變更。

若功能只完成 source code、mock、靜態畫面或單一 happy path，應標示為 prototype、shadow 或 partial，不得標示為產品完成。

## 9. 不可接受的捷徑

- 用角色 prompt 保存 task、權限、提醒規則、資料 freshness 或 domain logic。
- 讓 AI 的自然語言回答直接成為 task completed、設定已更新或 action 已執行的證據。
- 把正式工作狀態只放在 frontend、Electron `userData`、chat history 或 process memory，卻宣稱可跨角色與重啟承接。
- 為了看起來主動而取消去重、quiet hours、cooldown、重要度門檻或使用者選擇權。
- 直接朗讀完整新聞、報告、URL、程式碼、原始 JSON 或大量診斷內容。
- 用空白、`0`、預設值或舊 cache 掩蓋 unknown、missing、stale、partial、offline 或 provider failure。
- 讓展示層重新推導外部專案的資料真相，或用 frontend wording 修補 backend contract 缺口。
- 只因 endpoint 回 `200`、process 存在、port 可連或 build 通過，就宣稱整個桌面功能完成。
- 在未確認 listener owner、effective config 與 runtime identity 時沿用未知服務。
- 用廣泛 kill、無限 retry、靜默 exception、清空資料或重建整庫處理可診斷的故障。
- 用單一全域「完全自動」開關取代 integration／capability／action 層級 policy。
- 讓一次確認授權後續不同 payload，或把一般對話中的「好」視為高風險操作授權。
- 在沒有 idempotency、quota、audit、停用開關與 runtime acceptance 時開放 `scoped_auto`。
- 將 secrets、logs、chat、memory、mail、私人附件、聲音素材、模型權重、runtime config 或 Electron state commit 到 Git。
- 進行 Big Bang rewrite，卻沒有 contract、shadow comparison、rollback 與使用者可見 regression 驗證。
- 為了統一畫面而複製另一個產品的定位、資料模型或 domain 能力，導致 Kuro 失去自己的工作助理核心。

## 10. 品質例外與技術債

暫時未達標可以被接受，但必須同時具備：

- 明確標示目前是 prototype、partial、legacy 或受限模式。
- 說明使用者影響與不能依賴的部分。
- 指定 owner、替代流程與後續 milestone。
- 不跨越資料遺失、秘密外洩、未授權 side effect 或錯誤事實呈現等硬性邊界。

已知技術債不能透過 UI 隱藏。當 legacy path 與目標架構並存時，文件、Diagnostics 與測試必須能回答目前實際採用哪一條路徑。

## 11. 新版 Kuro 的首輪品質門檻

新版 Kuro 的第一個可用版本，不需要一次完成所有 external integration 或高階自動化，但至少要做到：

- 以 Work Panel 作為主要產品入口，Launcher 回到 runtime 管理與診斷角色。
- 建立最小 Kuro Core contract，讓正式 task、attention、settings 與 action status 不再由角色或展示層持有。
- Today 視圖能顯示三到五個優先項目、來源狀態、排序理由與下一步。
- 至少一個真實外部來源能以 read-only contract 提供 observation，並正確呈現 current、stale、partial、missing 與 offline。
- 主動提醒具備概要、展開、去重、cooldown、quiet hours 與 channel 設定。
- 切換角色後能承接相同工作狀態，關閉 TTS 或 Live2D 後核心流程仍可用。
- 寫入、發送、刪除、發布與高成本操作維持 `confirm` 或 disabled，並有可理解的確認狀態。
- 工作狀態可跨正常重啟保留，且有最小備份、migration 與 recovery 證據。
- 完成相應 Q2、Q3 與 Q4 驗證，包含真實 runtime 與使用者可見畫面。

達到這些條件後，才進一步擴充更多 integration、統一 confirmation queue、`scoped_auto` 與進階角色表現。

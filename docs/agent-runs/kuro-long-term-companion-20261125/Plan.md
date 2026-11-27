# Kuro Long-term Companion — 長期個人 AI 載體／Memory 2.0 工程計畫

- 日期：2026-11-25
- 專案：desktop-agent-runtime（C:\project\desktop-agent-runtime）
- 狀態：Planning；Source 健檢完成至下述範圍，未開始實作、測試、資料遷移或正式部署。
- 任務建議：GPT-6.2 Astra（gpt-6.2-astra）／high／Standard；待使用者授權實作後由 Codex Bridge 進行，Reviewer 獨立驗收。不得自行換模型、啟用 Fast 或覆蓋既有 WIP。
- 依據：本次 2026-11-25 Kuro Source 健檢、既有產品與架構文件、Memory Core overview 實際回應，以及 ChatSorter 公開設計的前輪查閱。外部服務的內部演算法及實測效能尚未獨立驗證。

## 0. North Star 與不可降級的完成條件

讓 Kuro 成為能持續使用數年的 local-first 個人 AI 載體：即使對話中斷、重啟、跨日、切換角色、替換模型、更新程式或搬遷電腦，使用者的歷史、已確認事實、偏好、事件經歷、角色關係及合法可共享的工作脈絡仍能正確延續；長期使用不因歷史累積而持續增加每輪重掃成本。

Kuro 不是把所有過往對話直接塞進 Prompt，也不是用記憶取代正式系統。AI 模型、人格與呈現層可更換；資料與經驗應成為可保存、可遷移、可檢索、可追溯的長期資產。產品仍以 ProductVision.md 的個人工作經理為核心，兼顧自然陪伴與長期互動。

完成的判準必須同時包含：
1. 新對話、同一長對話的早期內容、跨角色的共享資訊及跨日事件能從正式 Chat 路徑正確取回，且在無關問題時不亂帶背景。
2. 新舊事實能維持版本、時間與來源；過期狀態不當成現況，歷史事件不因過期而消失；對外部 domain truth 按需回查 owner。
3. 在使用者選定的授權模式下，有價值的日常資訊可自動形成記憶，而不是每個普通事件都永久卡在候選；原有明示保存、人工管理與停用／刪除仍正確。
4. 去除任意的全庫 active 上限；同一既有處理流程能完成所有符合資格的歷史回填與索引更新，具 checkpoint、可重試及明確失敗終態，不要求使用者逐段反覆指令。
5. 系統可重啟、升級、換模型、備份及還原；可從原始資料重建衍生索引，不因失敗覆蓋或遺失正式記憶。
6. 以可重放測試及正式 Qt → Runtime → LLM → Qt 的實際結果證明較現況改善；局部單元測試、API 回應、Job 成功與 source ready 不等於整體完成。

## 1. 範圍、原則與決策邊界

本輪主軸：記憶形成、情節摘要、檢索、時間語意、跨角色／專案共享、持久化與遷移、可觀測性、日常管理 UI、長期容量與評估；保留與記憶流程相連的必要 runtime、啟停及 error handling。

不擴大成完整桌寵重寫、語音／Live2D 視覺改版、Core Today／Schedule 重設計、全新工具系統、雲端 SaaS、多租戶、模型訓練或通用安全審計。其他已知產品未驗收項目依原 owner 繼續追蹤，不以本計畫宣稱全部已修復。

沿用 Open-LLM-VTuber Conversation Runtime、Repository、History、Retrieval、Lifecycle、Qt Memory UI 及既有 MCP capability。不要新增平行 Memory Manager／獨立 API Server／重複 Writer，除非經量測證明現有能力無法合理延伸。可引入必要的新資料表或模組，但要收斂至唯一 owner。

既有強制契約：AGENTS.md、docs/product/{ProductVision,OperatingModel,QualityBar,Roadmap}.md、docs/architecture/{RuntimeArchitecture,OwnershipMap,DataLineage,CorePersistence,ResearchBoundary}.md；尤其 docs/agent-runs/mcp-trust-security-m0/Contract.md 的來源、內容綁定授權、候選不可覆寫正式記憶等規則。M0 明定不開放 scoped_auto 保存。此計畫建議新增可選自動記憶模式，是對原契約的明確後續變更提案，不是當下已授權切換。實作可先建立該能力及測試；正式開啟前由使用者選定適用類型、來源及範圍。保留 explicit/manual 與現有確認模式；不要為低風險情節記錄無端設置逐筆人工批准。外部正式資料不因本次升級取得寫入權限。

所有額外 Batch、TTL、Timeout、模型／成本、並行與容量限制須說明來源（平台、契約、實測或假設）、效益與代價。回填任務整體完成邊界不等於單批請求邊界。測試規模是實驗樣本，不是生產上限。

## 2. 現況證據／缺陷與架構風險

以下路徑除特別註明外，均相對於 Open-LLM-VTuber/src/open_llm_vtuber/。行號是 2026-11-25 查閱快照，實作開始前以實際 checkout 及符號重定位。

| ID／優先級 | 已見 Source 證據 | 影響與改善 |
| --- | --- | --- |
| MEM-01 P1 功能缺口 | character_memory_manager.py:475–659、708–710；_extract_memory_candidates、build_memory_write_plan、_upsert_memory：regex／固定分數，非 explicit/manual 的候選待確認 | 一般自然陳述、偏好變化與經歷難形成可用的結構化記憶。屬原政策刻意設計與新目標衝突，不能描述為意外 bug。以語意擷取、來源語意、可選自動政策改善。 |
| MEM-02 P1 Source 已證實限制 | character_memory_manager.py _compact_store（約 920–1000）：active 超過 80 即依 importance、updated_at 停用其餘 | 長期記憶容量與單輪 Context 預算混用。取消全庫固定上限；不可把既有 disabled 一律恢復，需區分人工停用、取代、舊 compact 等原因，無證據則保留狀態。 |
| MEM-03 P1 功能缺口 | basic_memory_agent.py:186–247 _pack_short_term_memory；chat_history_manager.py:222–225 summary_short 只是首句 72 字元截取 | 無真正滾動 L2 摘要；超出短期窗口的本 thread 早期資訊又在自動歷史檢索中被排除，可能遺失當前任務脈絡。原始 History 尚在，不等於模型能使用。 |
| MEM-04 P1 架構／容量風險 | conversation_history_index.py:61–163、245–260：search 每次 sync，逐檔讀取所有同 conf_uid 的歷史、全量 upsert、全量重建該 namespace FTS；character_memory_sql_index.py 同類全量同步 | 每輪工作量隨歷史增長，額外 DB writer contention；目前未量測 Runtime 耗時。改增量索引與啟動修復／重建，不在正常 read path 全量寫入。 |
| MEM-05 P1 架構缺口 | character_memory_repository.py store_path(conf_uid)；manager _upsert_memory 將 scope_id 設 conf_uid；retriever 僅以 scope priority 計分 | global_user/project/thread 等標籤並非正確的共享實體識別。需有真正的 user/character/project/thread ID 與共享檢索。 |
| MEM-06 P2 檢索風險 | character_memory_retriever.py KeywordMemoryIndex、character_memory_sql_index.py search：關鍵字＋FTS＋固定重要度／可信度；未見 embedding；無 overlap 亦可有高分；updated_at 存在加 2 分 | 無關資訊可能注入，抽象語意與同義詞召回不足。新增 hybrid 候選召回、排序與關聯閾值的實測校準；穩定 persona 指令另有明確 Context 用途。 |
| MEM-07 P2 檢索風險 | basic_memory_agent.py:439–467、877：以本輪 request_text 查長期記憶，12 筆／900 估計 token，歷史 4 則／520；conversation_history_index.py:270–320：LIMIT 120 未 ORDER BY rank，set terms 切片；history hit 片段截斷 | 短追問、跨輪指涉、多跳及長歷史排序可能失真。先過濾合法 scope／候選，再穩定排序與相關性判斷；補同 thread 舊段召回、鄰接原文及來源。固定 Context 容量重估，不盲目增大。 |
| MEM-08 P2 時間／版本風險 | character_memory_manager.py CharacterMemoryEntry、_default_subject_key、_find_existing、_find_conflicting_memory：created/updated、字串包含、同 subject/key | 相對日期語意可能失效；同義陳述未必去重，變化的文字 key 可能不構成矛盾，粗略 key 也可能錯誤合併獨立事實。需 canonical fact identity、validity 與版本鏈。 |
| MEM-09 P2 停用／刪除語意缺口 | manager infer_memory_delete_plan、_apply_memory_delete_plan：recent turn 實際比對 history_uid；_memory_matches_target 使用字串或任意 term overlap；history index 獨立召回 | 指定上一輪可能停用整個 thread 的記憶；自然語句可能誤判刪除目標；停用後仍可能從原始歷史召回。統一意圖／操作語意、turn_id 與來源抑制／刪除傳播。尚無正式 runtime 重現。 |
| MEM-10 P2 持久化／恢復風險 | character_memory_repository.py：atomic replace、process lock、snapshot digest，衝突 raise；chat_history_manager.py store_message 直接重寫 JSON；single_conversation.py:575–665 部分 response 可能落盤，finalize 後處理記憶，未見完整 response_complete 條件 | 不撤除有效的原子寫入保護；需確認重啟、並行、磁碟失敗、未完成 turn、候選重試、History 完整性，避免錯把未完成回答視為結果。是否已在真實環境出錯未驗證。 |
| MEM-11 P2 運作／可觀測性缺口 | 基本 prompt 組裝失敗只記 warning；History／Memory 預覽與管理有既有 UI，完整加工覆蓋與跨層 trace 未確認 | 使用者需知道記憶是否處理完成、來源／版本、未處理缺口、索引錯誤和重建狀態。 |
| MEM-12 P2 評估缺口 | 已見 tests/test_character_memory_manager.py、test_mcp_m0_memory.py、test_paos_local_memory_routing.py，有 lifecycle、索引、migration、digest 等測試；未查得完整 longitudinal benchmark | 保留既有 regression，新增可重放長期記憶與真實產品驗收。不能只做主觀聊天示範。 |

證據層級：上表是 Source 可觀察行為／架構推論，不是全部已重現的 production incident。前輪未跑測試、未讀取私人聊天正文或本地正式記憶內容、未量測正式 Kuro Runtime。Memory Core overview 的可見範圍在 2026-11-25 15:12 台灣時間回傳 active records 25、archived 1、pending candidates 5、FTS5 25/25 healthy；此為獨立 Memory Core 的服務快照，非 Kuro 本地記憶數量，不能推定 Kuro→Memory Core 正式路由已完成 E2E。

## 3. ChatSorter 參考方向與差異

外部案例只作公開概念參考：三層短期／摘要／長期事實記憶、訊息重要性、事實擷取、時間衰減、相對日期解析、矛盾處理、語意檢索與長期 benchmark。先前查閱來源：
- https://chatsorter.com
- https://chatsorter.com/changelog
- https://github.com/codeislife12/Chatsorter
- https://pypi.org/project/chatsorter/
- https://pypi.org/project/chatsorter-local/

完整 backend、prompt、公式、授權與效能沒有獨立驗證；不把其自報 benchmark 當成產品能力已驗證，也不要求使用商業 API 或複製未授權程式碼。

| 概念 | Kuro 採用方向 |
| --- | --- |
| L1／L2／L3 | 延伸成 L0 原始歷史＋L1 工作記憶＋L2 情節記憶＋L3 語意記憶 |
| 定期摘要 | 依話題、事件、完成 turn、上下文成本形成可續接區段，避免機械截斷 |
| 自動擷取／重要性 | 結構化 extractor，來源、信心、時間、可確認的權限模式；保留人工管理 |
| Decay | 分離相關性、有效性、重要性，衰減檢索優先度而非刪除歷史 |
| 相似度 | 既有 FTS＋本機多語 embedding＋rerank，測試是否值得 rerank |
| 矛盾處理 | 穩定 fact identity、validity、版本鏈、證據，不能由模型斷言直接覆寫 |
| LoCoMo | 公開 benchmark＋Kuro-specific 合成 replay＋正式使用案例；相同模型／資料比較 |

## 4. 目標架構與 Ownership

```text
Qt Chat / Pet interaction / existing tools
  → Conversation Runtime (stable turn / event identity)
  → History owner: L0 raw, provenance, timestamps, completion status
  → existing memory pipeline
      ├─ L1 Working Context (recent dialogue, current task state reference)
      ├─ L2 Episodic (derived segments, milestones, summaries, source span)
      └─ L3 Semantic (scoped facts, preferences, relationship, versions)
  → canonical repository + derived incremental FTS / vector index
  → query-aware Context Compiler (scope + intent + time + provenance + budget)
  → LLM
  → Qt text / existing speech and pet presentation

Memory Core / OMI / Study / PAOS / Kuro Core
  → existing read-only or authorized contracts
  → Context Compiler or existing tool orchestration (not a second writer)
```

| Owner | 正式責任 |
| --- | --- |
| Chat History | 原始對話、turn id、來源時間、完成／中斷狀態；作為可回放證據 |
| Runtime Memory Repository | Kuro 個人互動記憶、L2/L3 canonical 資料與版本 |
| Runtime derived index | FTS、embedding、可重建索引、加工 checkpoint；非另一份真相 |
| Context Compiler | 組裝本輪需要的記憶及證據，不持久改寫 domain truth |
| 外部 Memory Core | 正式個人紀錄、實體、版本、關聯；按需透過原 MCP，Kuro 不擅自複製或雙寫 |
| Kuro Core | Schedule、Today、Work、Attention 等正式工作狀態 |
| OMI／Study／PAOS 等 | 各自即時領域資料；需要現在狀態時回原 owner |
| Qt / Pet | 管理、查看、呈現；不建立第二套 memory policy / ranking |

L0/L1/L2/L3 是邏輯表達，不要求四個 DB 或新增 service。短期緩衝不需要持久化成第二份正式記憶。Repository 先保留現有 JSON 的 canonical 語意；依大規模寫入、查詢、備份及 crash 測試比較原子 JSON＋增量索引與單一 SQLite canonical。若證據支持 SQLite 遷移，可在既有 Repository 介面內改底層，必須有單一 writer、schema version、migration、backup、rollback；不允許兩個正式來源長期並行。

### 4.1 建議資料契約（設計，不鎖死實作型別）

- Identity：record_id、scope_kind、scope_id、user_id、character_id/project_id/history_uid/turn_id（依適用範圍），fact subject/predicate/entity key；角色專屬關係不得被共享指令覆蓋。
- Provenance：source_kind（user_statement、manual、tool_verified、assistant_claim、derived_summary 等）、source_ref、source span／event id、evidence、observed_at、extractor/model/version、source revision。
- Time：recorded_at、event_at／事件區間、timezone、時間精度與原始相對詞、valid_from、valid_to、last_confirmed_at；retrieved_at 屬 trace／衍生欄位，不得令舊事實突然生效。
- Lifecycle：active／pending_confirmation／superseded／disabled／pending_delete 等既有狀態加必要 reason；historical 與 current 語意獨立，保留舊版本、關聯、使用者授權和修改紀錄。
- Quality：importance、confidence、evidence quality、relevance 分離；檢索排序與是否正式保存分離。數值／單位／否定／假設／不確定性保真，不從摘要捏造日期或因果。
- L2：episode_id、主題、時間範圍、事件順序、已做／未做／阻擋與決策、source spans、coverage watermark、summary revision。不同角色互動記憶保留來源，合法共享的使用者／工作脈絡可接續。
- 索引：stable source ID + revision + embedding model/version，對同一輸入可重建／去重。刪除、修訂、停用要同步到所有衍生讀取面。

### 4.2 記憶形成與生活化使用

現有 explicit/manual 路徑保留；語意 extractor 可結合本地模型或既有 LLM provider，輸出 schema 驗證的候選，不直接生成最終真相。先以測試量測低成本模型的繁中、日文、英文能力，再選模型，不綁死特定模型或雲服務。

區分以下來源及處理：
- 使用者直接說明的穩定偏好、一般經歷、個人目標：在其選定 scoped_auto 模式時，可直接保存具 provenance 的事實／事件，允許日後更正或撤回。
- 暫時情緒、當前工作進展：優先保存有時間的 episode／status，不把一次情緒變成永久人格。
- 角色互動關係：可形成角色專屬 episodic memory；人格設定、核心指令不從普通對話無條件改寫。
- 助手產生的建議、假設、未核對的完成宣告：只保留為 conversation evidence／unverified claim，不自動變為權威事實。
- 外部工具數據、行情、資產、學習進度：保持來源／時間及查詢限制，不能自動複製為權威長期狀態。

初始回填使用歷史完整證據重新加工符合範圍的記錄，對過去沒有保存許可的資訊不得擅自升為已核准 L3；能否在新模式下加工既有歷史由使用者設定與既有保留／忘記契約決定。L2 摘要是衍生歷史，需遵守同一來源及抑制語意。日常加工應能補完，不因一輪失敗永久丟失。

### 4.3 檢索、時間與 Context 編譯

- Query 使用當前問題＋必要近期上下文／實體／時間指涉，短追問能指向之前事件；需要歷史時搜尋同 thread 早期區段及其他允許 scope。
- 先按實體作用範圍、lifecycle、抑制狀態及 current/historical intent 限定候選，再 FTS 精確召回與多語向量語意召回；保留查詢股票代號、檔名、日文、繁中同義詞的能力。
- 比較 FTS-only、embedding-only、hybrid 與可選 rerank；使用 benchmark 調整排名、相關性拒答門檻、去重、相鄰來源擴展及 token allocation。不能把任何固定 top-k 當成整體記憶容量。
- 分離 persona／明確長期指令、當前 task context、歷史事件與外部 evidence，不讓無關高 importance 資料挤占回答。
- current 問題優先使用仍有效的版本；historical 問題可回查 superseded／已完成事件（但不得回查使用者明確禁止提取或已刪除的記憶）。
- 衰減只影響暫時資訊的檢索優先度；不直接刪除長期經歷，也不以衰減判斷工具資料是否 fresh。時間不確定則保留區間與原始表述。
- 每輪記錄選擇的記憶 ID、來源、排名理由、版本、budget、耗時及 fallback／缺口，不保存額外完整私密正文至診斷。
- LLM context/window 能力依實際 provider/profile；現有 4200/900/520 為歷史預設，不視為固定契約。根據精確 tokenizer 或量測誤差、工具 schema、圖片、輸出預留及品質選擇配置。

## 5. 工程階段（同一計畫持續至目標完成）

### M0 — Baseline／Contract（先做，之後依驗證結果調整）
- 查 AGENTS、M0 既有安全契約、Git HEAD/dirty diff、active runtime/source/config/model、正式 memory/history root、Qt Memory consumer、已存在的 jobs/processing/indexing capabilities。
- 只取得必要的聚合 metadata，不讀取與任務無關的私人內容；區分既有未驗收項目與新 regression。
- 固定實驗 corpus、模型／sampling、現有讀寫／查詢／重啟 baseline；量測 histories/message 數量、索引覆蓋、延遲、成本、候選流向與既有 active/disabled 狀態。
- 產出現況與目標 contract、缺陷與驗收對應、schema/ownership 選擇理由、不可重用或保留的原因。若既有能力已可滿足某一項，直接沿用並驗證。
- 驗收：正式路徑及可重放基準可定位；不以 baseline 假裝修復。

### M1 — Persistence／Index Foundation（P1，先消除長期使用硬障礙）
- 移除 _compact_store 的 80 筆全庫 active 限制，保留非 active 狀態與可稽核 lifecycle；調整管理 UI，不只顯示前 80 筆。
- 修正 History write 原子性及 repository conflict handling，沿用 lock/digest；若失敗須由原 owner 恢復或留下可重試狀態，不重複寫入、不吞掉已成功回答。
- 增量更新 character/history FTS（新增、修改、刪除、rename、reset、startup reconcile）；以持久 watermark/revision 追蹤索引未完成，避免正常查詢全量掃描與全量 DB writer。
- 對大語料測量 bind parameter、SQLite lock/transaction、磁碟與 CPU 瓶頸；處理所有符合資格的資料，不靠小批限制中斷總任務。
- 保留完整 rebuild/repair/export，必要時使用現有 repository contract 遷移 canonical storage。已有來源不可讀時不得以空資料覆寫。
- 驗收：超過 80 筆仍有效；初次全量 build 後無變更查詢不重掃；新增一段、刪一段只處理必要增量；大量資料及 crash recovery 可重跑且最終一致。

### M2 — Identity／Lifecycle／Source Correctness（P1）
- 真正 user/character/project/thread identity 與明確 scope filter，將現有 conf_uid store 的已知身份遷移至正式 ID；未知不得猜造。
- 跨角色共享一般使用者與 project 記憶、隔離角色互動；同專案／不同專案正反案例測試。
- stable fact key、來源優先、版本鏈、時間欄位與證據，保留矛盾未解狀態；新版本不能覆寫人工 provenance；錯誤與取消 turn 不當成已確認結果。
- 修正忘記意圖分類、recent turn 精準匹配、相似關聯與歷史提取抑制；分開停用 current／禁止 retrieval／永久刪除操作及其影響。避免重新索引或重新摘要使明確刪除內容復活。
- 驗收：換角色取回共享事實，不串角色專屬記憶；不同 scope 不混淆；使用者更正、刪除與重建之後讀回符合語意。

### M3 — Retrieval／Context Compiler（P1）
- 在現有 MemoryIndex/CharacterMemoryRetriever/ConversationHistoryIndex 邊界內加入多語語意索引及混合排序，保留可用的 FTS 精確搜尋；本機 embedding 優先評估，模型配置／版本可更換及重建。
- 修正無關候選、LIMIT 排序、term 穩定性、短追問、同 thread 舊內容及跨段證據；對來源可追溯、去重及 token allocation 進行統一組裝。
- 保留獨立外部 Memory Core on-demand read，若需提升主動召回，使用現有工具／讀取 contract，避免自動同步複製正式紀錄；外部失敗明示可降級範圍。
- 驗收：語意改寫、精確名稱、繁中／日文／英文、無答案、多跳及時序案例對照 baseline，實測檢索品質及延遲，無關記憶不能因 importance 單獨進入一般召回。

### M4 — L2 Episodic Memory／Consolidation（P1）
- 在既有 History owner 的 completed/persisted turn boundary 形成可追溯區段，採既有 processing/job owner 的可恢復流程；先處理新訊息，舊歷史增量補完。
- 依話題、事件邊界、對話延續及 Context 容量形成 summary；保留 unresolved decision、數值、否定、時間、失敗與原始 message spans；可更新／合併衍生摘要且不破壞原文。
- 舊段超出 L1 時仍可由 L2/raw fallback 找回；摘要失敗不阻塞日常對話，記錄 checkpoint 及原因，恢復後繼續。
- 驗收：長對話早期關鍵資訊、隔數週再續接、摘要含數值與反證、異常中斷後重跑無重複。所有可用歷史達到 coverage 或具明確不可處理原因。

### M5 — Semantic Memory Formation（P1）
- 將 Regex 由唯一擷取路徑改成明示指令／快速規則之一；加入 schema-guided semantic extractor、候選 scoring、fact identity、duplicate/conflict 與來源時間解析。
- 加入可設定模式：現況 explicit/manual＋review；按使用者批准類型／來源範圍的 automatic；以既有 UI 管理候選、修訂、批次審閱與關閉。授權模式需與 lifecycle digest、M0 contract 一起更新，不能偽造 manual approval。
- 對一般日常語句、偏好演變、長期經歷自動形成可檢索記憶；對假設、工具結果、助理未確認宣告避免當成權威事實。
- 驗收：使用者已選定的模式不依賴逐筆審核，完整端到端形成、檢索、更正；保留手動停用／刪除與未批准候選隔離。

### M6 — 長期生命週期、日常管理與可維護性（P1/P2）
- 依 current validity、event time、類型及檢索相關性處理 temporal decay；歷史不被無故清除。
- 延伸 Qt Memory／History／Diagnostics 現有 UI：分層/搜尋、filter、來源及原文跳轉、狀態/版本/衝突、加工進度與失敗原因、重新處理、記憶模式設定、匯出/還原。避免另外建立平行 UI，避免每次互動都有大量審核通知。
- 完成可攜式備份清單（歷史、正式記憶、必要 schema／設定、source refs、索引版本）；衍生索引可選保存或重建。可在新目錄/新電腦還原，私密資料與 secrets 不提交 Git；不得把 model-specific embedding 當唯一資料。
- 針對日常交互保留既有 Chat、tool evidence、speech lanes／角色切換／Today 正常行為；Memory 失效時短期對話仍可用且顯示限制。
- 驗收：停用模型／索引損壞、換模型／換角色、重啟及新目錄 restore 後，歷史與可用記憶能承接，不重複、不遺失。

### M7 — 歷史遷移、正式 Runtime 採用與長期驗收（P1）
- 取得當次實作/部署授權後，先做 dry-run inventory、備份、schema 與 counts/identity/revision 對帳；使用者確認記憶自動化／歷史回填的適用範圍後，以同一 job 完成所有符合資格的可用歷史。
- 以可恢復 checkpoint 保存 processed / failed / excluded / remaining 與 reason；允許批次、合理併發與 retry，但不把切片成功當成完成。若來源損壞或無授權，列明不可補及重試條件。
- 依原 owner 實際 build/deploy、核對 installed/running source 與 config；透過 Qt 正式聊天流程測試新記憶形成、跨對話／跨角色召回、時間版本、停用／刪除、外部查詢、語音及工具 regression。
- 做長時段 replay/soak 及冷啟、大量歷史、並行讀寫、備份還原測試；短期測試只證明當下的可觀測性，不宣稱已實際運作數年。
- 驗收：完成第 0 節所有成功條件，核心缺陷消除，資料對帳通過、正式路徑讀回、相同流程可重跑。未測 runtime 或需要使用者桌面實機操作時，保留 Unverified，不宣稱完成。

## 6. 驗收與 Benchmark Protocol

對照相同 corpus、模型版本、sampling、工具條件及評分準則。先保存 baseline，再比較每階段變更，保留每題輸入、預期證據 ID、結果、失敗分類、版本與耗時。對 LLM judge 以規則可核對題／人工複查抽樣校準，禁止把單次最佳分數當結論。

| 評估維度 | 測試與量測 |
| --- | --- |
| Recall / Precision | retrieval Recall@k、Precision@k、MRR／nDCG（如適用）、是否找到 gold source spans；跨對話、同 thread 舊段、同義詞、多跳 |
| Answer quality | single-hop／multi-hop／temporal／contradiction／abstention，exact fact/numeric accuracy、grounded correctness、false memory rate；既有與新版逐題差異 |
| Scope / Lifecycle | user/project/character/thread 正反案例；角色切換、舊新版本、停用與刪除後重建不復活、原有批准與版本保留 |
| Memory formation | 抽取 precision/recall、duplicate/false-merge rate、完成事件與未確認 claim 區分、候選累積、加工成功率及缺口原因 |
| Latency / Resource | 首 token 延遲、retrieval P50/P95、全 turn、增量寫入、回填吞吐、CPU/GPU/RAM/VRAM/DB 大小、模型 token/embedding/摘要總成本 |
| Persistence | 原始/衍生資料對帳、schema migration、checkpoint 續跑、並行讀寫、crash/restart/rebuild/backup/restore、版本切換 |
| Product | 正式 Qt + 現有 runtime，模型／角色更換，Memory UI 管理，Chat/Voice/Tools/Today 回歸；每個成功結果都有 evidence |

測試 corpus：公開 LoCoMo（確認授權與版本後使用）、自行建立的繁中/日文/英文合成情節／時間／專案／角色／否定案例，以及當次另有授權的真實使用流程。未經授權不將私人歷史轉為外部 benchmark 或上傳第三方。既有 tests/test_character_memory_manager.py、test_mcp_m0_memory.py、test_paos_local_memory_routing.py、history index、Qt Memory、conversation/MCP 相關測試均依實際改動繼承或重跑。

建議規模樣本：1k、10k、100k messages，超過 80 筆 active、長 thread、跨角色與大量歷史初始回填；依實際本機容量追加代表性規模。此為量測梯度而非硬上限。索引增量更新的驗收直接看 read/write operation counts，不只耗時。

品質標準：資料不遺失、錯誤 scope 不混入、明確禁止召回不復活、錯誤助手 claim 不升為正式資料、授權範圍正確、原流程可重跑等 deterministic case 必須通過。其餘準確率、延遲、資源與成本以 baseline／重複試驗決定合理改善門檻；必要的 trade-off 由使用者選擇，不能捏造目標數字或用平均分掩蓋重要 case regression。

## 7. Migration / Rollback / Operational Semantics

- 記錄來源 Git/dirty patch、實際 runtime identity、effective config、資料根目錄、schema versions、資料備份 hash、回復說明。不得將真實 history、memory、secrets 或原始 diagnostics 放進 Git。
- 使用隔離 synthetic replay/harness 做失敗實驗；依既有 ResearchBoundary 避免 worktree 不等於 runtime/DB 隔離。一般開發不新增無必要安全層或限制。
- 初始 backfill、重建索引、migration 任務具穩定 identity、watermark、source revision、idempotency、resume、失敗原因。若進行時有新對話，須 reconcile 至最新提交版本，不需每次整庫重做。
- 遇 SQLite/IO/LLM failure 依 owner 的可重試語意恢復；不能用新候選反覆覆寫已確認記憶；明確不可補來源單獨列出。
- 切換時只有一個 canonical writer。若舊資料庫仍可供 rollback，標明 shadow/read-only，不能雙向寫入。rollback 需能安全處理切換後新增對話／記憶（保留 journal、兼容匯出或正向修復），不得以直接覆蓋舊備份丟掉新資料。
- 當新 retrieval 未達標，可回復舊檢索實作，但不應刪除新增合法記憶；索引可重建。故障中使用原始歷史與短期記憶時清楚標示 degraded。
- 實際新機或新目錄還原：資料、schema／設定、角色／專案身份與必要依賴可遷移，確認沒有依賴原絕對路徑。中央 Voice 與外部 domain services 照既有 owner 管理。

## 8. 預期修改位置／交付清單

| 路徑或既有模組 | 修改方向 |
| --- | --- |
| character_memory_manager.py | 移除固定 cap；抽取、scope/identity、事實合併、時間/lifecycle、來源語意 |
| character_memory_repository.py | canonical persistence、revision、atomic conflict recovery、migration/restore |
| character_memory_retriever.py | query-aware hybrid、scope/validity、排序與 trace |
| character_memory_sql_index.py | derived index 增量更新、embedding index contract |
| conversation_history_index.py | 增量 indexing、query correctness、L2/raw spans、重建 |
| chat_history_manager.py / chat_event_manager.py | stable turn identity、atomic history、completed/interrupted provenance |
| character_memory_lifecycle.py / 既有 migration | 保存授權與狀態語意、版控及明確撤回 |
| agent/agents/basic_memory_agent.py | L1／L2／L3 context、query intent／follow-up、工具與記憶 evidence |
| conversations/single_conversation.py 等既有入口 | 正確 turn completion、非阻塞可恢復加工、實際讀回及事件 |
| mcpp/server_registry.py、tool_catalog_manager.py 等 | 確認外部 Memory Core 讀取邊界，按需整合，不擴大寫入權限 |
| kuro_launcher/memory_support.py、memory_panel.py、既有 Qt controller | 依現有 API/管理能力顯示層、記憶模式、進度、來源、備份與錯誤 |
| tests/、docs/architecture/、docs/product/ | 新 regression、replay、benchmark、migration 與更新產品契約 |

不要求上述檔案全部變更；依 source 根因及實際 owner 決定。避免複製同樣的 ranking/packing/classification 到 manager、UI、索引各處；清查同名 legacy helper 是否仍可到達正式路徑，能收斂就收斂。

交付：本 Plan、必要的 Contract/SourceBaseline、Progress/Evidence、Benchmark 可重放結果、Migration/Restore runbook、實作 Diff／tests、Runtime/Qt acceptance 及最終 Reviewer 判定。每階段分開標明 Completed、In Progress、Pending、Blocked、Unverified，以及繼承證據與失效條件。

## 9. Codex Handoff 與使用者決策

Objective：依第 0 節完成 Kuro Long-term Companion 的記憶與長期運作升級。先從正式 consumer 反推現有 source/owner，再落實 M0–M7；計畫中的缺陷優先級可依新證據調整，不得縮小成功條件或用局部 PASS 封版。

建議模型：gpt-6.2-astra / high / Standard。Execution mode 依當次使用者授權及既有 Bridge 能力決定。已有相同工作則續接，不無故建立重複 job；未開始實作前維持 Planning。無法使用指定模型時回報原錯，不暗中替換。

待使用者決策（不影響 M0–M4 的設計與隔離驗證）：
- 正式自動記憶範圍：建議一般偏好、經歷、個人目標與可辨識的使用者陳述可自動保存，核心指令、未確認助手結果與外部權威資料維持獨立契約；可逐類設定，預設正式啟用策略未改。
- 是否允許用既有私人歷史做本機摘要／事實回填，以及哪些資料類別排除。不得重新啟用已明確停用或要求遺忘的內容。
- 模型成本／本機資源取捨：M0/M3 量測後提出可用選項，優先本機 embedding 及可替換的 extractor；不預設新增付費服務。
- 正式 deployment、資料遷移、實機驗收的執行授權；本文件未授權實際修改正式資料。

當前狀態：Plan 已整理；尚未建立 Codex job、未修改程式、未執行測試、未改 Runtime／資料或寫入外部 Memory Core。此文件是可供後續實作的工程規格，不是封版驗收或完整 source audit 的終點。

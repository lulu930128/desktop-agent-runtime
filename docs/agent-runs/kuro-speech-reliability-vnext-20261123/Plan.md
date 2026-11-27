# Kuro Speech Reliability VNext — 自然口播、技術內容分流與長篇播放
> Codex 可自主設計的工程方案（Design Only）
>
> 日期：2026-11-23（Asia/Taipei）
> 專案：C:\project\desktop-agent-runtime
> 基線：main / HEAD c2b3e64c27caaec8c2cba5b213444ddce0d79e03，dirty worktree（讀取時約 170 個 changed entries，實際動工前重查）
> 狀態：僅設計，沒有程式修改、測試執行、Build、Runtime 採用或桌面 E2E 成功聲明
> 關聯既有工作：docs/agent-runs/kuro-tts-reliability-20261103/；docs/agent-runs/kuro-concise-tool-speech-20261105/；docs/agent-runs/kuro-multilingual-speech-20261031/

## 0. 不可降級的最終目標

讓 Kuro 成為**平常可以直接使用、穩定發聲的桌寵工作助理**：

1. 對話與 Tool 回答的完整 Display 始終正確保留；日常情境中應該朗讀的內容能自然且完整發聲，程式碼、網址、JSON、Log、表格等預設留在畫面，不因其中一小段技術內容使其他正常語音全部靜音。
2. 使用者明確要求詳細說明、長篇朗讀或繼續說時，不能被歷史短摘要字數／三段上限偷偷縮成兩句；長篇需按可運行的語音工作流完成，真正失敗才呈現未完成段落與原因。
3. 口播不能虛構事實、反轉「成功／失敗、已驗／未驗、過期／最新、可以／不可以」、錯報關鍵數字、停損及工具實際執行結果；**不能以無止境增加保守詞典／拒播規則來達成此目標**。
4. 使用者願意支付額外 LLM Token、延遲或首次長語音生成成本，以實際完成率、穩定性、自然度為優先；不再把「不用額外模型／只修一次／一定要 110 字」當作不可改契約。
5. 驗收必須走正式使用者路徑：Qt／Conversation → LLM/Tool → Speech 規劃/修復 → Central TTS → WS → Electron playing/ended/ack；Source、targeted tests、mock、真實後端、正式桌面端分開記錄。

**不在本任務內**：重新設計 OMI 或 Mail 商業邏輯、調整 Tool Policy、重做 Today、Live2D 美術、另建全新 Agent 系統、立即改成 GPT-Live。若實作中發現共同根因，先附確切 Source/Runtime 證據，再決定是否擴大。

## 1. 已有的能力與既有成果：必須重用，不要從零重寫

Kuro 已有：
- 同回合 Display＋私有 Speech Footer，SpeechLaneParser、SpeechPolicyEngine，並且已修過自然改述誤拒播（semantic_unverified）。
- 可只針對 Speech 追加模型重寫、不中斷原 Display／Tool／History 的 recovery。
- TTSTaskManager 依序合成/發送，中央 GPT-SoVITS、WebSocket、Electron 音訊佇列與回合 request_id、播放回報。
- Speech timing／狀態觀測、取消後孤兒音檔清理、純文字仍可用的降級能力。
- 2026-11-05 歷史測試已取得 12/12 次真實後端有效短語音、一次 Pet 真實 WAV 播放完成；當時仍有正式 Qt/LLM 新版採用與完整 E2E 的未驗證範圍，不能以其宣稱目前長篇已修好。

**工程原則**：優先延伸目前的 conversation/speech/TTS owner；不要為了學 Pipecat／LiveKit 而再創一組 Queue、TTS Manager、服務、Fallback Agent 或第二套 History。

## 2. 現行 Source 的確切問題與待驗證假設

| 編號 | 位置／實際行為（工作樹 Source） | 評價 | Codex 要查的問題 |
|---|---|---|---|
| S1 | conversations/speech_presentation.py：validate_semantic_lane() 逐段驗證，只要一個 segment 無法通過便 return 空 Speech，整個 lane 失去發聲機會 | Confirmed design gap | 哪些確定衝突才該阻擋整個語意群？哪些技術內容只應局部 skip、改述或重寫？ |
| S2 | 同檔 filter_speech_lane()：正則將路徑、網址、Markdown 特徵和技術符號視為整份語音禁止項；日文 locale 還要求至少有一個假名 | Confirmed design limitation | 誤拒自然技術解說或純漢字日文時，如何區分「不能直接唸的片段」與「可自然口述的技術名稱」？ |
| S3 | conversations/speech_recovery.py：summary 原設計偏向 55–85 字、最多 110 字；20 秒修復期限及一次修復，超長但合法可能再縮短 | Confirmed legacy trade-off | 可否依使用者意圖／實測負載允許更完整口播或多輪修稿？不能固定用短句冒充完成長篇需求。 |
| S4 | conversations/conversation_utils.py：_natural_speech_chunks() 固定最多三組；句子少於三句時可能將很長文字原封不動交 TTS | Confirmed defect/risk | 用實際中央 TTS 能力與自然句界作自適應拆段，確保每個工作單位可合成、又不破壞否定和價格角色。 |
| S5 | conversations/tts_manager.py：同一 speech_group 一個分段失敗就將後續分段標 skipped_after_failure | Confirmed behavior | 可否用內容依賴與播放進度決定延續／修復／停止，避免一段失敗導致無關段落全部消失？ |
| S6 | conversations/conversation_utils.py：finalize_conversation_turn() 固定 90 秒等待播放完成回報 | Unverified long-form risk | 適用長篇音訊時，播放完成是否可能超時、跨回合或被清理？調整應來自音訊長度／進度，而非盲目換大 timeout。 |
| S7 | tts/gpt_sovits_tts.py + utils/stream_audio.py + pet-electron/renderer/src/backend/backend-client.ts：中央一次回傳完整 WAV，再 Base64 裝入 WS JSON；Pet 以完整 WAV 建 Audio | Confirmed architecture trade-off | 首聲延遲、長段容量與傳輸負荷實測如何？先使現有 WAV 路徑可用，真正瓶頸出現再考慮中央原生 streaming。 |
| S8 | conversations/single_conversation.py：Speech 在完成 Display／最終 Speech Lane 後才排入 TTS | Confirmed latency design | 能否先改善完成率，再視需要讓「已確認可口播的片段」提前生成？不可為早說而早於 Tool 結果錯報成功。 |

以上並非宣稱每一點都是當次斷音的 Runtime 根因。真實原因須從 trace 找到：
- footer missing / malformed；
- semantic rejection / repair；
- TTS 合成 none / busy / timeout / WAV validation；
- sender queue / WebSocket delivery；
- Electron playing / ended / failed / ack。

現有 Regression tests（先閱讀、重用，再新增必要案例）：
- tests/test_speech_semantic_alignment.py
- tests/test_multilingual_speech.py
- tests/test_first_speech_latency.py
- tests/test_concise_tool_speech.py
- tests/test_tts_reliability_phase1.py
- tests/g3_presentation.test.cjs

## 3. 建議的產品與技術方向（設計空間，不是指定演算法）

### 3.1 同一份事實，不同呈現

Display 是供閱讀的正式完整答案；Spoken 是依使用情境轉成可聽語言的結果。不能以 Speech 成功而竄改 Display，也不能因 Speech 異常而抹掉完整回答。

為了設計討論，可把片段的處置概念化為三類：
- **SPEAK**：可自然唸的結論、正常聊天、必要數字和限制。
- **DISPLAY_ONLY**：原始程式碼、完整 URL、原始 JSON、繁密表格、Log、Trace；即使不唸仍完整保留在畫面。
- **REPHRASE**：把資料表、工具輸出、技術步驟轉成自然口語，保留關鍵結論和來源限制。

這是語意上的處置類型，不強制 Codex 實作同名 enum 或新的中介 schema。若現有 Speech Footer＋必要 metadata 已足夠就沿用；若需要版本化 Segment Contract 才能穩定處理也可提出並驗證。

例：Display 含「錯誤可能在重連流程」＋程式碼＋「尚未 Runtime 驗證」；Speech 應唸原因與未驗證狀態，程式碼留畫面。不能因含一個路徑把全部變成 unavailable；也不能直接刪路徑後拼接成改變邏輯的句子。

### 3.2 模型理解優先，程式做確定性的結構處理與關鍵事實檢查

保持語意路徑具彈性，請 Codex 比較：
- **A. 同輪雙 Lane（先沿用）**：改善模型生成 Speech 的要求與 Segment／Anchor 語意，容許個別片段修復。
- **B. Post-Display speech renderer**：先取得完整可信 Display，再另用一輪或多輪 LLM 專門產生口播；使用者接受額外 Token，若它顯著提高成功率和自然度，可以採用。
- **C. 混合式**：同輪正常輸出；出現 missing、格式錯誤、不自然、過度冗長、局部技術 payload 時才進 renderer／repair。非 AI 結構切分可先減少無謂模型工作。

選 A/B/C 的依據應是實測可用性、自然度、延遲與代碼複雜度，不是歷史成本偏好。盡量在既有 Conversation owner 增量調整，不另建平行 Tool/Agent 管理層。

**不應**用不斷增加 Regex、特殊詞表、固定字數和整段拒播達成「看似完全無誤」。Regex/AST 適合辨識格式與確定的非法 payload；LLM 更適合產生自然口播與上下文改述。數字角色、否定、成功／失敗、stale／unknown、未實測等決策性事實應維持可驗證來源，不允許為了發聲而捏造。

### 3.3 分級處理問題，不把所有錯誤當成靜音理由

由 Codex 設計合適的分類：明確不正確、不能判斷、可修復格式問題、技術細節只需不唸、TTS／傳輸故障。

偏好流程：
1. 合法且自然 → 直接發聲；
2. 局部純技術內容 → 留 Display／略過或自然改述；保持相鄰語意通順；
3. 有疑義但可取得全文與工具證據 → 使用模型重新表達需要的語意，重新核對；
4. 明確錯價、反轉否定、虛稱工具成功 → 不播放錯誤內容；優先生成正確版本，再判斷是否必須停止；
5. 合成或播放端真的不可用 → 保留文字，明確回報哪些段落未播，等待使用者操作或既有服務恢復。

不能以固定「詳細內容請看畫面」取代本來應完整朗讀的結果；只有使用者想聽概要或確實內容不適合口播時才可以。

**語音模式應看意圖**：日常提醒短概要；一般問答自然適中；使用者要求詳細／繼續說／全文朗讀時充分發聲。不把原本 summary 的 110 字偏好提升為整體硬上限。

### 3.4 長篇語音可完成，而不是固定三段

延伸既有 _natural_speech_chunks 和 TTSTaskManager：
- 先測量中央 TTS 對不同字數、單句長度、跨行／數字／標點及音訊時長的實際表現，再選動態分段策略。
- 允許多於三段；段數與每段長度由內容、Provider 能力及實測資源決定。
- 分段不可切壞引用、否定、因果、價格／停損的對應關係；必要時用模型將一段長文改寫成多個自然可合成單位。
- 對每段標識 turn／segment、是否必須與前段連動、已合成／已送達／已播放；恢復策略應依真實狀態，而非一律殺掉同組尾端。
- 先以現有中央 WAV/WS/Pet 實作可工作的可靠流程；真實首聲或容量瓶頸確認後，才獨立決定是否擴充 Streaming Contract。
- 原有 cancel、跨回合不重播、音檔清理、Qt 文字顯示繼續有效。

### 3.5 Token、Timeout、重試與防禦的取捨

**使用者決策：願意較高 Token 成本、更多模型修稿、較長首次生成時間；重點是使用者能真正聽到完整、可信、自然的內容。**

Codex 可以調整／移除「僅一輪修稿、20 秒、110 字、三段、90 秒」等歷史數值，但要說明它們源自哪裡、原來防的是什麼、實際改變對完成率／延遲／品質的影響。不要任意新增一個更低的新硬上限、固定短切片或多層 Gate 取代修根因。

不以額外黑名單、複雜狀態機、全面的 deny policy、重複 checker、第二套 manager 作為預設答案。能用既有 owner 的少量必要狀態解決，就不要繞一大圈。

仍需維持基本正確性：中斷不誤播下輪、單次含副作用的外部工作不盲重送、結果未知不假稱成功、文字與來源證據不變。這些是功能一致性，不是要求新增額外安全審核架構。

## 4. 應優先驗證的正式 Consumer Path

Qt Chat／Pet 使用者輸入
  → agent/tool continuation 最終 Display（若有工具先完成）
  → 同輪 Footer 或專用 Speech renderer
  → Speech 局部處置／必要語意驗證／repair
  → 有序 Segment 合成（Central TTS）
  → Audio payload／WS
  → Electron audioQueue、playing、ended、ack
  → Qt/Pet 顯示正確終態，History 保留完整 Display。

要求有**可串接但不記錄私人全文**的觀測：turn_id、segment_id、speech source route、驗證/修復結果、TTS 開始與完成、WAV 時長、WS audio sent、Pet playing/ended/error、是否完成全段及必要失敗原因。採既有 Log/metrics Owner；不要把不同 process monotonic 時鐘直接相減。

## 5. 驗收條件：使用者真正聽得見才算完成

### A. 正常與局部技術內容
- 普通聊天、日文學習、工具研究、混合中日文提問 → 合乎該角色的日文自然口播；Display 保留全文。
- Display 有 Python code block、路徑、HTTP URL、JSON、Markdown 表格及一段正常結論 → 不唸 raw payload，但正常結論與決策性限制仍能朗讀。
- 「API」「Node.js」「HTTP 503」、單獨漢字日文等可自然口述的技術詞彙，不因簡單正則或假名檢查整段靜音。
- 原始錯價、反轉成功／失敗、沒有工具結果卻宣稱查證完成的語音，不得發出；有修復手段就修復再播，不把合法其他內容一概扼殺。

### B. 長篇與播放穩定
- 有句號、無句號、長引用、密集數字、五段以上自然解說，以及超過目前 90 秒等待的長篇音訊，均用實測有能力支撐的工作流朗讀到底或有明確部分失敗終態。
- 中間一段確定失敗，能證明前面已播、後段是繼續／待補／停止何種結果；不得發出錯誤的 completed ack，也不得把局部失敗冒充已完成。
- 開始下輪、打斷、取消、Pet 短暫失聯／恢復，不會把過期的 WAV 誤播或重複朗讀已聽到的內容。
- 失敗時文字功能可用；顯示有意義的未發聲範圍，不使用空白沉默／通用模板掩蓋失敗。

### C. 測試與驗證分層
- **先 baseline/repro**：在現行 code 下重現至少語意整段拒播、超長單段、fail-stop 尾段略過；保留原始測試與 Runtime 證據差距。
- **Source/tests**：覆蓋 validator、repair、分段、合成失敗、播放隊列、回合取消、真實 Markdown/code 區段、數值與狀態、語系。
- **實際 TTS**：在受控執行條件下測 short/medium/long 的中央 GPT-SoVITS，記錄成功率、分段時長、音訊格式/長度與失敗原因；不把 HTTP 200 當播放成功。
- **正式 E2E**：確認新版實際安裝與 PID/Config/Model，經真 Qt/Conversation/Tool → TTS → Electron 正常播完整段，使用者可聽且畫面與 History 正確。
- **可重跑**：同一代表性完整工作流冷／熱啟、再次執行皆能完成，不僅一次 mock PASS。

品質指標由 Codex 建議可比較的 baseline 和測試樣本，包括 eligible speech coverage、false-silence、long-form completion、語義錯播、TTFA、每段 synth/playback failure、額外 Token/延遲；**不得任意以過短 deadline 作驗收門檻**。如需設定數值，必須來自實測／官方契約／使用者選定的效益取捨。

## 6. Codex 自主設計與實作權限（給下一輪任務）

Codex 在實作獲授權後：
1. 先核對**目前 dirty WIP、正式 Running Runtime 與既有文件**；先辨認是否已載入 11 月修復，而不是用舊 log 假設今天同一問題仍在。
2. 可以主動提出更有效的 Speech 處理模式，調整既有 Parser、Policy、Repair、Prompt、TTS Queue、Pet 播放及必要的 interface。**此計畫不是逐檔 patch 清單**，不要求依照表格順序實作。
3. 若證據顯示原本的限制妨礙完整輸出，應主動檢討並修改，而不是再為它加一層人工確認、略過條件或硬上限。
4. 優先重用既有責任 Owner；不可為了「比較安全」無證據地新增整套防禦、重複 Provider、Queue/Manager 或降級業務目標。
5. 可以使用額外 LLM token 與語音工作量完成必要的修稿／語意審查；模型與成本由既有實際權限/官方計價/用量觀測支撐，不硬設本計畫自創 quota。若現有授權／外部服務明確禁止某類操作，保持邊界並回報真實阻擋。
6. 測試失敗先辨來源缺陷、基線回歸、測試環境與工具權限，不能靠大量重試相同工作來假裝修好。
7. 每階段回報 Source Diff、測試範圍、實際 Runtime adoption、完整桌面 E2E 與未驗項目。若修改正式運行路徑，保留針對本輪變更的 rollback；不要 reset／checkout 覆蓋其他 WIP。

建議自然里程碑（可合併、拆分、改排序）：
- M0：定位現況與失敗 trace，提出經證據比較的 A/B/C 設計。
- M1：修復整段錯拒、自然口播與必要模型修稿；明確區分語意不足與真實失敗。
- M2：按中央 TTS 實測整理長篇分段、段落依賴、播放隊列與完成語意。
- M3：正式 Qt／LLM／TTS／Pet 端到端驗證，回歸、修正、量測與交付。
- M4（有實測收益才進）：原生音訊 Streaming/更早可播放的 Speech Event；不是本版成功的前置條件。

### 停止條件／封版原則

不是「程式編譯完成」、也不是「12 次短句成功」；而是一般聊天與工具回答能正常自然發聲、代表性長篇能完成、技術內容不導致整段靜音、取消與播放結果一致、相同正式流程能重跑。若外部限制仍妨礙某項需求，要以可觀測的根因與明確未完成範圍呈現，不能將它藏進新 Gate。

## 7. 來源與查證連結

### 專案內的第一手資料（當前 Source 與既有測試）
- Open-LLM-VTuber/src/open_llm_vtuber/conversations/speech_presentation.py：SpeechLaneParser、filter_speech_lane、validate_semantic_lane。
- Open-LLM-VTuber/src/open_llm_vtuber/conversations/speech_recovery.py：repair 設計、20s、摘要字數偏好。
- Open-LLM-VTuber/src/open_llm_vtuber/conversations/conversation_utils.py：_natural_speech_chunks、queue_generated_speech、finalize_conversation_turn。
- Open-LLM-VTuber/src/open_llm_vtuber/conversations/tts_manager.py：群組 Fail-stop、有序佇列。
- Open-LLM-VTuber/src/open_llm_vtuber/tts/gpt_sovits_tts.py；.../utils/stream_audio.py：中央完整 WAV 與 Base64。
- pet-electron/renderer/src/backend/backend-client.ts；Open-LLM-VTuber/src/open_llm_vtuber/websocket_handler.py：播放與 ack。
- docs/agent-runs/kuro-concise-tool-speech-20261105/Progress.md；docs/agent-runs/kuro-tts-reliability-20261103/ReviewerReview.md：歷史證據及尚未驗收事項。
- docs/product/ProductVision.md、OperatingModel.md、QualityBar.md：產品願景、責任與品質要求。

### 外部官方／開源實作（2026-11-23 查閱）
1. **Pipecat TTSService 原始碼** — https://github.com/pipecat-ai/pipecat/blob/main/src/pipecat/services/tts_service.py
   參考：TextAggregationMode、skip_text_types、text_transforms、skip_tts、Audio Context、分段與播放順序。這是**可借鑑的機制**，不是 Kuro 已有功能，也不是所有 Provider 的成功保證。
2. **Pipecat PatternPairAggregator 官方參考** — https://reference-server.pipecat.ai/en/stable/api/pipecat.utils.text.pattern_pair_aggregator.html
   參考：跨 streaming chunk 辨識 pattern、REMOVE／KEEP／AGGREGATE 對應不同文字類型。這並非完整 Markdown AST，也不能取代語意校驗。
3. **LiveKit Agents Text and transcriptions** — https://docs.livekit.io/agents/multimodality/text/
   參考：tts_text_transforms、filter_markdown、filter_emoji、可串接的文字轉換、TTS-aligned transcripts。
4. **LiveKit Pipeline nodes and hooks** — https://docs.livekit.io/agents/logic/nodes/
   參考：tts_node，可客製 chunking、Provider 與 AudioFrame；非原生 streaming TTS 可使用句子 tokenizer。
5. **LiveKit Fallback strategies** — https://docs.livekit.io/agents/logic/fallback-strategies/
   參考：partial audio 已送出時的 fallback 與重複播音風險；「增加重試」不是萬用解。
6. **OpenAI Realtime Prompting — Rephrase Supervisor** — https://developers.openai.com/api/docs/guides/voice-prompting
   參考：Responder/Thinker 分工，閱讀最佳的文字未必適合朗讀，可以另外語音化。這是公開建議架構，不宣稱 Dot 私有實作相同。

注意：GitHub 的 main 分支會變動；Codex 真正引用外部程式碼設計時應確認當時 release/commit。外部來源只支持機制，不保證 Kuro 可以零成本複製其行為。若引用外部片段，尊重其 License，不直接大段搬碼。

## 8. 狀態與後續

- **現在**：Design completed，Source 查閱／公開參考來源查閱；沒有實作或部署。
- **下一輪**：Codex 收到實作授權時，先從 M0 baseline 和設計選型開始，再落實與驗收。模型/effort、速度等遵循當次授權，不在本文件硬指定。
- **Reviewer**：獨立用原始使用者症狀與本文不可降級目標驗收，不以單一測試或單段音訊完成取代完整產品成功。

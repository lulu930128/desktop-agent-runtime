# Kuro 多語理解與單輪雙輸出語音重構 — Plan (Frozen v1)

> 日期：2026-10-31  
> 狀態：使用者確認需求；本文件先固定目標與驗收，再執行程式修改。  
> 專案：C:\project\desktop-agent-runtime  
> 原則：不新增不必要的 AI call、平行資料來源、全域新 service 或過度驗證；既有工作 WIP 不覆蓋。

## 1. 問題與實際基線

目前 Kuro 的一般對話：
- 手打／語音輸入後由 Conversation Runtime 的主 LLM 理解並輸出，ASR 使用 sherpa-onnx SenseVoice 多語模型；多語辨識的實際精度尚未驗證。
- \`basic_memory_agent.py\` 用 sentence divider／display processor／tts_filter 生成 \`SentenceOutput\`；\`single_conversation.py\` 目前對 SentenceOutput 使用 \`defer_sentence_voice=True\`，直到主 LLM 最終輸出完畢才在 \`flush_deferred_sentence_speech\` 做語音處理。
- \`conversation_utils.py\` 透過 \`_build_speech_plan\`、spoken adapter、語言與格式過濾，然後呼叫 \`BridgeSpeechEngine.translate\`，跨程序至 \`bridges/deeplx_bridge.py /render_spoken\`，額外以 OpenAI Responses API 產生日文台詞／情緒；失敗可能再做 repair／fallback。
- \`TTSTaskManager\` 安排中央 \`GPT-SoVITS\` 合成與有序播放；中央 voice service 單一推論鎖、按需載入，並非 streaming PCM 首片段發聲。
- 2026-10-28 00:04:26 語音稿完成；第一段中央 TTS 54.735 秒、第二段 2.109 秒。這證明冷／熱模型路徑可差很大，但不能由此直接推定每天 2–30 秒的比例。
- 前一次唯讀觀測：\`18890/health\` online、\`model_loaded=null\`；Kuro 的 \`1188/23456/23567\` 未監聽，未做本次 live E2E。

## 2. 本次必須完成的產品行為

### 輸入與理解

1. 手動文字／語音輸入**自動辨認語言或混合語言**，不在輸入 UI 增加語言選擇器。主 LLM 接收原文或 ASR 原始轉錄，不能強制預先全篇翻成日文；術語、程式碼、檔名與上下文不得被語言判斷破壞。
2. 在主 LLM 同一個對話任務中理解多國語言；輸入可能是 zh-Hant、en、ja 或混合。辨識結果允許 \`unknown\`／\`mixed\`，不能靠單一字元草率定義整則語言。若 ASR 沒有可信語言碼，主 LLM 根據轉錄理解；語言碼只是輔助觀測，非新一輪必經的 AI 分類器。
3. **現有 Chat 完整文字回答**與長期記憶／History 所見文本維持原來可讀的呈現，不因語音語言改變而被日文口播內容覆蓋；本輪不新增「畫面回答語言」設定。

### 口播與設定

4. **同一次主 LLM 輸出包含兩個 lane**：\`display\`（完整解答）和 \`speech\`（口播自然語句），後端為輕量解析器、格式檢查與分流；一般成功路徑**不得再呼叫 /render_spoken 或另一個 LLM 摘要/翻譯**。
5. \`speech\` 直接以選定朗讀語言生成，預設日文（\`ja-JP\`），保留 Kuro 角色語氣與專有名詞讀音；原有固定日文提示只可在 ja-JP 使用，不得把 \`fixed_ja\` 當通用跨語系內容。
6. Qt **設定 → 語音與感知**新增「朗讀策略：極簡／摘要／詳細」（預設摘要）與「朗讀語言」（預設日文）。輸入語言與輸入方式不新增 UI 控制。這兩項為一般聊天口播設定，與既有 \`proactiveVoice\`（主動通知）明確分離。設定要有真實的單一持久化 owner，讀回後切換回合有效；不只在前端 localStorage 存假設定。
7. 語言設定協定預留 \`ja-JP\`、\`zh-Hant\`、\`en-US\` 等 BCP-47 locale，但**實際能否發聲須根據目前角色中央模型能力**。目前 Kuro/Yuki central package 以日文為預設；其他語言若未驗證，不得在 UI 假裝已正式支援。可明確標示實驗性／未驗證或不提供啟用，並在設計上可日後擴充；不可偷偷強制換成日文卻顯示英文已生效。
8. 保留對話既有字幕更新、工具 call/status、conversation complete、嘴型、情緒、取消／中斷行為及 Live2D / Qt owner 邊界。

### 口播內容策略

9. \`brief\`：只唸關鍵結論；\`summary\`：結論＋關鍵理由／限制／下一步；\`detailed\`：較完整的自然語句（仍不逐字念程式碼與表格）。不得只用固定字數截斷而漏失否定、失敗、不確定性。
10. 語意整理**由同一次主 LLM 負責**，不是主 LLM 結束後的另一個 AI classifier／summarizer。需使用主回答及已返回的工具證據，不能先於工具回覆就預先肯定結果。
11. 對 code fence、inline code、URL、file path、JSON、table、stack trace、dense log、原始技術 payload 等**完整留在 Display**；口播只保留重要結論與必要條件。用既有 \`SpeechPolicyEngine\`／\`conversation_utils\` 作 deterministic hard filter 與兜底，不額外建立新的平行語音政策引擎。
12. 股票價位、停損停利、數據 freshness、來源缺失、\`未驗證\`、操作失敗等，若屬關鍵資訊，口播不能被誤刪或反轉；語言轉換不得引入未出現在原始證據的事實。
13. 語音輸出協定需版本化／可測的解析狀態；兼容 \`stream=True\` 的主 LLM 和工具 loop。不能把系統控制標記／口播資料洩漏到 Qt Chat、History 或記憶，亦不能讓語音段落污染 tool-call arguments。

## 3. 工程決策（已固定）

- **A. 一輪主 LLM、雙 lane**；不是 \`LLM → 第二個 AI 分類器 → AI 翻譯 → TTS\`。即使主 LLM 本身多產出一些 speech tokens，也要省去成功路徑上的第二次獨立 API 往返。
- **B. 後端輕量分流**：保留 \`basic_memory_agent\`、\`single_conversation\`、\`SpeechPolicyEngine\`、\`TTSTaskManager\`、中央 TTS owner；新協定可用穩定的結構化 envelope／明確標記，但須能與 streaming、tool events 相容，並可可靠丟棄 malformed speech 而不破壞顯示回答。技術實作細節以最小必要變更選擇，不另做第二套對話 Runtime。
- **C. 禁止強制早唸不可靠結論**：第一版以工具結果／主回答確定後的口播語意正確為優先；能安全提前合成的片段才做 overlap。不要為了第一句快而錯報狀態。
- **D. Bridge**：保留現有語音 Bridge 原始碼作特定失敗路徑／rollback；**一般成功路徑不再進 Bridge 的第二輪 OpenAI**。fallback 必須有可辨理由、次數有界，且不需為了保持有聲而一再呼叫 LLM。失敗時允許顯示完整文字、略過語音。
- **E. 設定 owner**：沿用既有 Qt + Launcher/runtime config／Core setting ownership，先確認單一持久化來源及執行時套用方式。不得把設定只寫在角色 Prompt、Electron localStorage 或額外平行 manager；現有 \`proactiveVoice\` 不是聊天 speech setting，必要時以版本化 contract 擴充且保持舊值可讀。對目前實際語音能力不支持的 locale 必須表明不支援或未驗證。
- **F. 不擴大任務**：不動 Core task、OMI domain、Memory Core、交易、Mail、工具權限、不重訓 GPT-SoVITS、不改中央 owner 自動重啟策略、不主動 commit/push、也不啟停正式 Kuro 供人工測試。使用者將在完成後自行實機驗證。

## 4. 實作順序與驗收 Gate

### G0 — Baseline
- 唯讀確認 Git WIP／受影響檔案、現有 Qt 設定 owner、stream/agent event/tts 管線與現有測試。
- 保存受影響檔案基線，嚴格保留其他任務 dirty WIP；分辨新增變更與既有修改。

### G1 — 協定與輸出
- 建立單輪雙 lane 的 prompt、runtime parsing／routing；主 LLM 的 \`display\` 照常顯示與保存，\`speech\` 送 TTS。
- 不得直接把完整回答交給第二輪 render_spoken 作一般成功路徑；只在明確 fallback／unsupported 走舊服務。
- 若 malformed、缺少 speech、error、interrupted、tool loop 各情況，\`display\` 不丟失，且不重複送 TTS／不把標記顯示給使用者。

### G2 — 語音規則與多語
- 重用既有程式碼／URL／表格過濾、日文讀音、emotion 與 \`TTSTaskManager\`；調整為 locale-neutral input 與指定輸出語言。
- 依簡短、摘要、詳細三模式制定有用的口播範圍，對技術錯誤、價格／數字及限制保留關鍵語意。
- ASR／文字直接走同一主 LLM 理解；輸入語言自動、不新增前端輸入語言按鈕。

### G3 — Qt Settings 接線
- 在正式 Qt Settings 的「語音與感知」提供兩項設定：語音語言、口播策略；刷新與重開後可讀回、能影響下一個對話 turn。
- 避免和 Core proactiveVoice／Pet settings／Launcher profile 產生雙重 owner。
- 對未驗證語言語音能力如實顯示，不得承諾自然多語音色已可用。

### G4 — 定點驗證（Codex 執行）
- Syntax、關鍵 targeted tests、受影響 Qt/renderer build 或 smoke，僅按變更範圍。
- Fixture 至少覆蓋：繁中/英文/日文/混合輸入；簡單聊天；程式碼 + stack trace；表格 + URL；價格/停損及 unknown/stale；三種朗讀策略；voice unavailable；stream chunks；tool call；取消；silent fallback；設定 round-trip。
- 測量／留出埋點：LLM 完成／speech 準備、二次 Bridge 請求次數（成功路徑應 0）、TTS request 與完成、WebSocket send、Electron playing；不需實際付費 LLM／中央合成也能驗證 wiring。延遲實際數字未測前不得宣稱更快。
- Reviewer 檢查 Diff、回歸風險、正式路徑與測試結論；記錄本輪未驗證項目。

### G5 — 使用者實機驗收（非本輪自動執行）
- 使用者啟動／更新 Kuro 後：查看設定、切換簡短/摘要/詳細、用中文/英文/日文輸入，確認字幕完整且音色是設定語言。
- 測試程式碼/技術串與實際 TTS；記錄首次冷載及後續熱載的「LLM 回答完成 → 第一聲」延遲。
- 若需要 rollback，恢復受影響模組的原有 Bridge 語音路徑與預設設定，不動使用者歷史／記憶／中央模型包；保留新舊設定可讀性。

## 5. 完成標準與工作狀態

- **Source Ready**：G1–G3 完成，且主 LLM 成功路徑第二輪 speech render API = 0；Qt 設定有真實讀寫且能影響下一輪，核心工具／History／memory 不污染。
- **Targeted PASS**：G4 測試、建置與 Reviewer Diff 檢查通過；若失敗，報具體阻擋與實際影響。
- **Runtime / Desktop E2E：未驗證**，直到使用者在正式載入新版後回報完整對話、發聲、嘴型與延遲。Source Ready 不等於 E2E 完成。
- **保留現有資料、設定及 Git dirty WIP；不自動部署、commit 或 push。**

## 6. 交接與紀錄

- Codex 依本 \`Plan.md\` 原地實作；不可另立內容衝突的 Plan。只因新證據導致設計確實不可行時，需記錄證據與最小方案，不自行改變最終產品目標。
- 執行進度記錄在同目錄 \`Progress.md\`：Completed / Pending / Blocked / Unverified、改動檔案、測試命令與結果、Codex job/turn、Reviewer 審查與使用者 G5 手驗步驟。

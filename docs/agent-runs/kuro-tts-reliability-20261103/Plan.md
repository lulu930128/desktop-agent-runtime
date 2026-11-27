# Kuro TTS 可靠性與低延遲三階段計畫（2026-11-03）

> 狀態：長期計畫已固定；本輪只授權 Phase 1「錯誤靜音」定點修復。Phase 2/3 為規劃，未授權實作、部署或重啟。  
> 專案：`C:\project\desktop-agent-runtime`。語音中央 Owner：`C:\project\voice package\GPT-SoVITS`。  
> 本計畫不取代 `docs/product/{ProductVision,OperatingModel,QualityBar,Roadmap}.md`，也不改 Domain/Tool/Memory owner。

## 0. 現況、事實與基線

- 正式資料流：User/ASR → Open-LLM-VTuber 主 LLM → Display（Qt Chat / History / Memory）與 private `kuro.speech-lanes.v2` Footer → `SpeechLaneParser`／`SpeechPolicyEngine` → `queue_generated_speech` → `TTSTaskManager` → 中央 GPT-SoVITS `/tts`（完整 WAV）→ WS → Electron/Live2D。
- 2026-11-03 01:25:36 log：`route=dual_lane, lane_state=missing`，無 Speech；01:27:16 log：`option_unverified, stage=required_anchor, anchor_index=1, received_anchors=4, received_semantic_segments=1`；01:28:51–56：`ready → tts_request → TTS available=True → websocket_audio_sent`。
- 根因 1（Confirmed Defect）：`speech_presentation.py` 的 `_option_supported` 對少數跨語詞彙可判，對其他中文→日文建議通常只能得出「未確認」，卻由 `validate_semantic_lane` 採 all-or-silent。模型已有合法日文 speech，卻因 deterministic 證據不足而失聲。
- 根因 2（獨立狀態）：`missing` 是主 LLM 未提供私有日文 Speech，與「驗證錯誤拒絕已存在的 Speech」不同；不能用放寬 validator 憑空產生日文內容。現有長清單固定提示不是一般對話修復；不可聲稱本輪修好 missing。
- 現有中央引擎 `voice_service.py` 以 `streaming_mode=False, return_fragment=False` 完整合成 WAV；Kuro 已在 LLM 完成後按句切最多三段；現有 TTS POST response 是完整 WAV。此路徑並非真正的增量音訊流。
- 單次短句已觀察到 LLM/語音稿約 2.45 s、合成 4.52 s、WS 發送總約 6.98 s；**不等於首聲播放、平均、上限或保證可改善幅度**。
- Repo 目前有大量未提交 WIP、可能並行作業；實作前必須記錄當下 HEAD/status、Task-owned preimage，精準 patch，不能 reset/checkout 覆蓋他人的改動。
- 參考既有 `docs/agent-runs/kuro-speech-semantic-alignment-20261031/`、`kuro-display-speech-20261031/` 與 `kuro-multilingual-speech-20261031/`；保留原設計的工具／市場事實、數值與否定語意，以及 Display lossless。

## 1. 共同產品原則

1. **Speech Success Rate 優先**：合法、可用的日文口播，不因 deterministic validator 無法跨語驗證而無聲。不能把「未知」宣稱「一致」。
2. 保留完整 Display；Speech 是次要呈現，不能改寫事實、誤稱工具成功、顛倒價格、失敗、未驗證、否定與交易/操作前提。
3. 不重複輸出兩份可見文字；private Speech JSON 不進 Qt History/Memory/Tool args。
4. 同一角色音色與既有中央 TTS owner，保留取消、按序播放、去重、失敗回報與回合生命週期。
5. 不能因語音失敗拖住整體文字完成；不要為正常路徑額外要求第二次 LLM/Bridge；測量真實 TTFA，而非猜測效能。
6. 只有經證據確認不相容或必要時才修改 prompt、schema、central voice 或 Electron；不新增平行 Parser/Queue/Manager。
7. 規劃、Source test、實際 Runtime 合成、WS 訊息與 Electron 真正 playing 分開驗收，不以 Source PASS 宣告正式發聲成功。

## 2. Phase 1 — 修復錯誤靜音（本輪唯一實作範圍）

### 目標

- 把 **「確定不合法／確定衝突」** 與 **「無法跨語言確認」** 分開；後者允許現有已生成的自然日文 Speech 經正常 TTS 路徑播放，同時保留 structured `semantic_unverified` / `degraded` 診斷。
- 不增加新的 LLM 校稿、翻譯或語意 Judge，不以更多硬編碼同義詞、固定稿、Regex 列表填洞；也不降低重要事實的已知確定性檢查。
- 只針對已驗證的靜音根因做最小改動；**本輪不自動為 `missing` 觸發 Bridge 或猜測譯文**。將其如實列為 Remaining / Pending（如屬日文 Display 的同語直讀可在實作前先評估是否有既有路徑，不新增旁支）。

### 設計要求

- 在既有 `SpeechLaneParser` / `SpeechPolicyEngine` 內區分：
  - `ready`：通過形式與可驗證語意；
  - `semantic_unverified`（名稱可與現有 contract 對齊）：結構、語言與技術 payload 合法，沒有確定衝突，但像 `option_unverified` 的跨語詞彙檢查無足夠證據；**應送 TTS，不得當成 `ready`**；
  - `blocked`：malformed/schema、empty、technical payload、locale mismatch、明確數值或失敗/否定/狀態反轉、所需 speech segment 真的缺失等有證據的失敗，仍拒播。
- 維持 `source` 必須精確存在 Display、required anchor 引用存在、格式/重複 key 檢查。確切可檢的數字/價格/比例/錯誤碼、失敗與未驗證狀態不能被誤放行。
- `_option_supported` 目前把「難以語言比對」與「選項漏掉或否定」共用 false。修改時避免直接將所有 false 放行；需以現有可識別的明確矛盾保留拒播，其餘 unknown 作 soft fail。若現有 helper 無法可靠區分，採窄範圍退化並保留 diagnostics，不假稱已做完語意審核。
- Parser 必須保留 `semantic_unverified` 狀態所需的合法 Speech text；`queue_generated_speech` 必須確實接受它。若只改 validator reason 而未能佇列，等於未修。
- 觀察欄位：turn/route/contract/lane_state/reason/check stage/tts_chunks，與 `tts_request → tts_complete → websocket_audio_sent`；不輸出私人語音稿或工具 payload 至 log。
- 負向測試不能退化：工具 failure 或 blocked ≠ success，未驗證 ≠ 已確認，缺資料 ≠ 完整資料，價位/停損/負號/百分比/錯誤碼不能被反轉；維持 Markdown/URL/Code 的 Display 及語音隔離。
- 不修改中央 `voice_service.py`、WAV protocol、Electron renderer、Qt signed bundle、Tool Policy、MCP、Memory、DB、Commit/Push；本輪不重啟正式 Kuro 與中央服務。

### 建議修改點

- `Open-LLM-VTuber/src/open_llm_vtuber/conversations/speech_presentation.py`：Option 檢查的未知/確定衝突判定與 Parser Speech 保留。
- `Open-LLM-VTuber/src/open_llm_vtuber/conversations/conversation_utils.py`：`queue_generated_speech` 狀態接線、Log 診斷；必要時 `single_conversation.py` 的 final status。
- `tests/test_speech_semantic_alignment.py` 及既有`test_multilingual_speech.py`／`test_first_speech_latency.py` 定點補測；不要無故變更基線測試預期以求全綠。

### 驗收 Gate

1. 模擬「你好／我好餓／該不該吃宵夜」的中日自然語義但無可比對字詞的 v2 response：原先 `option_unverified`，修後應記錄 soft state，`TTS mock` 收到正確日文一次，Display/History/Memory 不變。
2. 模擬真正少一個 required action／已明確否定某操作、錯誤資訊、錯價、缺失 speech segment、malformed footer、technical payload、locale mismatch：按可確定的既有證據拒播或以 unverified 記錄，不得錯誤宣稱 verified。
3. 完整 `single_conversation → parser → queue → TTSTaskManager` mock fixture PASS；終結 ack、群組 cancel/fail-stop 不受影響；正常路徑 `bridge_requests=0`。
4. 定點 Python unit tests／source compile／diff check PASS；比對本輪 patch 與原有 WIP，明列 baseline failures。
5. Reviewer 獨立讀取實際 Source diff 與測試收據；正式 Runtime/音質/TTFA **另待使用者或獲授權的 runtime 測試**。不得把本 Gate 4 當成真人播放成功。

### 本輪狀態記錄

- Planned → Source Implemented → Targeted PASS → Reviewer Reviewed → Runtime Adopted → Desktop E2E Verified；請保留各層證據，不提前跳級。
- 若對「跨語詞義 unknown」仍難以用現有規則區分，不要自行加大型語意分類器；記錄限制與 fail/degrade 行為供 reviewer 評估。
- `missing` / 真正缺少日文 speech 的答覆為**獨立未解問題**。若要之後消除，須另行決定「僅 missing 才呼叫既有 Bridge」的額外延遲/費用，或修改主回應協定，但不屬本次 P1 silent false-reject scope。

## 3. Phase 2 — 中央 GPT-SoVITS 音訊串流（長期，**本輪不實作**）

**目標**：降低 TTS request → 第一個可播放音訊片段時間，不改角色音色或 Domain owner。

- 先隔離查明目前 GPT-SoVITS pipeline 對 `streaming_mode=True`、`return_fragment=True` 的真實支援、codec/sample rate/chunk boundary/句尾品質，辨別是真逐片生成或僅最終切塊；不得直接切換 production。
- 在中央 Owner 擴充有版本協商的 incremental endpoint/transport；對不支援 consumer 保留既有 `/tts` WAV 回退，禁止二次推論或平行模型服務。不要讓 Pet/Qt 管 TTS 模型。
- Kuro client/WS/Electron 加有序 chunk、buffer/backpressure、短靜音/句尾、cancel/seq/ack、發聲實際時間埋點；長句分片要控制語調、接縫與 GPU memory。
- 驗收：音訊片段可按序播放，cancel 不洩漏到下輪、斷線不重播、語音品質不劣化；量測 cold/warm P50/P95 TTFA、request→first chunk、request→final audio，以及人耳比較。
- **Gate**：Phase 1 Runtime 可用並有可比較的基線、真 GPU + consumer E2E 驗證能力，再獨立授權。

## 4. Phase 3 — LLM / Speech 增量生成與播放重疊（長期，**本輪不實作**）

**目標**：降低完整 LLM completion 等待，第一段可信 Speech 可在後續 Display 生成時排入 Phase 2 TTS；保留工具結果先完成、決策性限制不能提前說錯。

- 現行 v2 footer 位於完整 Display 結束後，**不能**只修改 TTS queue 就達成增量語音。需要有 versioned Speech Event/commit protocol；每段和 Display commit point、turn id、tool result snapshot、取消序號綁定。
- 必須避免先口播「成功」後工具才回「失敗」；未完成上下文與依賴後文條件的內容不能先播。
- 增量回退到 Phase 1 完整 footer / Phase 2 音訊串流；禁止取消後的 stale speech 進入新回合。
- 量測 token→committed segment→first synth→Electron playing 的重疊改善、語義錯播/漏播率、中斷恢復與語音自然度；驗收包括工具延遲、長文、部分回應、關鍵數值與多選項。
- **Gate**：Phase 2 穩定、已有即時音訊傳輸/播放收據，再另立設計與授權。

## 5. 統一度量、回滾、工作結束定義

- 核心量測：Speech Success Rate（有效且應可發聲的回答中實際播放比率）、TTFA（使用者送出→Electron 真正 playing），以及 `missing`／`semantic_unverified`／`blocked` 的分類分布。請保留 LLM completed、speech committed、TTS first byte、TTS complete、WS audio sent、Electron playing 的同事件關聯；不同 process 的 monotonic clocks 不能直接相減。
- 每個 Phase 均區分 Source、Installed Release、實際 Process/Port、中央 TTS、Qt/Electron E2E。Log 只能說明到其實際觀察的邊界。
- Phase 1 回滾：保留局部 patch / preimage，核對後精準逆轉；不要以整檔 `git checkout` 覆蓋 dirty repo。Phase 2 保留原完整 WAV 介面；Phase 3 保留完整 footer 路徑。
- **本輪的終點**：Phase 1 source 補丁＋最小定點測試＋Reviewer diff 複查；不包含服務重啟、部署、中心模型變更、Phase 2/3、Git commit/push。

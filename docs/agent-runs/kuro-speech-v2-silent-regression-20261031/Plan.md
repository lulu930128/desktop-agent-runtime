# Kuro v2 口播全靜音回歸 — 定點修復計畫（2026-10-31）

> 專案：`C:\project\desktop-agent-runtime`  
> 主問題：正式 Kuro 更新後，Display 正常，但部分對話沒有 TTS 聲音。  
> 本輪狀態：修復計畫；後續 Codex 依此文件實作，結果寫同目錄 `Progress.md`。  
> 原則：以實際證據與最小修改修復既有正式路徑；不另建平行引擎、Queue、Service、LLM 二次翻譯或過度防護。保留現有 dirty WIP。

## 1. 已確認證據與範圍

**正式 Runtime 證據（不是只憑單元測試）**

- 2026-10-31 **13:09:51**，舊一輪已見 `speech_timing.state=ready`；實際 `tts_request` → 中央 `synthesis passed`（22.875 秒）→ `websocket_audio_sent`。此僅證明傳送，不冒充 Electron 播放／人耳聽感。
- 2026-10-31 **13:54:26** 新 Kuro conversation runtime 啟動；正式 Log `launcher_logs/llm/2026_10/31/2026-10-31_13-54-21_kuro_01/llm.combined.log`：
  - **13:57:58** `contract=kuro.speech-lanes.v2, state=technical_payload`，未見 TTS request。
  - **14:00:13** `contract=kuro.speech-lanes.v2, state=option_unverified`，未見 TTS request。
  - 兩輪 `anchors=0 / semantic_segments=0` 為現有計數位置的結果，**不能單憑它推定模型原先未生成 anchors/segments**，因 parser 驗證失敗時未將原始欄位回傳。
- 中央 `127.0.0.1:18890/health` 目前 HTTP 200、`status=available`、`model_loaded=kuro`、PID 34284；它仍是缺少 `preload` capability 的舊 runtime。本次「未送出 TTS」與中央預載換版是**兩個問題**，不應混為一談。
- 同一回合另有 MCP `omi_ask` 的 `invalid_arguments`，但非本輪 TTS 根因；保留原有 tool 結果與錯誤語意，不修改 MCP/tool schema。

**正規責任鏈（Production Path）**

`openai_llm → basic_memory_agent → SpeechLaneParser / SpeechPolicyEngine → single_conversation.queue_generated_speech → TTSTaskManager → central GPT-SoVITS → WS → Electron`。

定位：
- `Open-LLM-VTuber/src/open_llm_vtuber/conversations/speech_presentation.py`：`filter_speech_lane()` 對 technical payload 的整段拒絕；`validate_semantic_lane()` 對 options 行動驗證。
- `.../conversations/conversation_utils.py`：`queue_generated_speech()` 在 `state != ready` 時回傳 `speech-status:unavailable`，無 TTS。
- `Open-LLM-VTuber/prompts/utils/speech_lanes_prompt.txt`：v2 一輪雙輸出提示。
- `tests/test_speech_semantic_alignment.py`、`tests/test_multilingual_speech.py`、`tests/test_first_speech_latency.py`：現有回歸基準。

**問題分類**

- Confirmed Defect / P1：正式新版在兩次真實對話跳過語音、影響核心桌寵體驗。
- 待確認：兩次分別是主 LLM 生成了不適合朗讀的字串，還是 validator 錯殺合理自然口播；現有 Log 只留 reason，**不可假裝已取得被拒絕的原文**。
- 不在本輪處理：中央服務預載套版／冷啟動延遲、其他 MCP 修復、Qt/UI 大改、音色／讀音詞典、Memory、History、OMI。

## 2. 修改目標與取捨

1. **恢復有效日文口播**：一般日常對話、提到程式碼或 URL 的技術說明、工具失敗與「兩種可選方案」回答，不能因過度寬泛的詞法檢查而無故靜音。
2. **保留雙 lane**：Display 原樣完整可讀；Speech 仍由主 LLM 同一次 final 回答提供，**正常路徑 Bridge / second LLM calls = 0**。保留 v1 parser 相容作為退路，但不自動開第二次 AI。
3. **不憑空改變語意**：重要錯誤、失敗、未驗證、數值／停損以及實際不同選項不可在口播中反轉或漏掉。已能確定的矛盾、非法 JSON、未知 anchor、真實 raw code/URL/path 仍應拒絕。不能把失敗直接標成成功，也不能僅憑 source_ids 完整就放過漏選項。
4. **避免不必要的新限制**：不新增 allowlist、安全 gate、雙重審批、新 service 或新 validator；只修現有 `SpeechPolicyEngine` 與必要 prompt、少量診斷。
5. **釐清失敗類型**：區分「模型生成 speech 不合約」和「validator 過度拒絕」，有足夠的 `reason / rule_id / segment_index / count` 定點診斷（避免記錄私人全文、tool payload、秘密）。
6. **驗收分層**：Source/fixtures PASS ≠ 正式已載入新 Source ≠ 中央已推論 ≠ Electron 正在播放。

## 3. 執行 Gate（Codex）

### G0 — 固定基線與重現

- 先讀本 Plan、原 `kuro-speech-semantic-alignment-20261031/{Plan,Progress}.md`、repo `AGENTS.md`、目前 Git dirty status、受影響檔案最新內容；保存必要 preimage hash 與 scoped diff，絕不 reset/checkout 覆寫並行 MCP 變更。
- 不讀取私人歷史全文作測試輸入。以 13:57 `technical_payload`、14:00 `option_unverified` 的**結構與情境**建立 synthetic v2 fixture。以正反案例證明目前 validator 哪條 regex／選項切分會拒絕可口播內容；若只有模型產生不合規內容，明確區分 prompt 與 validator 的責任。
- 確認正常 v1/v2、工具 loop、異常回合的音訊送出行為，最小化修改檔案數。

### G1 — 修復技術內容誤判

- 檢查 `filter_speech_lane()` 的 technical 正規式：只針對**真正需要保留在 Display 的 raw code/fence、URL、實際路徑、traceback、JSON/table/log**拒絕，避免將自然日文描述或一般技術詞彙整段判死。優先修精準比對條件，不對整段盲目刪字或無根據拼接句子。
- 若輸入確實包含原始技術 payload，維持 Display 完整、Speech 的明確原因與不發 raw payload 的行為；補對應正反 fixture。
- 口播 prompt 使用現有 `speech_lanes_prompt.txt` 明確要求「自然口語敘述，不要複製 Display 裡的原始欄位、程式碼、JSON 等」。只做與實際故障有關的最小 prompt 調整。

### G2 — 修復選項語意誤判

- 在 `_option_parts`、`_option_supported` 及 v2 anchor/coverage 實際流程，精確重現正常日文兩方案被標 `option_unverified` 的情況；檢查正規式是否把自然動作詞、不同句法、選項的句子邊界誤拒。
- 允許**已能確認**完整涵蓋選項的自然日文同義表述；保留對「只提到一個選項」「只說詳情在畫面」「把可執行行動誤說為不可執行」的拒絕。不得直接全域移除 option check。
- 對**無法以目前 deterministic 規則證明**的跨語語意，保留誠實的 unknown/unverified 診斷；若要改 soft-fail，需證明不會放過上述負案例，否則不能以「避免靜音」為由全面放行。
- 確認 required anchor 狀態、重要數字、否定／失敗／未驗證邏輯未遭破壞。

### G3 — 診斷與低副作用降級

- 最小化改善 `speech_timing` 或 `speech-status` 的觀測：report v1/v2、`ready/blocked` 的精確 rule/reason，若合適附有限 segment/anchor count，避免把 validation failed 的 `0` 誤讀成 LLM 生成 0。
- 不寫入私人 spoken/Display 全文至 Log，不另增 telemetry server；無需要時不修改 Qt/Electron。
- 若仍有合法語音被拒的少量 blind spot，記錄「剩餘可復現的限制」及下一次人工驗收案例。不要以自動再請另一模型或自動切 legacy Bridge 掩蓋此問題。

### G4 — 定點測試與端到端隔離驗證

- 補 `tests/test_speech_semantic_alignment.py` 正反 cases：
  - 短日常問候、中日混合提問、普通技術說明含程式語彙（自然日語口播 PASS）。
  - Display 含 code fence、URL、Windows/Unix path、JSON/table、stack trace；Speech 用自然語句摘要 PASS；Speech 真有原始技術 payload FAIL。
  - 不同日文句式表達兩種選項 PASS；漏一個選項／反轉動作／只說在畫面 FAIL。
  - 工具被拒、`invalid_arguments`、失敗、尚未驗證、部分缺失、價格/停損重要數值，Speech 不反轉、Display/history 完整。
  - malformed/invalid anchors、取消、工具 continuation、legacy v1 compatibility、最多三段 TTS / fail-stop、完成 ack。
- 不只單測 validator：使用**現有正式 parser → queue_generated_speech → TTSTaskManager → mock central/audio WS** 的隔離路徑，確認先前合理的兩種情境均 `ready`，會排 `tts_request` 且傳出音訊；錯誤案例不誤送。不得宣稱假音訊就是正式發聲成功。
- 跑必要的 `test_speech_semantic_alignment.py`、`test_multilingual_speech.py`、`test_first_speech_latency.py`、TTS pronunciation pipeline targeted suites、syntax、scoped diff check。僅因受影響共享依賴才擴大測試，不做無意義全專案重驗。
- 確保正常成功路徑不增加第二輪 OpenAI／Bridge 呼叫，影響 TTS 首句/WS 的變更有真實測試。
- 記錄測試 command、PASS/FAIL、獨立可審的精確 Diff、未測範圍至同目錄 `Progress.md`。

### G5 — 交付與正式換版條件（本輪不自行重啟）

- 程式碼修改、isolated tests 與證據完成後交 Reviewer 審查；區分 `Source Ready`、`Targeted PASS`、`Installed Release`、`Runtime`、`Desktop E2E`。
- **不自行停止/重啟**現行 Kuro Launcher／Conversation Runtime／中央 GPT-SoVITS，也不重建 Qt bundle（無涉 Qt source 時）；不 commit/push、不刪資料、不進行真實金融委託。
- 後續正式切換由原 lifecycle owner 依授權操作；用新的 conversation PID/開始時間、實際載入 source hash、獨立短聊天與技術/兩方案 turn，追 `state=ready → tts_request → tts_complete → websocket_audio_sent → Electron playing`；最後由使用者實際聽感驗收。
- 如果修復引入回歸，僅依保存的本輪 preimage/精確 Patch 還原本輪檔案，保留其他 WIP；僅在 v2 本次修復不可行且證據明確時提供 v1 prompt 最小 rollback 步驟，**不默默自行啟用第二輪 Bridge**。

## 4. 最終驗收條件

1. 可重現的**正常**技術說明與自然日文雙選項不再被錯殺；實際 production-path 的隔離 TTS queue 有音訊事件。
2. 真正包含 raw payload 或漏掉重要事實/選項仍能被精準拒絕；Display/History/Memory/tool args 不污染。
3. 保持 `kuro.speech-lanes.v2` 一輪雙輸出、v1 rollback 兼容與現有語音設定；正常路徑 second LLM/Bridge = 0。
4. 對舊問題清楚提供：原始原因、受影響檔案、改動意圖、實際測試、具體剩餘盲點、G5 實機檢查步驟。
5. 不變更中央服務和其他進行中的 MCP/WIP；**沒有 runtime adoption 證據前不可宣稱「桌寵已恢復說話」。**
